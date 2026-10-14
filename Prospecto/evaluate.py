"""Evaluate the prospectus bot on a test set (single- and multi-turn).

    python evaluate.py questions.csv --out out_g --limit 20          # quick check
    python evaluate.py questions.csv --out out_g --fresh             # full run (saves after every row, resumable)
    python evaluate.py questions.csv --out out_g --fresh --rewrite   # A/B: LLM query rewriting
    python evaluate.py questions.csv --out out_g --retrieval-only    # retrieval metrics only, no answers / judge

CSV columns used (extra ones ignored): test_id, category, difficulty, conversation_id, turn_number, user_question,
expected_behavior, expected_answer, supporting_section, supporting_evidence, answerability, failure_mode_tested,
evaluation_criteria.  A plain .txt (one question per line) also works.

Metrics
  * pass / partial / fail  - LLM judge using expected_behavior + expected_answer + evaluation_criteria
  * section hit@k          - is the supporting_section (clause number, page or title) among the top-k retrieved chunks
  * evidence coverage      - share of supporting_evidence words that appear in the context sent to the LLM
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from answer import answer
from llm import generate
from retrieval import Retriever, tokenize

KS = (1, 3, 5, 8)
QCOLS = ("user_question", "question", "q", "query", "prompt")

JUDGE = """You are grading a university-prospectus chatbot for students.

Student message: {q}
Answerability: {answerability}    Failure mode being tested: {failure_mode}
Expected behavior: {behavior}
Expected answer: {gold}
Supporting evidence from the prospectus: {evidence}
Grading criteria: {criteria}

Bot answer:
{pred}

Grade the bot answer. "pass" = it does what the expected behavior and criteria ask AND its facts/numbers agree with the
expected answer (extra correct detail is fine). "partial" = right direction but misses or blurs a key fact/condition.
"fail" = wrong or invented facts, wrong behavior (e.g. guessed instead of asking, answered an unanswerable question,
refused an answerable one), or off-topic.
Reply with JSON only: {{"verdict": "pass" | "partial" | "fail", "reason": "<max 15 words>"}}"""


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _s(v) -> str:
    return "" if v is None else str(v).strip()


def load_cases(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix == ".txt":
        rows = [{"user_question": l.strip()} for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    elif p.suffix == ".csv":
        raw = list(csv.reader(p.open(encoding="utf-8-sig", newline="")))
        head = [c.strip().lower() for c in raw[0]] if raw else []
        if any(c in QCOLS for c in head):
            rows = [dict(zip(head, r)) for r in raw[1:]]
        else:                                                   # no header row: first column is the question
            rows = [{"user_question": r[0]} for r in raw if r and r[0].strip()]
    elif p.suffix == ".jsonl":
        rows = [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]
    else:
        rows = json.loads(p.read_text(encoding="utf-8"))

    cases, seen = [], defaultdict(int)
    for i, r in enumerate(rows):
        r = {str(k).strip().lower(): _s(v) for k, v in r.items()}
        q = next((r[c] for c in QCOLS if r.get(c)), "")
        if not q:
            continue
        m = re.search(r"\d+", r.get("turn_number", ""))
        cid = r.get("test_id") or f"q{i + 1:03d}"
        seen[cid] += 1
        cases.append({
            "_i": i, "id": cid if seen[cid] == 1 else f"{cid}#{seen[cid]}",
            "cid": r.get("conversation_id") or cid, "turn": int(m.group()) if m else 1, "question": q,
            "category": r.get("category", ""), "difficulty": r.get("difficulty", ""),
            "behavior": r.get("expected_behavior", ""), "gold": r.get("expected_answer", ""),
            "section": r.get("supporting_section", ""), "evidence": r.get("supporting_evidence", ""),
            "answerability": r.get("answerability", ""), "failure_mode": r.get("failure_mode_tested", ""),
            "criteria": r.get("evaluation_criteria", ""),
        })
    first: dict[str, int] = {}
    for c in cases:
        first.setdefault(c["cid"], c["_i"])
    cases.sort(key=lambda c: (first[c["cid"]], c["turn"], c["_i"]))      # conversations in order, turns in order
    return cases


# --------------------------------------------------------------------------- #
# Retrieval metrics
# --------------------------------------------------------------------------- #
_ID = re.compile(r"\d+(?:\.\d+)+(?:\s*\([ivxlc]+\))?", re.I)
_PG = re.compile(r"(?:\bpp?\.|\bpages?)\s*(\d+)(?:\s*[-–]\s*(\d+))?", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def parse_section(text: str, page_offset: int = 0):
    ids = [re.sub(r"\s+", "", m) for m in _ID.findall(text)]
    pages = set()
    for a, b in _PG.findall(text):
        lo, hi = int(a), int(b or a)
        pages.update(range(lo + page_offset, hi + page_offset + 1))
    return ids, pages


def section_hit(h: dict, ids: list[str], pages: set[int], text: str) -> bool:
    path = " > ".join(h["section_path"]).replace(" (", "(")
    for i in ids:                                    # clause number, e.g. 6.9 must not match 6.91 or 6.9.1
        if re.search(rf"(?<![\d.]){re.escape(i)}(?!\d|\.\d)", path):
            return True
    if pages and any(h["page_start"] <= p <= h["page_end"] for p in pages):
        return True
    if text and not ids and not pages:               # plain title, e.g. "Class Attendance"
        t = _norm(text)
        return bool(t) and (t in _norm(path) or any(len(_norm(e)) > 6 and _norm(e) in t for e in h["section_path"]))
    return False


def coverage(evidence: str, ctx: str):
    toks = {t for t in tokenize(evidence) if len(t) > 2 or t.isdigit()}
    if not toks:
        return None
    return len(toks & set(tokenize(ctx))) / len(toks)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "n/a"


def breakdown(results: list[dict], field: str) -> None:
    g: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in results:
        if "verdict" in r:
            s = g[r.get(field) or "(none)"]
            s[0] += r["verdict"] == "pass"
            s[1] += r["verdict"] == "partial"
            s[2] += 1
    if len(g) > 1:
        print(f"\nby {field} (worst first):")
        for k, (p, pa, n) in sorted(g.items(), key=lambda kv: kv[1][0] / kv[1][2]):
            print(f"  {k[:40]:40} pass {pct(p, n):>11}   partial {pa}")


def fmt(r: dict) -> str:
    hit = r.get("hit")
    ret = f"section@{KS[-1]}: {'yes' if hit[str(KS[-1])] else 'NO'}" if hit else "section: n/a"
    ev = f"{r['ev_cov']:.0%}" if r.get("ev_cov") is not None else "n/a"
    lines = [f"### [{r.get('verdict', '-').upper()}] {r['id']} · {r['category']} · {r['difficulty']} · "
             f"conv {r['cid']} turn {r['turn']}", f"**Q:** {r['question']}"]
    if r.get("standalone") and r["standalone"] != r["question"]:
        lines.append(f"*(searched as: {r['standalone']})*")
    lines += [f"**Expected ({r['answerability'] or '?'}):** {r['behavior']} | {r['gold']}",
              f"**Bot:** {r.get('pred') or '(ERROR: ' + r.get('error', '?') + ')'}",
              f"**Judge:** {r.get('reason', '')}",
              f"*{ret} | evidence coverage: {ev} | top: {' || '.join(r.get('top_sections', []))}*", "", "---", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("qa")
    ap.add_argument("--out", default="out_g")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--rewrite", action="store_true", help="LLM query rewriting (1 extra call per question)")
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--no-judge", action="store_true", help="generate answers but skip the LLM judge")
    ap.add_argument("--page-offset", type=int, default=0, help="added to pages found in supporting_section")
    ap.add_argument("--fresh", action="store_true", help="ignore saved results and start over")
    a = ap.parse_args()

    cases = load_cases(a.qa)
    if a.limit:
        cases = cases[:a.limit]
    print(f"[eval] {len(cases)} test rows, {len({c['cid'] for c in cases})} conversations")
    rt = Retriever(a.out)

    res_f = Path(a.out, "eval_results.jsonl")
    store: dict[str, dict] = {}                          # test id -> record, saved after EVERY row
    if res_f.exists() and not a.fresh:
        for l in res_f.read_text(encoding="utf-8").splitlines():
            if l.strip():
                d = json.loads(l)
                if d.get("id"):
                    store[d["id"]] = d
        print(f"[resume] {sum('pred' in d for d in store.values())} answered rows loaded from {res_f}")

    conv: dict[str, list[tuple[str, str]]] = defaultdict(list)
    results: list[dict] = []

    for n, c in enumerate(cases, 1):
        hist = conv[c["cid"]][-3:]
        prev = store.get(c["id"])
        if prev and "pred" in prev and not a.retrieval_only:            # answered in an earlier run
            rec, called = prev, False
        else:
            called = True
            rec = {k: c[k] for k in ("id", "cid", "turn", "category", "difficulty", "answerability", "failure_mode",
                                      "question", "behavior", "gold", "criteria")}
            try:
                r = answer(c["question"], rt, a.k, a.rewrite, hist, respond=not a.retrieval_only)
                hits = r["hits"]
                rec["standalone"] = r["standalone"]
                rec["top_sections"] = [" > ".join(h["section_path"])[-80:] for h in hits[:3]]
                rec["retrieved_pages"] = [f"{h['page_start']}-{h['page_end']}" for h in hits]
                if c["section"]:
                    ids, pages = parse_section(c["section"], a.page_offset)
                    rec["hit"] = {str(k): any(section_hit(h, ids, pages, c["section"]) for h in hits[:k]) for k in KS}
                if c["evidence"]:
                    rec["ev_cov"] = coverage(c["evidence"], r["context"])
                if not a.retrieval_only:
                    rec["pred"] = r["answer"]
                    if not a.no_judge and (c["gold"] or c["behavior"]):
                        try:
                            j = generate(JUDGE.format(q=c["question"], answerability=c["answerability"],
                                                      failure_mode=c["failure_mode"], behavior=c["behavior"],
                                                      gold=c["gold"], evidence=c["evidence"][:1200],
                                                      criteria=c["criteria"], pred=r["answer"]))
                            v = json.loads(re.search(r"\{.*\}", j, re.S).group(0))
                            verdict = str(v.get("verdict", "")).lower()
                            rec["verdict"] = verdict if verdict in ("pass", "partial", "fail") else "fail"
                            rec["reason"] = str(v.get("reason", ""))[:160]
                        except Exception as e:
                            rec["judge_error"] = str(e)[:100]
            except Exception as e:                       # no "pred" -> retried on the next run
                rec["error"] = str(e)[:200]
                print(f"   !! failed: {rec['error']}")
        store[c["id"]] = rec
        res_f.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in store.values()), encoding="utf-8")
        results.append(rec)
        # earlier turns feed the follow-ups: bot's own answers normally, gold answers when only testing retrieval
        said = c["gold"] if a.retrieval_only else rec.get("pred", "")
        if said:
            conv[c["cid"]].append((c["question"], said))
        tag = rec.get("verdict", "ERR" if "error" in rec else "-").upper()[:4]
        print(f"[{n}/{len(cases)}] {tag:4} {c['cid']}/t{c['turn']}  {c['question'][:70]}")
        if called and not a.retrieval_only:
            time.sleep(a.delay)

    # ---------------- summary ----------------
    print("\n=== RESULTS ===")
    judged = [r for r in results if "verdict" in r]
    if judged:
        p = sum(r["verdict"] == "pass" for r in judged)
        pa = sum(r["verdict"] == "partial" for r in judged)
        print(f"judge: pass {pct(p, len(judged))}   partial {pa}   fail {len(judged) - p - pa}")
        for f in ("category", "difficulty", "answerability", "failure_mode"):
            breakdown(results, f)
    gh = [r for r in results if r.get("hit")]
    if gh:
        print("\nretrieval, supporting_section in top-k:  " +
              "  ".join(f"@{k}={sum(r['hit'][str(k)] for r in gh) / len(gh):.0%}" for k in KS) + f"   (n={len(gh)})")
    cv = [r["ev_cov"] for r in results if r.get("ev_cov") is not None]
    if cv:
        print(f"evidence coverage in LLM context: mean {sum(cv) / len(cv):.0%}, "
              f">=80% in {pct(sum(x >= 0.8 for x in cv), len(cv))} of rows")
    errs = sum("error" in r for r in results)
    if errs:
        print(f"{errs} rows errored (marked ERR); rerun the same command to retry them")

    if not a.retrieval_only:
        Path(a.out, "eval_report.md").write_text("\n".join(fmt(r) for r in results), encoding="utf-8")
        bad = [r for r in results if r.get("verdict") in ("fail", "partial") or "error" in r]
        Path(a.out, "eval_failures.md").write_text("\n".join(fmt(r) for r in bad), encoding="utf-8")
        print(f"\nread first: {a.out}/eval_failures.md  ({len(bad)} rows)   all rows: {a.out}/eval_report.md")


if __name__ == "__main__":
    main()