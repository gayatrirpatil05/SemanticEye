"""Step 4 - AI-pattern signals. Pure statistics, no model, no download, fully explainable.

Every point of the score comes from a named, visible signal (an additive score, so the
"why" is exact, not approximated). The score measures how much a text *resembles*
machine-written style. It is evidence, not proof.
"""
import math
import re
from collections import Counter

from config import AI_SENTENCE_THRESHOLD
from textutil import tokens

# (phrase, weight). Strong tells weigh most. English only.
_PHRASES = [
    ("as an ai language model", 1.0), ("i hope this helps", 0.8), ("delve into", 0.6), ("delves into", 0.6),
    ("delving into", 0.6), ("rich tapestry", 0.6), ("tapestry of", 0.5), ("a testament to", 0.5),
    ("it is important to note", 0.55), ("it is worth noting", 0.5), ("it's worth noting", 0.5),
    ("in today's fast-paced world", 0.6), ("in today's digital age", 0.55), ("in the ever-evolving", 0.55),
    ("ever-evolving landscape", 0.55), ("ever-changing landscape", 0.5), ("navigate the complexities", 0.55),
    ("plays a crucial role", 0.45), ("plays a vital role", 0.45), ("plays a pivotal role", 0.45),
    ("play a crucial role", 0.45), ("play a vital role", 0.45), ("underscores the importance", 0.45),
    ("highlights the importance", 0.4), ("shed light on", 0.35), ("paves the way", 0.35),
    ("pave the way", 0.35), ("unlock the potential", 0.45), ("unlocking the potential", 0.45),
    ("harness the power", 0.45), ("holistic approach", 0.4), ("multifaceted", 0.35), ("game-changer", 0.35),
    ("in conclusion", 0.35), ("in summary", 0.3), ("to sum up", 0.3), ("in essence", 0.3), ("at its core", 0.3),
    ("furthermore", 0.3), ("moreover", 0.3), ("consequently", 0.2), ("nevertheless", 0.2),
    ("additionally", 0.2), ("overall", 0.15), ("seamlessly", 0.3), ("transformative", 0.3),
    ("comprehensive understanding", 0.35), ("a wide range of", 0.2), ("a variety of", 0.15),
    ("significant impact", 0.2), ("it is essential to", 0.3), ("is crucial for", 0.3), ("this essay will", 0.3),
    ("this article explores", 0.4), ("leverage", 0.2), ("fosters", 0.2), ("revolutionize", 0.3),
]
_PHRASE_W = {p: w for p, w in _PHRASES}
_PHRASE_RE = re.compile(r"\b(?:" + "|".join(re.escape(p) for p, _ in sorted(_PHRASES, key=lambda x: -len(x[0]))) + r")\b")
_NOT_ONLY = re.compile(r"\bnot only\b.{0,90}?\bbut also\b")
_FIRST = {"i", "i'm", "i've", "i'll", "i'd", "my", "me", "mine", "myself"}
_CONTR = re.compile(r"(?:n't|'re|'ve|'ll|'m|'d)$")
_INFORMAL = {"lol", "kinda", "gonna", "wanna", "honestly", "stuff", "yeah", "ok", "okay", "really", "pretty", "super", "basically", "literally"}


def _sig(z):
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def sentence_signals(sentence: str) -> dict:
    low = sentence.lower().replace("\u2019", "'")
    toks = tokens(sentence)
    n = max(len(toks), 1)
    hits = [m.group() for m in _PHRASE_RE.finditer(low)]
    pw = sum(_PHRASE_W[h] for h in hits)
    if _NOT_ONLY.search(low):
        hits.append("not only ... but also")
        pw += 0.25
    contr = sum(1 for t in toks if _CONTR.search(t))
    first = sum(1 for t in toks if t in _FIRST)
    informal = sum(1 for t in toks if t in _INFORMAL)
    longr = sum(1 for t in toks if len(t) >= 9) / n
    emo = 1 if ("?" in sentence or "!" in sentence) else 0
    return {"n": len(toks), "phrases": hits, "pw": pw, "contr": contr, "first": first,
            "informal": informal, "long": longr, "emo": emo}


def sentence_score(sig: dict):
    z = -0.9 + 2.2 * sig["pw"]
    why = []
    if sig["phrases"]:
        why.append("stock phrase: " + ", ".join(sorted(set(sig["phrases"]))[:3]))
    n = sig["n"]
    if 17 <= n <= 32:
        z += 0.45
    elif n <= 8:
        z -= 0.5
    if sig["long"] > 0.2:
        z += 0.4
        why.append("dense formal vocabulary")
    if sig["contr"]:
        z -= min(sig["contr"], 2) * 1.0
        why.append("contraction (personal voice)")
    if sig["first"]:
        z -= 0.8
        why.append("first-person voice")
    if sig["informal"]:
        z -= 0.6
        why.append("informal wording")
    if sig["emo"]:
        z -= 0.5
    return _sig(z), why


def _mattr(toks, window=50):
    n = len(toks)
    if n == 0:
        return 0.0
    if n <= window:
        return len(set(toks)) / n
    cnt = Counter(toks[:window])
    total, k = len(cnt) / window, 1
    for i in range(window, n):
        out = toks[i - window]
        cnt[out] -= 1
        if cnt[out] == 0:
            del cnt[out]
        cnt[toks[i]] += 1
        total += len(cnt) / window
        k += 1
    return total / k


def document_signals(sentences, sigs):
    toks_all = [t for s in sentences for t in tokens(s)]
    n_words = len(toks_all)
    lens = [x["n"] for x in sigs]
    mean = sum(lens) / len(lens)
    var = sum((l - mean) ** 2 for l in lens) / len(lens)
    cv = math.sqrt(var) / mean if mean else 0.0
    openers = [tokens(s)[0] for s in sentences if tokens(s)]
    distinct_open = len(set(openers)) / len(openers) if openers else 1.0
    per100 = lambda v: 100.0 * v / max(n_words, 1)
    tri = Counter(zip(toks_all, toks_all[1:], toks_all[2:]))
    rep_tri = sum(c for c in tri.values() if c > 1) / max(len(toks_all) - 2, 1)
    return {
        "words": n_words, "sentences": len(sentences), "mean_len": mean, "cv": cv,
        "mattr": _mattr(toks_all), "distinct_open": distinct_open, "rep_tri": rep_tri,
        "phrase_density": per100(sum(x["pw"] for x in sigs)),
        "contr_rate": per100(sum(x["contr"] for x in sigs)),
        "first_rate": per100(sum(x["first"] for x in sigs)),
        "informal_rate": per100(sum(x["informal"] for x in sigs)),
        "long_ratio": sum(1 for t in toks_all if len(t) >= 9) / max(n_words, 1),
    }


def document_score(d: dict):
    """Additive log-odds model. Returns (probability-like score 0..1, list of named contributions)."""
    parts = []

    def add(name, value, text):
        parts.append({"signal": name, "points": round(value, 2), "detail": text})

    add("Stock phrases", _clip(1.1 * d["phrase_density"], 0, 4.0),
        f"{d['phrase_density']:.1f} weighted stock-phrase hits per 100 words (cliches typical of generated text)")
    add("Sentence rhythm", _clip(3.2 * (0.45 - d["cv"]), -1.8, 1.6),
        f"Sentence-length variation is {d['cv']:.2f}; low values mean very even sentences, high values mean natural ups and downs")
    add("Vocabulary variety", _clip(2.5 * (0.70 - d["mattr"]), -1.0, 1.0),
        f"Moving-window vocabulary variety is {d['mattr']:.2f}")
    add("Personal voice", -_clip(0.55 * d["contr_rate"] + 0.45 * d["first_rate"] + 0.5 * d["informal_rate"], 0, 2.4),
        f"{d['contr_rate']:.1f} contractions, {d['first_rate']:.1f} first-person words and {d['informal_rate']:.1f} informal words per 100 words")
    add("Sentence length", 0.5 if 16 <= d["mean_len"] <= 30 else (-0.5 if d["mean_len"] < 11 else 0.0),
        f"Average sentence is {d['mean_len']:.0f} words")
    add("Formal vocabulary", _clip(4.0 * (d["long_ratio"] - 0.13), -0.8, 0.9),
        f"{d['long_ratio'] * 100:.0f}% of words have 9 or more letters")
    add("Repeated openers", _clip(2.0 * (0.72 - d["distinct_open"]), -0.6, 0.8),
        f"{d['distinct_open'] * 100:.0f}% of sentences start with a different word")
    add("Repeated phrasing", _clip(6.0 * (d["rep_tri"] - 0.04), -0.3, 0.8),
        f"{d['rep_tri'] * 100:.1f}% of word triplets are repeated")
    z = -1.2 + sum(p["points"] for p in parts)
    z *= min(1.0, math.sqrt(d["words"] / 200.0))        # short text -> pulled toward 50%, never confident
    parts.sort(key=lambda p: -abs(p["points"]))
    for p in parts:
        p["effect"] = "raises" if p["points"] > 0.05 else ("lowers" if p["points"] < -0.05 else "neutral")
    return _sig(z), parts


def analyse(sentences):
    """Per-sentence AI-pattern scores and the document-level explained score."""
    sigs = [sentence_signals(s) for s in sentences]
    rows = []
    for s, sg in zip(sentences, sigs):
        p, why = sentence_score(sg)
        rows.append({"ai": p, "why": why, "flag": p >= AI_SENTENCE_THRESHOLD})
    d = document_signals(sentences, sigs)
    score, parts = document_score(d)
    return rows, score, parts, d
