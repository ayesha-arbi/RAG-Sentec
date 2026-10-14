"""Shared data structures + JSON helpers for the ingest -> split -> chunk pipeline."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable


@dataclass
class Element:
    """One layout element extracted from the PDF, in reading order."""
    type: str                       # heading | paragraph | list_item | table | picture | caption | footnote
    page: int
    text: str = ""
    level: int = 0                  # heading level (1 = top)
    header: list[str] | None = None  # tables only
    rows: list[list[str]] | None = None
    caption: str = ""
    image_path: str | None = None
    description: str = ""           # pictures: filled later by a (free) VLM
    page_end: int = 0               # tables stitched across pages


@dataclass
class Section:
    """A heading-delimited block of the document. Also serves as the 'parent' for small-to-big retrieval."""
    section_id: str
    path: list[str]                 # breadcrumb, e.g. ["Faculty of Engineering", "Dept of CS", "BS Software Engineering"]
    elements: list[Element] = field(default_factory=list)
    page_start: int = 0
    page_end: int = 0
    text: str = ""                  # full rendered markdown of the section


@dataclass
class Chunk:
    chunk_id: str
    section_id: str                 # parent section (for small-to-big retrieval)
    content_type: str               # text | table | image
    text: str                       # what gets shown to the LLM
    embed_text: str                 # what gets embedded (breadcrumb prefix + body)
    section_path: list[str]
    page_start: int
    page_end: int
    n_tokens: int
    extra: dict[str, Any] = field(default_factory=dict)


def save_json(obj: Any, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def save_jsonl(items: Iterable[Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(asdict(it) if hasattr(it, "__dataclass_fields__") else it, ensure_ascii=False) + "\n")


def save_elements(elements: list[Element], path: str | Path) -> None:
    save_json([asdict(e) for e in elements], path)


def load_elements(path: str | Path) -> list[Element]:
    return [Element(**d) for d in json.loads(Path(path).read_text(encoding="utf-8"))]


def save_sections(sections: list[Section], path: str | Path) -> None:
    save_json([asdict(s) for s in sections], path)


def load_sections(path: str | Path) -> list[Section]:
    out = []
    for d in json.loads(Path(path).read_text(encoding="utf-8")):
        d["elements"] = [Element(**e) for e in d["elements"]]
        out.append(Section(**d))
    return out