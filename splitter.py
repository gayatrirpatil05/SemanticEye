"""Split text into sentences. Blank lines are always hard boundaries."""
import re

from config import MIN_SENTENCE_WORDS

_SPLIT = re.compile(r"""(?:(?<=[.!?])|(?<=[.!?]["')\]]))\s+(?=[A-Z0-9"'(\[])""")
_ABBR = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|Fig|No|Inc|Ltd|Co|cf|al|e\.g|i\.e)\.", re.I)
_DOT = "\u2024"


def split_sentences(text: str, min_words: int = MIN_SENTENCE_WORDS) -> list:
    out = []
    for para in re.split(r"\n\s*\n", text.replace("\r", "")):
        t = re.sub(r"\s+", " ", para).strip()
        if not t:
            continue
        t = _ABBR.sub(lambda m: m.group(0).replace(".", _DOT), t)
        for s in _SPLIT.split(t):
            s = s.replace(_DOT, ".").strip()
            if len(s.split()) >= min_words:
                out.append(s)
    return out
