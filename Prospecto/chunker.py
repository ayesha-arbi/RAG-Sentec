"""Stage 3 - Chunker.

list[Section] -> list[Chunk]

Rules:
  * Text: pack whole paragraphs up to `max_tokens`; long paragraphs are split on sentences (with overlap).
  * Lists: kept together with their intro line ("Required documents:"); if too long, intro is repeated per piece.
  * Tables: never split mid-row. Small table = 1 chunk. Big table = row groups with the header repeated.
            `text` is markdown (for the LLM); `embed_text` is "Column: value" rows (for the embedder).
  * Pictures: only chunked if they have a caption / VLM description.
  * Every chunk gets a breadcrumb prefix in `embed_text` (and optional LLM-written context blurb).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from schema import Chunk, Element, Section
from utils import count_tokens, row_to_kv, split_sentences, table_to_markdown


@dataclass
class ChunkConfig:
    doc_title: str = "University Prospectus"
    max_tokens: int = 350          # keep below your embedder's limit (bge-small/e5: 512, MiniLM: 256!)
    min_tokens: int = 80           # smaller tail chunks get merged into the previous one
    overlap_sentences: int = 1     # only used when a single paragraph must be split
    max_table_tokens: int = 600
    table_embed_mode: str = "kv"   # "kv" | "markdown"
    include_pictures: bool = True


@dataclass
class _Block:
    text: str
    page: int
    kind: str = "para"             # para | list
    intro: str = ""
    atomic: bool = False           # already-split pieces must not be re-packed with neighbours
    page_end: int = 0

    def __post_init__(self):
        self.page_end = self.page_end or self.page


# ----------------------------- splitting helpers ----------------------------- #
def _hard_split(text: str, max_tokens: int) -> list[str]:
    out, cur = [], []
    for w in text.split():
        cur.append(w)
        if len(cur) > 1 and count_tokens(" ".join(cur)) > max_tokens:
            out.append(" ".join(cur[:-1]))
            cur = [w]
    if cur:
        out.append(" ".join(cur))
    return out


def _greedy(units: list[str], joiner: str, max_tokens: int, overlap: int = 0, prefix: str = "") -> list[str]:
    expanded: list[str] = []
    for u in units:
        expanded += _hard_split(u, max_tokens) if count_tokens(prefix + u) > max_tokens else [u]
    pieces: list[list[str]] = []
    cur: list[str] = []
    for u in expanded:
        if cur and count_tokens(prefix + joiner.join(cur + [u])) > max_tokens:
            pieces.append(cur)
            cur = (cur[-overlap:] if overlap else []) + [u]
            if count_tokens(prefix + joiner.join(cur)) > max_tokens:
                cur = [u]
        else:
            cur.append(u)
    if cur:
        pieces.append(cur)
    return [prefix + joiner.join(p) for p in pieces]


def _split_long_block(b: _Block, cfg: ChunkConfig) -> list[_Block]:
    if b.kind == "list":
        lines = b.text.split("\n")
        prefix = (lines[0] + "\n") if b.intro else ""
        items = lines[1:] if b.intro else lines
        texts = _greedy(items, "\n", cfg.max_tokens, prefix=prefix)
    else:
        texts = _greedy(split_sentences(b.text), " ", cfg.max_tokens, overlap=cfg.overlap_sentences)
    return [_Block(t, b.page, b.kind, b.intro, atomic=True, page_end=b.page_end) for t in texts]


def _pack(blocks: list[_Block], cfg: ChunkConfig) -> list[list[_Block]]:
    units: list[_Block] = []
    for b in blocks:
        units += _split_long_block(b, cfg) if count_tokens(b.text) > cfg.max_tokens else [b]

    packs: list[list[_Block]] = []
    cur: list[_Block] = []
    cur_tok = 0
    for u in units:
        t = count_tokens(u.text)
        if u.atomic:
            if cur:
                packs.append(cur); cur, cur_tok = [], 0
            packs.append([u])
            continue
        if cur and cur_tok + t > cfg.max_tokens:
            packs.append(cur); cur, cur_tok = [], 0
        cur.append(u); cur_tok += t
    if cur:
        packs.append(cur)

    def tok(p): return count_tokens("\n\n".join(x.text for x in p))
    if (len(packs) > 1 and not any(x.atomic for x in packs[-1]) and not any(x.atomic for x in packs[-2])
            and tok(packs[-1]) < cfg.min_tokens and tok(packs[-1]) + tok(packs[-2]) <= cfg.max_tokens * 1.25):
        packs[-2].extend(packs.pop())
    return packs


# ----------------------------- table helpers ----------------------------- #
def _table_chunk_texts(e: Element, caption: str, cfg: ChunkConfig):
    """Yield (markdown_text, embed_body) per table chunk."""
    header, rows = e.header, e.rows or []
    label = caption.strip()
    full_md = (label + "\n\n" if label else "") + table_to_markdown(header, rows)
    if count_tokens(full_md) <= cfg.max_table_tokens or len(rows) <= 1:
        groups = [rows]
    else:
        base = count_tokens(label) + count_tokens(table_to_markdown(header, []))
        groups, cur, cur_tok = [], [], base
        for r in rows:
            rt = count_tokens(" | ".join(r)) + 3
            if cur and cur_tok + rt > cfg.max_table_tokens:
                groups.append(cur); cur, cur_tok = [], base
            cur.append(r); cur_tok += rt
        if cur:
            groups.append(cur)
    for gi, g in enumerate(groups):
        part = f" (part {gi + 1}/{len(groups)})" if len(groups) > 1 else ""
        title = (label or ("Table" if part else "")) + part
        md = (title + "\n\n" if title else "") + table_to_markdown(header, g)
        if cfg.table_embed_mode == "kv" and header:
            body = (title + "\n" if title else "") + "\n".join(row_to_kv(header, r) for r in g)
        else:
            body = md
        yield md, body, len(groups)


# ----------------------------- main ----------------------------- #
def chunk_sections(sections: list[Section], cfg: ChunkConfig | None = None,
                   contextualizer: Callable[[str, str], str] | None = None) -> list[Chunk]:
    """`contextualizer(section_text, chunk_text) -> short blurb` is an optional hook for a free local LLM
    (Ollama / Gemini free tier) to write 'contextual retrieval' blurbs. Leave None to skip."""
    cfg = cfg or ChunkConfig()
    chunks: list[Chunk] = []

    for sec in sections:
        prefix = f"[{cfg.doc_title} > {' > '.join(sec.path)}]\n"
        counter = 0

        def add(ctype, text, body, p0, p1, extra=None):
            nonlocal counter
            if not text.strip():
                return
            embed = prefix + body
            if contextualizer:
                try:
                    blurb = contextualizer(sec.text, text)
                    if blurb:
                        embed = prefix + blurb.strip() + "\n" + body
                except Exception:
                    pass
            chunks.append(Chunk(
                chunk_id=f"{sec.section_id}-c{counter:03d}", section_id=sec.section_id, content_type=ctype,
                text=text, embed_text=embed, section_path=sec.path, page_start=p0, page_end=p1,
                n_tokens=count_tokens(text), extra=extra or {}))
            counter += 1

        els = sec.elements
        # attach captions to the neighbouring table / picture
        attached: dict[int, str] = {}
        skip: set[int] = set()
        for i, e in enumerate(els):
            if e.type != "caption":
                continue
            if i + 1 < len(els) and els[i + 1].type in ("table", "picture"):
                attached[i + 1] = e.text; skip.add(i)
            elif i > 0 and els[i - 1].type in ("table", "picture") and (i - 1) not in attached:
                attached[i - 1] = e.text; skip.add(i)

        blocks: list[_Block] = []

        def flush():
            for pack in _pack(blocks, cfg):
                text = "\n\n".join(b.text for b in pack)
                add("text", text, text, min(b.page for b in pack), max(b.page_end for b in pack))
            blocks.clear()

        for i, e in enumerate(els):
            if i in skip:
                continue
            if e.type in ("paragraph", "footnote", "caption"):
                blocks.append(_Block(e.text, e.page))
            elif e.type == "heading":
                blocks.append(_Block(f"**{e.text}**", e.page))
            elif e.type == "list_item":
                if blocks and blocks[-1].kind == "list":
                    blocks[-1].text += "\n- " + e.text
                    blocks[-1].page_end = e.page
                else:
                    intro = ""
                    if blocks and blocks[-1].kind == "para" and blocks[-1].text.rstrip().endswith(":"):
                        intro = blocks.pop().text
                    blocks.append(_Block((intro + "\n" if intro else "") + "- " + e.text, e.page, "list", intro))
            elif e.type == "table":
                flush()
                cap = e.caption or attached.get(i, "")
                for md, body, n_parts in _table_chunk_texts(e, cap, cfg):
                    add("table", md, body, e.page, e.page_end or e.page, {"table_parts": n_parts})
            elif e.type == "picture":
                flush()
                desc = e.description or e.caption or attached.get(i, "")
                if cfg.include_pictures and desc:
                    add("image", desc, desc, e.page, e.page, {"image_path": e.image_path})
        flush()
    return chunks