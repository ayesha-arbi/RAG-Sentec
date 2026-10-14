"""Index build + hybrid retrieval (dense + BM25, fused with RRF) + parent-section context assembly.

    python retrieval.py build --out out_g      # embeds chunks (resumable), writes emb.npy
    python retrieval.py search "fee for BS CS" --out out_g
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from llm import embed
from schema import load_sections

_tok = re.compile(r"[a-z0-9]+")


def tokenize(t: str) -> list[str]:
    return _tok.findall(t.lower())


# --------------------------------------------------------------------------- #
# BM25 (tiny, no dependency)
# --------------------------------------------------------------------------- #
class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b, self.N = k1, b, len(docs)
        self.dl = np.array([len(d) for d in docs], dtype=np.float32)
        self.avg = float(self.dl.mean()) if self.N else 1.0
        self.post: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, d in enumerate(docs):
            for t, c in Counter(d).items():
                self.post[t].append((i, c))

    def scores(self, q: list[str]) -> np.ndarray:
        s = np.zeros(self.N, dtype=np.float32)
        for t in set(q):
            p = self.post.get(t)
            if not p:
                continue
            idf = math.log(1 + (self.N - len(p) + 0.5) / (len(p) + 0.5))
            for i, c in p:
                s[i] += idf * c * (self.k1 + 1) / (c + self.k1 * (1 - self.b + self.b * self.dl[i] / self.avg))
        return s


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build_index(out_dir: str = "out_g", min_tokens: int = 15, batch: int = 50) -> None:
    out = Path(out_dir)
    chunks = [json.loads(l) for l in (out / "chunks.jsonl").open(encoding="utf-8")]
    n0 = len(chunks)
    chunks = [c for c in chunks if c["content_type"] == "image" or c["n_tokens"] >= min_tokens]   # drop junk fragments
    print(f"[index] {len(chunks)} chunks kept ({n0 - len(chunks)} junk dropped)")

    cache_f = out / "emb_cache.pkl"
    cache: dict[str, np.ndarray] = pickle.loads(cache_f.read_bytes()) if cache_f.exists() else {}
    keys = [hashlib.sha1(c["embed_text"].encode("utf-8")).hexdigest() for c in chunks]
    todo: dict[str, str] = {k: c["embed_text"] for k, c in zip(keys, chunks) if k not in cache}
    items = list(todo.items())
    for i in range(0, len(items), batch):
        part = items[i:i + batch]
        vecs = embed([t for _, t in part], "RETRIEVAL_DOCUMENT")
        for (k, _), v in zip(part, vecs):
            cache[k] = v
        cache_f.write_bytes(pickle.dumps(cache))           # checkpoint: safe to Ctrl+C and resume
        print(f"[index] embedded {min(i + batch, len(items))}/{len(items)}")
        time.sleep(1.0)

    np.save(out / "emb.npy", np.stack([cache[k] for k in keys]))
    (out / "index_chunks.json").write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    print(f"[index] done -> {out}/emb.npy, index_chunks.json")


# --------------------------------------------------------------------------- #
# Retrieve
# --------------------------------------------------------------------------- #
class Retriever:
    def __init__(self, out_dir: str = "out_g"):
        out = Path(out_dir)
        self.out = out
        self.chunks = json.loads((out / "index_chunks.json").read_text(encoding="utf-8"))
        self.M = np.load(out / "emb.npy")
        self.bm25 = BM25([tokenize(c["embed_text"]) for c in self.chunks])
        self.sections = {s.section_id: s for s in load_sections(out / "sections.json")}
        self._qf = out / "query_cache.json"
        self._qc: dict[str, list[float]] = json.loads(self._qf.read_text("utf-8")) if self._qf.exists() else {}

    def _qvec(self, q: str) -> np.ndarray:
        if q not in self._qc:
            self._qc[q] = embed([q], "RETRIEVAL_QUERY")[0].tolist()
            self._qf.write_text(json.dumps(self._qc), encoding="utf-8")
        return np.array(self._qc[q], dtype=np.float32)

    def search(self, q: str, k: int = 6, **kw) -> list[dict]:
        return self.search_multi([q], k=k, **kw)

    def search_multi(self, queries: list[str], k: int = 6, pool: int = 30, w_dense: float = 1.0,
                     w_bm25: float = 1.0, rrf_k: int = 60) -> list[dict]:
        """Hybrid search; with several query variants (original + rewrites) all rankings are fused by RRF."""
        fused: dict[int, float] = defaultdict(float)
        for q in queries:
            dense = self.M @ self._qvec(q)
            lex = self.bm25.scores(tokenize(q))
            for r, i in enumerate(np.argsort(-dense)[:pool]):
                fused[int(i)] += w_dense / (rrf_k + r + 1)
            for r, i in enumerate(np.argsort(-lex)[:pool]):
                if lex[i] > 0:
                    fused[int(i)] += w_bm25 / (rrf_k + r + 1)
        top = sorted(fused, key=fused.get, reverse=True)[:k]
        return [dict(self.chunks[i], score=fused[i], idx=i) for i in top]

    def build_context(self, hits: list[dict], max_chars: int = 14000, section_max_chars: int = 6000) -> str:
        """Small-to-big: if a hit's parent section is short, send the whole section (once); else just the chunk."""
        seen: set[str] = set()
        blocks, used = [], 0
        for h in hits:
            sec = self.sections.get(h["section_id"])
            if sec and len(sec.text) <= section_max_chars:
                if sec.section_id in seen:
                    continue
                seen.add(sec.section_id)
                body, p0, p1 = sec.text, sec.page_start, sec.page_end
            else:
                body, p0, p1 = h["text"], h["page_start"], h["page_end"]
            pages = f"p.{p0}" if p0 == p1 else f"pp.{p0}-{p1}"
            block = f"[Source: {' > '.join(h['section_path'])} | {pages}]\n{body}"
            if used + len(block) > max_chars and blocks:
                break
            blocks.append(block)
            used += len(block)
        return "\n\n=====\n\n".join(blocks)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "search"])
    ap.add_argument("query", nargs="?")
    ap.add_argument("--out", default="out_g")
    a = ap.parse_args()
    if a.cmd == "build":
        build_index(a.out)
    else:
        for h in Retriever(a.out).search(a.query):
            print(f"{h['score']:.4f} p.{h['page_start']}-{h['page_end']} {' > '.join(h['section_path'])}\n   {h['text'][:160]!r}")