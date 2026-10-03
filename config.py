"""Central settings for SemanticEye (offline edition)."""
import hashlib
import os

ENGINE_VERSION = "2.0-offline"
HERE = os.path.dirname(os.path.abspath(__file__))

MAX_FILE_MB = 50            # per uploaded file
MAX_ZIP_EXPANSION_MB = 300  # DOCX safety: refuse zip bombs
MIN_SENTENCE_WORDS = 4

# Plagiarism thresholds
SHINGLE = 4                 # word n-gram size for exact-copy fingerprints
VERBATIM_RUN_WORDS = 8      # this many consecutive identical words = copied passage
VERBATIM_COVERAGE = 0.50    # or half of the sentence's 4-grams found in a source
REWORD_DICE = 0.62          # strong concept overlap (Dice) = reworded
REWORD_CONTAIN = 0.45       # or >=5 shared concepts covering this share of the shorter sentence

# AI-pattern thresholds
AI_SENTENCE_THRESHOLD = 0.52

LIBRARY_DIR = os.path.join(HERE, "library")
LIBRARY_EXTS = (".txt", ".md", ".docx", ".pdf")


def build_fingerprint() -> str:
    """SHA-256 over the app's own source files. Lets anyone verify the code they run."""
    h = hashlib.sha256()
    for name in sorted(os.listdir(HERE)):
        if name.endswith((".py", ".html")):
            with open(os.path.join(HERE, name), "rb") as f:
                h.update(name.encode() + b"\0" + f.read())
    return h.hexdigest()
