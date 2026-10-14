"""Light-weight ingester for SCANNED PDFs: page image -> Gemini vision -> Markdown -> Elements.

Needs only PyMuPDF (page rendering) + the standard library (HTTP). No torch / pandas / onnx.
Progress is cached per page in <out>/pages/pNNN.md, so you can stop and resume at any time
(free-tier quotas!). Set GEMINI_API_KEY (free key from aistudio.google.com).
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from schema import Element, save_elements
from utils import clean_inline, is_bullet_line, strip_bullet

try:
    import pymupdf
except ImportError:                      # older PyMuPDF
    import fitz as pymupdf

API = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")   # run --list-models if it 404s

PROMPT = """You are transcribing one scanned page of a university prospectus into Markdown.
Rules:
- Keep the original reading order (handle multi-column layouts column by column).
- Headings: use '#', '##', '###' according to their visual importance on the page.
- Tables: output Markdown pipe tables, one row per line, keep EVERY column and row, merge multi-line cell text into one cell. Never invent a header; if the page continues a table without a header row, just output the rows.
- Lists: one '- ' line per bullet (keep numbering like '1.' if present).
- Omit running headers, footers and page numbers.
- Photos/diagrams: only if informative, add one line like [Figure: short description]. Ignore logos and decoration.
- Transcribe text exactly. Do not summarise, translate or add commentary.
- Output ONLY the Markdown. If the page is blank, output nothing."""


class DailyQuotaError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def _request(url: str, key: str, body: dict | None = None, timeout: int = 120) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("Set your key first:  $env:GEMINI_API_KEY=\"...\"  (PowerShell)  |  export GEMINI_API_KEY=...")
    return key


def list_models() -> None:
    key, token = _key(), ""
    while True:
        d = _request(f"{API}/models?pageSize=100" + (f"&pageToken={token}" if token else ""), key)
        for m in d.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                print(m["name"].replace("models/", ""))
        token = d.get("nextPageToken", "")
        if not token:
            break


def call_gemini(image: bytes, mime: str, model: str, key: str, max_retries: int = 6) -> str:
    body = {"contents": [{"parts": [{"text": PROMPT},
                                    {"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode()}}]}],
            "generationConfig": {"temperature": 0}}
    url = f"{API}/models/{model}:generateContent"
    for attempt in range(max_retries):
        try:
            data = _request(url, key, body)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")
            if e.code in (429, 500, 503):
                low = msg.lower()
                if e.code == 429 and ("perday" in low or "per day" in low or "daily" in low):
                    raise DailyQuotaError(msg[:300])
                wait = min(90, 8 * 2 ** attempt)
                print(f"   HTTP {e.code}, retrying in {wait}s ...")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Gemini HTTP {e.code}: {msg[:500]}")
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError("Gemini: retries exhausted")

    cands = data.get("candidates") or []
    if not cands:
        return ""
    text = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))
    return re.sub(r"^```(?:markdown|md)?\s*\n|\n```\s*$", "", text.strip()).strip()


def render_page(page, dpi: int = 150) -> tuple[bytes, str]:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), colorspace=pymupdf.csGRAY)
    try:
        return pix.tobytes("jpeg", jpg_quality=85), "image/jpeg"
    except Exception:
        return pix.tobytes("png"), "image/png"


# --------------------------------------------------------------------------- #
# Markdown -> Elements
# --------------------------------------------------------------------------- #
_SEP = re.compile(r"^:?-{2,}:?$")
_FIG = re.compile(r"^\[(?:figure|image|photo|chart|diagram)\s*[:\-]?\s*(.*)\]$", re.I)


def _split_row(line: str) -> list[str]:
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    cells = re.split(r"(?<!\\)\|", s)
    return [clean_inline(re.sub(r"<br\s*/?>", " ", c).replace("\\|", "|")) for c in cells]


def md_to_elements(md: str, page: int) -> list[Element]:
    els: list[Element] = []
    buf: list[str] = []
    lines = md.splitlines()

    def flush():
        if buf:
            els.append(Element("paragraph", page, clean_inline(" ".join(buf))))
            buf.clear()

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1
        if not line:
            flush()
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", line)
        if m:
            flush()
            text = clean_inline(m.group(2).replace("*", ""))
            if text:
                els.append(Element("heading", page, text, level=len(m.group(1))))
            continue
        if line.startswith("|"):
            flush()
            tl = [line]
            while i < len(lines) and lines[i].strip().startswith("|"):
                tl.append(lines[i].strip())
                i += 1
            rows = [_split_row(l) for l in tl]
            has_sep = len(rows) > 1 and all(_SEP.match(c.strip()) for c in rows[1] if c.strip()) and any(rows[1])
            if has_sep:
                rows.pop(1)
            rows = [r for r in rows if any(c.strip() for c in r)]
            if not rows:
                continue
            ncols = max(len(r) for r in rows)
            rows = [r + [""] * (ncols - len(r)) for r in rows]
            first_on_page = not els
            if has_sep and not first_on_page:
                els.append(Element("table", page, header=rows[0], rows=rows[1:]))
            else:   # may be a continuation of the previous page's table; the splitter decides
                els.append(Element("table", page, header=None, rows=rows))
            continue
        fm = _FIG.match(line)
        if fm:
            flush()
            if fm.group(1).strip():
                els.append(Element("picture", page, description=clean_inline(fm.group(1))))
            continue
        if is_bullet_line(line):
            flush()
            els.append(Element("list_item", page, clean_inline(strip_bullet(line))))
            continue
        if raw.startswith("  ") and not buf and els and els[-1].type == "list_item":
            els[-1].text = clean_inline(els[-1].text + " " + line)
            continue
        buf.append(line)
    flush()
    return [e for e in els if e.text or e.rows or e.description]


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def ingest_gemini(pdf_path, out_dir, model: str | None = None, pages: tuple[int, int] | None = None,
                  delay: float = 6.0, dpi: int = 150) -> list[Element]:
    model = model or DEFAULT_MODEL
    key = _key()
    out = Path(out_dir)
    pdir = out / "pages"
    pdir.mkdir(parents=True, exist_ok=True)
    pdf = pymupdf.open(str(pdf_path))
    a, b = pages if pages else (1, len(pdf))
    b = min(b, len(pdf))
    print(f"[gemini] model={model} pages {a}-{b} (cached pages are skipped)")

    for pno in range(a, b + 1):
        f = pdir / f"p{pno:03d}.md"
        if f.exists():
            continue
        img, mime = render_page(pdf[pno - 1], dpi)
        try:
            md = call_gemini(img, mime, model, key)
        except DailyQuotaError as e:
            print(f"[gemini] DAILY QUOTA reached at page {pno}. Progress is saved; re-run later "
                  f"(or use another key/model). {e}")
            break
        f.write_text(md, encoding="utf-8")
        print(f"[gemini] page {pno}/{b} done ({len(md)} chars)")
        time.sleep(delay)

    elements: list[Element] = []
    combined, missing, empty = [], [], []
    for pno in range(a, b + 1):
        f = pdir / f"p{pno:03d}.md"
        if not f.exists():
            missing.append(pno)
            continue
        md = f.read_text(encoding="utf-8")
        if not md.strip():
            empty.append(pno)
        combined.append(f"<!-- page {pno} -->\n{md}")
        elements += md_to_elements(md, pno)
    (out / "prospectus.gemini.md").write_text("\n\n".join(combined), encoding="utf-8")
    save_elements(elements, out / "elements.json")
    if missing:
        print(f"[gemini] WARNING: {len(missing)} pages not processed yet: {missing[:10]}{'...' if len(missing) > 10 else ''}")
    if empty:
        print(f"[gemini] note: empty output for pages {empty} (blank pages or blocked responses)")
    return elements