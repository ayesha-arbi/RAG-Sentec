"""Small text helpers shared across stages."""
from __future__ import annotations

import re

# ---------- tokens ----------
_enc = None


def count_tokens(text: str) -> int:
    """Token count. Uses tiktoken if available, else a word-based estimate.
    Tip: for exact limits, swap in your embedding model's own tokenizer."""
    global _enc
    if _enc is None:
        try:
            import tiktoken
            _enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _enc = False
    if _enc:
        return len(_enc.encode(text))
    return int(len(text.split()) * 1.3) + 1


# ---------- cleaning ----------
_LIGATURES = {"\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi", "\ufb04": "ffl"}
_SYMBOL_BULLET = re.compile(r"^\s*[•▪◦●■□◆\-–—*]\s+")
_ANY_BULLET = re.compile(r"^\s*(?:[•▪◦●■□◆\-–—*]|\(?\d{1,2}[.)]|\(?[a-z][.)])\s+")


def clean_inline(s: str) -> str:
    """Normalise a paragraph: ligatures, soft hyphens, line-break hyphenation, whitespace."""
    if not s:
        return ""
    for k, v in _LIGATURES.items():
        s = s.replace(k, v)
    s = s.replace("\u00ad", "").replace("\u00a0", " ")
    s = re.sub(r"(\w)-\s*\n\s*([a-z])", r"\1\2", s)   # re-join words hyphenated at line end
    s = re.sub(r"\s*\n\s*", " ", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def strip_bullet(s: str) -> str:
    """Remove symbol bullets (keeps numbering, since order can matter)."""
    return _SYMBOL_BULLET.sub("", s, count=1).strip()


def is_bullet_line(s: str) -> bool:
    return bool(_ANY_BULLET.match(s))


def split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9("“•])', text.strip())
    return [p for p in parts if p]


# ---------- tables ----------
def _cell(c) -> str:
    return re.sub(r"\s+", " ", str(c).replace("|", "\\|")).strip()


def table_to_markdown(header: list[str] | None, rows: list[list[str]]) -> str:
    ncols = max([len(header or [])] + [len(r) for r in rows] + [1])
    hdr = list(header) if header else [f"Col {i + 1}" for i in range(ncols)]
    hdr += [""] * (ncols - len(hdr))
    lines = ["| " + " | ".join(_cell(h) for h in hdr) + " |", "|" + "|".join(["---"] * ncols) + "|"]
    for r in rows:
        r = list(r) + [""] * (ncols - len(r))
        lines.append("| " + " | ".join(_cell(c) for c in r) + " |")
    return "\n".join(lines)


def row_to_kv(header: list[str] | None, row: list[str]) -> str:
    """'Column: value; Column: value' - embeds far better than pipes and dashes."""
    if not header:
        return "; ".join(_cell(c) for c in row if str(c).strip())
    return "; ".join(f"{_cell(h)}: {_cell(c)}" for h, c in zip(header, row) if str(c).strip())