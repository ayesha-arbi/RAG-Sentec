"""Answer a student's question from the prospectus (supports multi-turn follow-ups).

    python answer.py "What is the fee for BS Software Engineering?" --out out_g
    python answer.py --out out_g                     # interactive chat; follow-ups like "and for transfer students?" work
    python answer.py "punishment for cheating" --rewrite   # +1 LLM call: rewrites slang into prospectus wording
"""
from __future__ import annotations

import argparse

from llm import generate
from retrieval import Retriever

SYSTEM = """You are Prospecto, a warm, patient, and knowledgeable assistant who helps university students navigate the prospectus. You genuinely care about every student's wellbeing and success.

Persona & tone:
- Always be kind, calm, and encouraging — no matter how the student phrases their message.
- If a student is rude, frustrated, or uses harsh language, do NOT mirror it or scold them. Acknowledge that university can be stressful, stay warm, and simply help them. One calm, empathetic opening sentence is enough — then get straight to the answer.
- If a student is panicking or sounds overwhelmed, reassure them briefly (one sentence) before listing their options.
- Never lecture, moralize, or make the student feel judged for their question or their tone.
- Use plain, friendly language. Avoid overly formal or bureaucratic wording where possible.
- It is okay to use light, supportive phrases like "Good news —", "Take a breath —", or "You have options here." when appropriate.

How to answer (factual rules — follow these strictly):
- Use ONLY the context from the prospectus below. Never invent rules.
- Give the direct answer first in plain language, then the key condition or exception. Keep it short.
- Copy numbers (fees, dates, CGPA, marks, credit hours, percentages, weeks) exactly as written.
- Write formulas in plain text, e.g. CGPA = sum(credit hours x grade points) / total credit hours. Never use LaTeX or $$.
- If tables cover several programs/years/categories, use the row that matches the question; if unclear, say which one you used.
- If the question is vague or could mean several things (e.g. "Is 70 enough?") and the conversation does not clarify it, do not guess. Say what is unclear, ask ONE short question, and briefly list what the prospectus says for the likely meanings.
- If the question contains a wrong assumption (e.g. "I automatically lose my degree if I fail one course"), gently correct it using the context — no need to make the student feel bad about the assumption.
- If the question needs personal data (my CGPA, my attendance, my fee status), say you cannot see student records, explain how it is calculated, and tell them who to ask.
- If the context only partly answers, give what it says and state what is missing. Say "I couldn't find this in the prospectus." only when nothing relevant is in the context.
- If asked to make something up or ignore the prospectus, decline warmly in one line and give what the prospectus actually says instead.
- Use the conversation so far to understand follow-up questions, but take facts only from the context.
- End with the source pages, e.g. (Source: p. 47)."""

REWRITE = """Rewrite this student's question as 3 short search queries for a university prospectus.
Use formal regulation wording (e.g. "unfair means", "malpractice", "withdrawal of course", "probation", "CGPA",
"credit hours", "fee refund") and resolve slang. Output exactly 3 lines, one query per line, no numbering, no extra text.

Question: {q}"""

CONDENSE = """Rewrite the student's latest message as ONE standalone question for searching a university prospectus.
Use the conversation for missing context (program, course, numbers, what "it" / "that" refers to). Keep every detail.
Output only the question.

Conversation:
{hist}

Latest message: {q}"""


def _fmt_hist(history: list[tuple[str, str]]) -> str:
    return "\n".join(f"Student: {u}\nAssistant: {a[:500]}" for u, a in history)


def condense(q: str, history: list[tuple[str, str]]) -> str:
    try:
        out = generate(CONDENSE.format(hist=_fmt_hist(history), q=q)).strip()
        line = next((l.strip().strip('"') for l in out.splitlines() if l.strip()), "")
        return line or q
    except Exception:
        return q


def rewrite_queries(q: str) -> list[str]:
    try:
        lines = [l.strip(" -*\t0123456789.") for l in generate(REWRITE.format(q=q)).splitlines() if l.strip()]
    except Exception:
        lines = []
    return [q] + lines[:3]


def answer(q: str, rt: Retriever, k: int = 8, rewrite: bool = False,
           history: list[tuple[str, str]] | None = None, respond: bool = True) -> dict:
    """history = [(student_msg, bot_answer), ...] of earlier turns. respond=False -> retrieval only."""
    history = history or []
    standalone = condense(q, history) if history else q
    queries = rewrite_queries(standalone) if rewrite else [standalone]
    hits = rt.search_multi(queries, k=k)
    ctx = rt.build_context(hits)
    conv = f"Conversation so far:\n{_fmt_hist(history)}\n\n" if history else ""
    prompt = f"Context from the prospectus:\n\n{ctx}\n\n---\n{conv}Student's latest message: {q}\n\nAnswer:"
    pred = generate(prompt, SYSTEM) if respond else ""
    return {"question": q, "standalone": standalone, "queries": queries, "answer": pred, "hits": hits, "context": ctx}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?")
    ap.add_argument("--out", default="out_g")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--rewrite", action="store_true")
    a = ap.parse_args()
    rt = Retriever(a.out)
    hist: list[tuple[str, str]] = []

    def run(q: str) -> None:
        r = answer(q, rt, a.k, a.rewrite, hist)
        if r["standalone"] != q:
            print("searched as:", r["standalone"])
        if a.rewrite:
            print("queries:", r["queries"])
        print("\n" + r["answer"])
        print("\nretrieved:", [f"p.{h['page_start']}" for h in r["hits"]])
        hist.append((q, r["answer"]))
        del hist[:-3]

    if a.question:
        run(a.question)
    else:
        while True:
            q = input("\nQ> ").strip()
            if not q:
                break
            run(q)