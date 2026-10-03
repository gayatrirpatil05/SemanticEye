"""SemanticEye end-to-end: Input -> Split -> Match -> AI signals -> Explain -> one report."""
import hashlib
import time

import ai_signals
import ingest
import plagiarism
import splitter
from config import ENGINE_VERSION
from textutil import tokens

FAIRNESS = ("Style signals can misfire on non-native English, formal academic writing and templated text. "
            "Treat results as evidence to review, never as proof.")


def _band(pct):
    return "low" if pct < 35 else ("mixed" if pct < 65 else "high")


def analyze(text=None, name=None, data=None, sources=None, use_library=True) -> dict:
    """sources: list of (name, text) pairs supplied with this request."""
    t0 = time.perf_counter()
    clean = ingest.prepare(text=text, name=name, data=data)
    sents = splitter.split_sentences(clean)
    if not sents:
        raise ingest.InputError("Text is too short to analyse. Add at least one full sentence.")

    indexes, labels = [], []
    req_sources = [(n, t) for n, t in (sources or []) if t and t.strip()]
    if req_sources:
        indexes.append(plagiarism.build_index(req_sources))
        labels += [n for n, _ in req_sources]
    lib = plagiarism.library() if use_library else None
    if lib and lib["docs"]:
        indexes.append(lib["index"])
    src_docs = len(req_sources) + (lib["docs"] if lib else 0)
    src_words = sum(ix.words for ix in indexes)

    ev = plagiarism.check_all(sents, indexes) if indexes else [None] * len(sents)
    rows, ai_score, parts, d = ai_signals.analyse(sents)

    out_sents, w_total, w_match, w_ai = [], 0, 0, 0
    for s, e, r in zip(sents, ev, rows):
        n = len(tokens(s))
        w_total += n
        matched = e is not None and e["kind"] != "clean"
        if matched:
            flag = "copied"; w_match += n
        elif r["flag"]:
            flag = "ai"; w_ai += n
        else:
            flag = "ok"
        out_sents.append({
            "text": s, "flag": flag, "ai_prob": round(r["ai"], 3),
            "similarity": round(e["similarity"], 3) if e else None,
            "match_type": e["kind"] if matched else None,
            "source": e["source"] if matched else None,
            "source_text": e["source_text"] if matched else None,
            "spans": e["spans"] if matched else [],
            "why": r["why"] if flag == "ai" else [],
        })
    w_ok = max(w_total - w_match - w_ai, 0)
    have_sources = bool(indexes)
    plag_pct = round(100.0 * w_match / w_total, 1) if have_sources and w_total else None
    ai_pct = round(100.0 * ai_score, 1)
    reliability = "good" if d["words"] >= 250 else ("fair" if d["words"] >= 100 else "low")

    if have_sources and plag_pct >= 15 and ai_pct >= 65:
        verdict = "matched_and_ai"
    elif have_sources and plag_pct >= 15:
        verdict = "matched"
    elif ai_pct >= 65:
        verdict = "ai_pattern"
    elif ai_pct >= 35 or (have_sources and plag_pct >= 5):
        verdict = "mixed"
    else:
        verdict = "original"

    h = hashlib.sha256()
    for part in (ENGINE_VERSION, clean, *[t for _, t in req_sources], lib["digest"] if lib else ""):
        h.update(hashlib.sha256(part.encode("utf-8", "ignore")).digest())
    return {
        "engine": ENGINE_VERSION,
        "report_id": h.hexdigest()[:16],
        "verdict": verdict,
        "plagiarism_pct": plag_pct,
        "ai_pct": ai_pct,
        "ai_band": _band(ai_pct),
        "reliability": reliability,
        "shares": {"original": round(100.0 * w_ok / max(w_total, 1), 1),
                   "ai_pattern": round(100.0 * w_ai / max(w_total, 1), 1),
                   "matched": round(100.0 * w_match / max(w_total, 1), 1)},
        "reasons": parts,
        "sentences": out_sents,
        "stats": {"words": w_total, "sentences": len(sents), "sources": src_docs, "source_words": src_words,
                  "library_docs": lib["docs"] if lib else 0,
                  "seconds": round(time.perf_counter() - t0, 3)},
        "fairness": FAIRNESS,
    }
