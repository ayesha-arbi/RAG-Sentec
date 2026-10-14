"""Stage 2 - Structure-aware text splitter.

list[Element] -> list[Section]   (one section per heading, with breadcrumb path)

Also: stitches tables that continue across pages, and lets you fix unreliable heading levels
with regex rules (very common in prospectuses where every heading comes out as level 1).
"""
from __future__ import annotations

import re

from schema import Element, Section
from utils import table_to_markdown

# (regex, level). First match wins. Edit these to match YOUR prospectus's heading vocabulary.
HEADING_RULES: list[tuple[str, int]] = [
    # Numbered clauses: level = depth of the number. Without this every "6.x" clause ended up nested under "6.1"
    # (see breadcrumbs like "6.1 ADMISSION IN FIRST SEMESTER > 6.9 WITHDRAWAL"), polluting every chunk's embedding.
    (r"^\d+\.\d+\.\d+", 3),             # 6.1.5   8.6.1   3.2.6
    (r"^\d+\.\d+\s*\([ivxIVX]+\)", 3),  # 5.1(i)  5.2(ii)
    (r"^\d+\.\d+\b", 2),                # 6.1     7.2     8.6
]


def apply_heading_rules(elements: list[Element], rules=HEADING_RULES) -> list[Element]:
    comp = [(re.compile(p, re.I), lvl) for p, lvl in rules]
    for e in elements:
        if e.type == "heading":
            for rx, lvl in comp:
                if rx.search(e.text):
                    e.level = lvl
                    break
    return elements


def _ncols(t: Element) -> int:
    if t.header:
        return len(t.header)
    return len(t.rows[0]) if t.rows else 0


def stitch_tables(elements: list[Element]) -> list[Element]:
    """Merge a table that continues on the next page; then promote first row to header if none was detected."""
    out: list[Element] = []
    for e in elements:
        prev = out[-1] if out else None
        if (e.type == "table" and prev is not None and prev.type == "table"
                and e.page == (prev.page_end or prev.page) + 1 and e.rows and prev.rows
                and _ncols(e) == _ncols(prev) and _ncols(e) > 0):
            prev_head = prev.header or prev.rows[0]
            if e.header is None or e.header == prev_head:
                rows = list(e.rows)
                if rows and rows[0] == prev_head:      # repeated header row on the new page
                    rows = rows[1:]
                prev.rows.extend(rows)
                prev.page_end = e.page
                continue
        out.append(e)
    for t in out:
        if t.type == "table" and t.header is None and t.rows:
            t.header, t.rows = t.rows[0], t.rows[1:]
    return out


def render_section(sec: Section) -> str:
    parts = []
    for e in sec.elements:
        if e.type == "heading":
            parts.append("#" * min(max(e.level, 1) + 1, 6) + " " + e.text)
        elif e.type == "list_item":
            parts.append("- " + e.text)
        elif e.type == "table":
            md = table_to_markdown(e.header, e.rows or [])
            parts.append((e.caption + "\n\n" if e.caption else "") + md)
        elif e.type == "picture":
            parts.append(f"[Image: {e.description or e.caption or 'no description'}]")
        else:
            parts.append(e.text)
    return "\n\n".join(parts)


def _chars(sec: Section) -> int:
    n = 0
    for e in sec.elements:
        n += len(e.text)
        if e.rows:
            n += sum(len(c) for r in e.rows for c in r)
    return n


def build_sections(elements: list[Element], min_section_chars: int = 0) -> list[Section]:
    """Group elements under their heading path. Sibling sections shorter than `min_section_chars`
    are folded into the previous sibling (their heading stays as an inline line)."""
    elements = stitch_tables(apply_heading_rules(elements))
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    cur: Section | None = None

    def new_section(path, page):
        nonlocal cur
        cur = Section(section_id=f"s{len(sections):04d}", path=list(path), page_start=page, page_end=page)
        sections.append(cur)

    for e in elements:
        if e.type == "heading":
            lvl = max(e.level, 1)
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            stack.append((lvl, e.text))
            new_section([t for _, t in stack], e.page)
        else:
            if cur is None:
                new_section(["Preamble"], e.page)
            cur.elements.append(e)
            cur.page_end = max(cur.page_end, e.page)

    sections = [s for s in sections if s.elements]

    if min_section_chars > 0:
        merged: list[Section] = []
        for s in sections:
            p = merged[-1] if merged else None
            if p and _chars(s) < min_section_chars and p.path[:-1] == s.path[:-1] and len(s.path) > 1:
                p.elements.append(Element("heading", s.page_start, s.path[-1], level=len(s.path)))
                p.elements.extend(s.elements)
                p.page_end = max(p.page_end, s.page_end)
            else:
                merged.append(s)
        sections = merged

    for i, s in enumerate(sections):
        s.section_id = f"s{i:04d}"
        s.text = render_section(s)
    return sections