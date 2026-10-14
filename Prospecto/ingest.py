"""Stage 1 - PDF ingester.

PDF  ->  ordered list[Element]  (headings, paragraphs, list items, tables, pictures).

Two free engines:
  * docling  (default) - layout-aware: reading order, table structure, optional OCR.
  * pymupdf  (fallback) - fast & light; font-size heading detection + find_tables().
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from schema import Element, save_elements
from utils import clean_inline, strip_bullet, is_bullet_line


# --------------------------------------------------------------------------- #
# Docling
# --------------------------------------------------------------------------- #
def ingest_docling(pdf_path: str | Path, out_dir: str | Path, ocr: bool = False,
                   image_scale: float = 1.0, min_image_px: int = 150, pages: tuple[int, int] | None = None,
                   images: bool = False, fast_tables: bool = True) -> list[Element]:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode, EasyOcrOptions
    from docling_core.types.doc import TableItem, PictureItem

    out = Path(out_dir)
    img_dir = out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    opts = PdfPipelineOptions()
    if ocr:
        opts.ocr_options = EasyOcrOptions(force_full_page_ocr=True, lang=["en"])   # scanned pages: OCR the whole page
    opts.do_ocr = ocr                       # turn on for scanned pages (free EasyOCR/RapidOCR models)
    opts.do_table_structure = True
    opts.table_structure_options.do_cell_matching = not fast_tables
    if fast_tables:
        opts.table_structure_options.mode = TableFormerMode.FAST
    opts.generate_picture_images = images
    opts.images_scale = image_scale

    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    kw = {"page_range": pages} if pages else {}
    doc = converter.convert(str(pdf_path), **kw).document
    (out / "prospectus.docling.md").write_text(doc.export_to_markdown(), encoding="utf-8")  # eyeball this!

    elements: list[Element] = []
    n_pic = 0
    for item, _ in doc.iterate_items():
        label = getattr(item.label, "value", str(item.label))
        page = item.prov[0].page_no if getattr(item, "prov", None) else (elements[-1].page if elements else 1)

        if isinstance(item, TableItem):
            try:
                df = item.export_to_dataframe(doc)
            except TypeError:
                df = item.export_to_dataframe()
            if df.empty and df.shape[1] == 0:
                continue
            has_header = list(df.columns) != list(range(df.shape[1]))   # int columns = no header detected
            header = [clean_inline(str(c)) for c in df.columns] if has_header else None
            rows = [[clean_inline(str(c)) for c in r] for r in df.fillna("").values.tolist()]
            try:
                cap = clean_inline(item.caption_text(doc))
            except Exception:
                cap = ""
            elements.append(Element("table", page, header=header, rows=rows, caption=cap))

        elif isinstance(item, PictureItem):
            img_path, keep = None, True
            try:
                img = item.get_image(doc)
                if img is not None:
                    if img.width < min_image_px or img.height < min_image_px:
                        keep = False                       # logos / bullets / decorations
                    else:
                        n_pic += 1
                        img_path = str(img_dir / f"p{page:03d}_{n_pic:03d}.png")
                        img.save(img_path)
            except Exception:
                pass
            try:
                cap = clean_inline(item.caption_text(doc))
            except Exception:
                cap = ""
            if keep and (img_path or cap):
                elements.append(Element("picture", page, caption=cap, image_path=img_path))

        else:
            text = clean_inline(getattr(item, "text", "") or "")
            if not text or label in ("page_header", "page_footer"):
                continue
            if label == "title":
                elements.append(Element("heading", page, text, level=1))
            elif label == "section_header":
                elements.append(Element("heading", page, text, level=max(1, int(getattr(item, "level", 1) or 1))))
            elif label == "list_item":
                elements.append(Element("list_item", page, strip_bullet(text)))
            elif label == "caption":
                elements.append(Element("caption", page, text))
            elif label == "footnote":
                elements.append(Element("footnote", page, text))
            else:
                elements.append(Element("paragraph", page, text))

    save_elements(elements, out / "elements.json")
    return elements


# --------------------------------------------------------------------------- #
# PyMuPDF fallback
# --------------------------------------------------------------------------- #
def _norm_edge(t: str) -> str:
    return re.sub(r"\d+", "#", t.lower()).strip()


def ingest_pymupdf(pdf_path: str | Path, out_dir: str | Path) -> list[Element]:
    import fitz  # PyMuPDF

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdf = fitz.open(str(pdf_path))

    # ---- pass 1: collect blocks per page ----
    pages = []
    edge_count: Counter = Counter()
    for pno, page in enumerate(pdf, start=1):
        H = page.rect.height
        tabs = []
        try:
            tabs = list(page.find_tables().tables)
        except Exception:
            pass
        blocks = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            x0, y0, x1, y1 = b["bbox"]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if any(t.bbox[0] <= cx <= t.bbox[2] and t.bbox[1] <= cy <= t.bbox[3] for t in tabs):
                continue                                         # text belongs to a table
            lines = ["".join(s["text"] for s in l["spans"]).strip() for l in b["lines"]]
            lines = [l for l in lines if l]
            if not lines:
                continue
            sizes = Counter()
            for l in b["lines"]:
                for s in l["spans"]:
                    sizes[round(s["size"], 1)] += len(s["text"].strip())
            size = sizes.most_common(1)[0][0] if sizes else 0
            edge = y1 < 0.08 * H or y0 > 0.92 * H
            text = "\n".join(lines)
            if edge:
                edge_count[_norm_edge(text)] += 1
            blocks.append({"lines": lines, "text": text, "size": size, "y0": y0, "edge": edge})
        pages.append((pno, blocks, tabs))

    n_pages = max(len(pages), 1)
    repeated = {k for k, v in edge_count.items() if v >= max(3, 0.3 * n_pages)}   # running headers/footers

    body_sizes: Counter = Counter()
    for _, blocks, _ in pages:
        for b in blocks:
            if not (b["edge"] and _norm_edge(b["text"]) in repeated):
                body_sizes[b["size"]] += len(b["text"])
    body = body_sizes.most_common(1)[0][0] if body_sizes else 10
    big = sorted({s for s in body_sizes if s >= body * 1.12}, reverse=True)
    level_of = {s: min(i + 1, 4) for i, s in enumerate(big)}

    # ---- pass 2: emit elements ----
    elements: list[Element] = []
    for pno, blocks, tabs in pages:
        tabs = sorted(tabs, key=lambda t: t.bbox[1])
        ti = 0

        def emit_table(t):
            rows = [[clean_inline(c or "") for c in r] for r in t.extract()]
            rows = [r for r in rows if any(r)]
            if rows:
                elements.append(Element("table", pno, header=None, rows=rows))

        for b in blocks:
            if b["edge"] and _norm_edge(b["text"]) in repeated:
                continue
            while ti < len(tabs) and tabs[ti].bbox[1] <= b["y0"]:
                emit_table(tabs[ti]); ti += 1
            text = clean_inline(b["text"])
            if b["size"] in level_of and len(text) < 200:
                elements.append(Element("heading", pno, text, level=level_of[b["size"]]))
            elif any(is_bullet_line(l) for l in b["lines"]):
                intro, items = [], []
                for l in b["lines"]:
                    if is_bullet_line(l):
                        items.append([strip_bullet(l)])
                    elif items:
                        items[-1].append(l)
                    else:
                        intro.append(l)
                if intro:
                    elements.append(Element("paragraph", pno, clean_inline(" ".join(intro))))
                for it in items:
                    elements.append(Element("list_item", pno, clean_inline(" ".join(it))))
            else:
                elements.append(Element("paragraph", pno, text))
        while ti < len(tabs):
            emit_table(tabs[ti]); ti += 1

    save_elements(elements, out / "elements.json")
    return elements


def ingest(pdf_path, out_dir, engine: str = "docling", ocr: bool = False, pages=None, images: bool = False,
           model=None, delay: float = 6.0) -> list[Element]:
    if engine == "gemini":
        from gemini_ocr import ingest_gemini
        return ingest_gemini(pdf_path, out_dir, model=model, pages=pages, delay=delay)
    if engine == "docling":
        return ingest_docling(pdf_path, out_dir, ocr=ocr, pages=pages, images=images)
    return ingest_pymupdf(pdf_path, out_dir)