"""Gemini REST helpers: embeddings + generation. Stdlib + numpy only (same style as gemini_ocr.py)."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import numpy as np

API = "https://generativelanguage.googleapis.com/v1beta"
EMBED_MODEL = os.environ.get("EMBED_MODEL", "gemini-embedding-001")
GEN_MODEL = os.environ.get("GEN_MODEL", "gemini-flash-lite-latest")   # same model your OCR run used; fast, no long "thinking"
EMBED_DIM = 768


def _key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            'Gemini API key not found. Set GEMINI_API_KEY in your environment or in a .env file.'
        )
    return key


def _post(url: str, body: dict, retries: int = 7) -> dict:
    data = json.dumps(body).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": _key()})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                out = json.loads(r.read().decode("utf-8"))
            print(f"   [api] {url.rsplit('/', 1)[-1].split('?')[0]} ok in {time.time() - t0:.1f}s")
            return out
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")
            if e.code in (429, 500, 503) and attempt < retries - 1:
                wait = min(30, 3 * 2 ** attempt)
                print(f"   [api] HTTP {e.code} after {time.time() - t0:.1f}s, retrying in {wait}s ... {msg[:160]!r}")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Gemini HTTP {e.code}: {msg[:500]}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:      # was silent before
            print(f"   [api] network error after {time.time() - t0:.1f}s: {e!r} (attempt {attempt + 1}/{retries})")
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("Gemini: retries exhausted - check your internet / VPN / proxy and the model name")


def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> np.ndarray:
    """task: RETRIEVAL_DOCUMENT | RETRIEVAL_QUERY. Returns L2-normalised float32 (n, EMBED_DIM)."""
    model = f"models/{EMBED_MODEL}"
    body = {"requests": [{"model": model, "content": {"parts": [{"text": t[:8000]}]},
                          "taskType": task, "outputDimensionality": EMBED_DIM} for t in texts]}
    data = _post(f"{API}/{model}:batchEmbedContents", body)
    v = np.array([e["values"] for e in data["embeddings"]], dtype=np.float32)
    return v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-9, None)   # required for <3072 dims


def generate(prompt: str, system: str = "", temperature: float = 0.0, model: str | None = None) -> str:
    model = model or GEN_MODEL
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    data = _post(f"{API}/models/{model}:generateContent", body)
    cands = data.get("candidates") or []
    if not cands:
        return ""
    parts = cands[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()