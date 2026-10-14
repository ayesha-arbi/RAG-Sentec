"""Run: PDF -> elements -> sections -> chunks, and write files you can inspect.

    python run_pipeline.py prospectus.pdf --out out                 # docling
    python run_pipeline.py prospectus.pdf --out out --ocr           # scanned pages
    python run_pipeline.py prospectus.pdf --out out --engine pymupdf
"""
from __future__ import annotations

import argparse
import statistics
from collections import Counter
from pathlib import Path

from chunker import ChunkConfig, chunk_sections
from ingest import ingest
from schema import load_elements, save_jsonl, save_sections
from splitter import build_sections


def write_preview(chunks, path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(f"## {c.chunk_id} | {c.content_type} | p.{c.page_start}-{c.page_end} | {c.n_tokens} tok\n")
            f.write(f"*{' > '.join(c.section_path)}*\n\n{c.text}\n\n---\n\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?")
    ap.add_argument("--out", default="out")
    ap.add_argument("--engine", choices=["docling", "pymupdf", "gemini"], default="docling")
    ap.add_argument("--ocr", action="store_true")
    ap.add_argument("--title", default="University Prospectus")
    ap.add_argument("--max-tokens", type=int, default=350)
    ap.add_argument("--min-section-chars", type=int, default=0)
    ap.add_argument("--pages", default=None, help="docling only, e.g. 1-15")
    ap.add_argument("--skip-ingest", action="store_true", help="reuse out/elements.json")
    ap.add_argument("--model", default=None, help="gemini model id (see --list-models)")
    ap.add_argument("--delay", type=float, default=6.0, help="gemini: seconds between pages")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--images", action="store_true", help="docling: also extract pictures (slower)")
    a = ap.parse_args()
    if a.list_models:
        from gemini_ocr import list_models
        list_models()
        return
    if not a.pdf and not a.skip_ingest:
        ap.error("pdf is required (unless --skip-ingest)")

    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    if a.skip_ingest:
        elements = load_elements(out / "elements.json")
    else:
        pages = tuple(int(x) for x in a.pages.split("-")) if a.pages else None
        elements = ingest(a.pdf, out, engine=a.engine, ocr=a.ocr, pages=pages, images=a.images, model=a.model, delay=a.delay)
    print(f"[ingest]  {len(elements)} elements:", dict(Counter(e.type for e in elements)))

    sections = build_sections(elements, min_section_chars=a.min_section_chars)
    save_sections(sections, out / "sections.json")
    print(f"[split]   {len(sections)} sections")

    cfg = ChunkConfig(doc_title=a.title, max_tokens=a.max_tokens)
    chunks = chunk_sections(sections, cfg)
    save_jsonl(chunks, out / "chunks.jsonl")
    write_preview(chunks, out / "chunks_preview.md")

    toks = [c.n_tokens for c in chunks]
    print(f"[chunk]   {len(chunks)} chunks | by type: {dict(Counter(c.content_type for c in chunks))}")
    if toks:
        print(f"          tokens min/median/max = {min(toks)}/{int(statistics.median(toks))}/{max(toks)}")
    print(f"Outputs in {out}/  -> open chunks_preview.md and read it like a student would.")


if __name__ == "__main__":
    main()