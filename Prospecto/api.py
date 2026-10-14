"""FastAPI server for the Prospecto RAG pipeline.

    uvicorn api:app --reload --port 8000

Endpoints:
    POST /chat          - ask a question (with optional session for multi-turn)
    DELETE /chat/{sid}  - clear a conversation session
    GET  /health        - liveness check
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
load_dotenv()   # picks up GEMINI_API_KEY from .env if present

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from answer import answer
from retrieval import Retriever

# --------------------------------------------------------------------------- #
# App lifecycle — load the retriever ONCE at startup (embeddings live in RAM)
# --------------------------------------------------------------------------- #
retriever: Retriever | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global retriever
    print("[startup] loading index ...")
    retriever = Retriever(out_dir="out_g")
    print("[startup] index ready - OK")
    yield
    # nothing to clean up


app = FastAPI(
    title="Prospecto API",
    description="University prospectus RAG chatbot — powered by Prospec",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow all origins during development; tighten this for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# In-memory conversation store  { session_id -> [(user_msg, bot_reply), ...] }
# --------------------------------------------------------------------------- #
_sessions: dict[str, list[tuple[str, str]]] = defaultdict(list)
MAX_HISTORY = 6   # keep last 6 turns per session (matches answer.py's del hist[:-3])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None   # omit to start a new session
    rewrite: bool = False              # enable LLM query rewriting (costs 1 extra call)
    k: int = 8                         # number of chunks to retrieve


class SourceChunk(BaseModel):
    section: str
    page_start: int
    page_end: int
    score: float
    text: str = ""                     # chunk excerpt for frontend source viewer/accordion


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[SourceChunk]
    standalone_question: str           # what was actually searched (useful for debugging)


class HealthResponse(BaseModel):
    status: str
    chunks_loaded: int


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/health", response_model=HealthResponse, tags=["system"])
def health():
    """Liveness check — also tells the frontend how many chunks are indexed."""
    if retriever is None:
        raise HTTPException(503, "Index not loaded yet")
    return HealthResponse(status="ok", chunks_loaded=len(retriever.chunks))


@app.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(req: ChatRequest):
    """
    Send a question and get an answer grounded in the prospectus.

    - **session_id**: pass the value returned in the previous response to
      continue a multi-turn conversation. Omit (or pass null) to start fresh.
    - **rewrite**: set true to let the LLM expand slang into formal queries
      (e.g. "punishment for cheating" → "unfair means / malpractice").
    - **k**: how many chunks to retrieve (default 8).
    """
    if retriever is None:
        raise HTTPException(503, "Index not loaded yet — try again in a moment")

    q = req.question.strip()
    if not q:
        raise HTTPException(400, "Question cannot be empty.")

    # Create or reuse session
    sid = req.session_id or str(uuid.uuid4())
    history = _sessions[sid][-MAX_HISTORY:]

    try:
        result = answer(
            q=q,
            rt=retriever,
            k=req.k,
            rewrite=req.rewrite,
            history=history,
        )
    except Exception as exc:
        raise HTTPException(500, detail=str(exc))

    # Persist turn
    _sessions[sid].append((q, result["answer"]))
    if len(_sessions[sid]) > MAX_HISTORY:
        _sessions[sid] = _sessions[sid][-MAX_HISTORY:]

    sources = [
        SourceChunk(
            section=" > ".join(h["section_path"]),
            page_start=h["page_start"],
            page_end=h["page_end"],
            score=round(h["score"], 4),
            text=h.get("text", ""),
        )
        for h in result["hits"]
    ]

    return ChatResponse(
        session_id=sid,
        answer=result["answer"],
        sources=sources,
        standalone_question=result["standalone"],
    )


@app.delete("/chat/{session_id}", tags=["chat"])
def clear_session(session_id: str):
    """Clear the conversation history for a session (i.e. start over)."""
    _sessions.pop(session_id, None)
    return {"cleared": session_id}
