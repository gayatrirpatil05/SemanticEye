"""Step 3 - Match. Three offline layers, no model, no download:

 1. Fingerprints : word 4-grams hashed and indexed -> finds verbatim and near-verbatim copying.
 2. Concept map  : stems + built-in synonym groups -> finds reworded or reordered copying.
 3. Evidence     : every flag keeps the source name, the source sentence and the matching words.

Limit (by design): offline means it can only compare against text you provide
(pasted sources, uploaded sources, or files in the library folder). It cannot search the web.
"""
import hashlib
import math
import os
from collections import Counter, defaultdict

import ingest
from config import (LIBRARY_DIR, LIBRARY_EXTS, SHINGLE, VERBATIM_RUN_WORDS,
                    VERBATIM_COVERAGE, REWORD_DICE, REWORD_CONTAIN)
from splitter import split_sentences
from textutil import tokens, tokens_pos, concepts

_MAX_POSTING = 400


class SourceIndex:
    def __init__(self):
        self.names = []                  # doc names
        self.sent_doc = []               # sid -> doc id
        self.sent_text = []              # sid -> text
        self.sent_conc = []              # sid -> frozenset of concepts
        self.gram = {}                   # 4-gram hash -> sid
        self.post = defaultdict(list)    # concept -> [sid]
        self.words = 0
        self._idf = {}

    def add(self, name: str, text: str):
        did = len(self.names)
        self.names.append(name)
        for s in split_sentences(text):
            sid = len(self.sent_text)
            toks = tokens(s)
            self.words += len(toks)
            self.sent_doc.append(did)
            self.sent_text.append(s)
            conc = frozenset(concepts(toks))
            self.sent_conc.append(conc)
            for c in conc:
                self.post[c].append(sid)
            for i in range(len(toks) - SHINGLE + 1):
                self.gram.setdefault(hash(tuple(toks[i:i + SHINGLE])), sid)
        self._idf = {}

    @property
    def empty(self):
        return not self.sent_text

    def idf(self, c):
        v = self._idf.get(c)
        if v is None:
            v = math.log(1 + len(self.sent_text) / (1 + len(self.post.get(c, ()))))
            self._idf[c] = v
        return v

    def check(self, sentence: str) -> dict:
        """Compare one sentence with this index. Returns evidence or a clean result."""
        pos = tokens_pos(sentence)
        toks = [p[0] for p in pos]
        res = {"kind": "clean", "similarity": 0.0, "source": None, "source_text": None, "spans": []}
        if self.empty or not toks:
            return res

        # layer 1: exact fingerprints
        matched = [False] * len(toks)
        hits = Counter()
        ngrams = max(len(toks) - SHINGLE + 1, 0)
        found = 0
        for i in range(ngrams):
            sid = self.gram.get(hash(tuple(toks[i:i + SHINGLE])))
            if sid is not None:
                found += 1
                hits[sid] += 1
                for j in range(i, i + SHINGLE):
                    matched[j] = True
        exact = found / ngrams if ngrams else 0.0
        run = best = 0
        for m in matched:
            run = run + 1 if m else 0
            best = max(best, run)

        # layer 2: concept overlap with the best few candidates
        conc = frozenset(concepts(toks))
        sim2, sim_sid, reworded = 0.0, None, False
        if len(conc) >= 3:
            n_sent = len(self.sent_text)
            limit = max(60, int(n_sent * 0.05))
            usable = [c for c in conc if 0 < len(self.post.get(c, ())) <= min(limit, _MAX_POSTING)]
            usable.sort(key=lambda c: len(self.post[c]))
            cand = Counter()
            for c in usable[:6]:
                for sid in self.post[c]:
                    cand[sid] += 1
            w_in = sum(self.idf(c) for c in conc)
            for sid, _ in cand.most_common(25):
                sc = self.sent_conc[sid]
                common = conc & sc
                if len(common) < 3:
                    continue
                shared = sum(self.idf(c) for c in common)
                w_src = sum(self.idf(c) for c in sc)
                contain = shared / min(w_in, w_src)          # how much of the shorter sentence is covered
                dice = 2 * shared / (w_in + w_src)
                strong = (len(common) >= 5 and contain >= REWORD_CONTAIN and dice >= 0.30) or dice >= REWORD_DICE
                if (strong, contain) > (reworded, sim2):
                    reworded, sim2, sim_sid = strong, contain, sid
        dice = sim2
        dice_sid = sim_sid

        verbatim = best >= VERBATIM_RUN_WORDS or exact >= VERBATIM_COVERAGE
        if verbatim:
            sid = hits.most_common(1)[0][0]
            res.update(kind="verbatim", similarity=max(exact, dice), spans=_spans(pos, matched))
        elif reworded:
            sid = dice_sid
            res.update(kind="reworded", similarity=dice, spans=[])
        else:
            res["similarity"] = max(exact, dice)
            return res
        res["source"] = self.names[self.sent_doc[sid]]
        res["source_text"] = self.sent_text[sid][:300]
        return res


def _spans(pos, matched):
    spans, start = [], None
    for k, m in enumerate(matched):
        if m and start is None:
            start = k
        if (not m or k == len(matched) - 1) and start is not None:
            end = k if m else k - 1
            spans.append([pos[start][1], pos[end][2]])
            start = None
    return spans


def build_index(named_texts) -> SourceIndex:
    idx = SourceIndex()
    for name, text in named_texts:
        idx.add(name, text)
    return idx


def check_all(sentences, indexes):
    """Best evidence per sentence across several indexes (flagged beats clean, then higher similarity)."""
    empty = {"kind": "clean", "similarity": 0.0, "source": None, "source_text": None, "spans": []}
    out = []
    for s in sentences:
        results = [ix.check(s) for ix in indexes] or [empty]
        out.append(max(results, key=lambda r: (r["kind"] != "clean", r["similarity"])))
    return out


# ---- private reference library (a folder on this computer) -----------------------

_lib = {"sig": None, "index": None, "digest": "", "docs": 0, "words": 0, "skipped": 0}


def library():
    """Index every file in library/, cached in memory and rebuilt only when files change."""
    files = []
    if os.path.isdir(LIBRARY_DIR):
        for n in sorted(os.listdir(LIBRARY_DIR)):
            p = os.path.join(LIBRARY_DIR, n)
            if os.path.isfile(p) and n.lower().endswith(LIBRARY_EXTS):
                st = os.stat(p)
                files.append((n, p, st.st_size, int(st.st_mtime)))
    sig = tuple((n, sz, mt) for n, _, sz, mt in files)
    if sig == _lib["sig"] and _lib["index"] is not None:
        return _lib
    named, h, skipped = [], hashlib.sha256(), 0
    for n, p, _, _ in files:
        try:
            t = ingest.read_path(p)
            named.append((n, t))
            h.update(n.encode() + hashlib.sha256(t.encode("utf-8", "ignore")).digest())
        except Exception:
            skipped += 1
    idx = build_index(named)
    _lib.update(sig=sig, index=idx, digest=h.hexdigest(), docs=len(named), words=idx.words, skipped=skipped)
    return _lib
