"""Shared text helpers: tokens, light stemming, and a small built-in concept map.

The concept map is what lets SemanticEye notice reworded copying with no AI model
and no download: words with the same meaning ("large", "huge", "substantial")
collapse to one concept before sentences are compared.
"""
import re

_TOK = re.compile(r"[^\W_]+(?:['\u2019][^\W_]+)*")

STOP = set("""a an the and or but if then else of to in on at by for with about as into like through after
over between out against during without before under around among from up down is are was were be been being
am do does did doing have has had having i me my we our you your he him his she her it its they them their
this that these those there here what which who whom whose when where why how not no nor so than too very can
could should would may might will shall must also just only own same such both each few more most other some
any all again further once while because until s t""".split())


def tokens(text: str):
    return [m.group().lower().replace("\u2019", "'") for m in _TOK.finditer(text)]


def tokens_pos(text: str):
    return [(m.group().lower().replace("\u2019", "'"), m.start(), m.end()) for m in _TOK.finditer(text)]


_SUFFIXES = ("ations", "ation", "ments", "ment", "ness", "ings", "ing", "edly", "ed", "es", "ly", "s")


def stem(w: str) -> str:
    n = len(w)
    if n <= 3 or not w.isalpha():
        return w
    if w.endswith("ies") and n > 4:
        w = w[:-3] + "y"
    else:
        for suf in _SUFFIXES:
            if w.endswith(suf) and n - len(suf) >= 3:
                w = w[: -len(suf)]
                break
    if w.endswith("e") and len(w) > 3:      # live / living -> liv ; rise / rising -> ris
        w = w[:-1]
    return w


_GROUPS = """
big large huge enormous massive substantial considerable sizable
small little tiny minor modest
show demonstrate reveal indicate illustrate display
use utilize employ apply
help assist aid support
begin start commence initiate
end finish conclude terminate complete
buy purchase acquire obtain
important crucial vital essential significant key critical matter
increase rise grow growth expand boost
decrease reduce decline drop lower diminish
fast quick rapid swift speedy
slow gradual sluggish
good great excellent positive beneficial favorable favourable
bad poor negative harmful adverse
problem issue challenge difficulty obstacle
idea concept notion thought
method approach technique strategy procedure
result outcome finding consequence effect
change alter modify transform shift adjust
need require demand necessitate
make create produce generate build develop
examine inspect study investigate analyze analyse
say state declare mention argue claim assert
think believe consider suppose assume
people individuals persons humans
many numerous several various multiple countless
often frequently commonly regularly
enough sufficient adequate
hard difficult tough challenging demanding
easy simple straightforward effortless
choose select pick
give provide offer supply deliver
keep retain maintain preserve
find discover locate identify detect
explain describe clarify outline
prove confirm verify validate
child kid youngster
house home dwelling residence
car vehicle automobile
job occupation profession career employment
money cash funds capital
company firm business corporation enterprise
country nation
doctor physician
student pupil learner
teacher instructor educator
rich wealthy affluent
poor impoverished needy
smart intelligent clever bright
happy glad pleased joyful
sad unhappy sorrowful
start origin source beginning
danger risk threat hazard
chance opportunity possibility prospect
way manner means
protect safeguard conserve defend shield
animal wildlife fauna creature
cause trigger induce provoke
expel eject emit release discharge push
warm heat hot temperature
white pale bleached
""".strip().splitlines()

CANON = {}
for _line in _GROUPS:
    _ws = _line.split()
    _c = stem(_ws[0])
    for _w in _ws:
        CANON.setdefault(stem(_w), _c)


def concepts(words):
    """Content-bearing concepts of a token list (stopwords out, synonyms merged)."""
    out = []
    for w in words:
        if w in STOP or len(w) < 3 and not w.isdigit():
            continue
        s = stem(w)
        out.append(CANON.get(s, s))
    return out
