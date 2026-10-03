"""Step 1 - Input. Reads TXT / MD / DOCX / PDF straight from memory.

Uploaded files are never written to disk by SemanticEye. Only Python's standard
library is used, except for PDF where a bundled copy of pypdf (vendor/) is used,
with a basic built-in reader as fallback.
"""
import base64
import io
import os
import re
import sys
import zipfile
import zlib
import xml.etree.ElementTree as ET

from config import HERE, MAX_FILE_MB, MAX_ZIP_EXPANSION_MB


class InputError(ValueError):
    """Problems with the user's input. Messages are safe to show (they never echo content)."""


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _decode_text(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def _docx_text(data: bytes) -> str:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise InputError("This DOCX file is damaged or not a real DOCX.")
    total = sum(i.file_size for i in z.infolist())
    if total > MAX_ZIP_EXPANSION_MB * 1024 * 1024:
        raise InputError("DOCX expands to an unsafe size and was refused.")
    try:
        xml = z.read("word/document.xml")
    except KeyError:
        raise InputError("This DOCX has no readable body.")
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:       # blocks XML entity-expansion tricks
        raise InputError("DOCX contains unsafe XML and was refused.")
    root = ET.fromstring(xml)
    paras = []
    for p in root.iter(_W + "p"):
        parts = []
        for node in p.iter():
            if node.tag == _W + "t" and node.text:
                parts.append(node.text)
            elif node.tag in (_W + "tab", _W + "br"):
                parts.append(" ")
        paras.append("".join(parts))
    return "\n\n".join(paras)


# ---- PDF -------------------------------------------------------------------

def _pdf_via_pypdf(data: bytes) -> str:
    vendor = os.path.join(HERE, "vendor")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    if r.is_encrypted:
        try:
            if not r.decrypt(""):
                raise InputError("This PDF is password-protected.")
        except InputError:
            raise
        except Exception:
            raise InputError("This PDF is password-protected.")
    return "\n\n".join((p.extract_text() or "") for p in r.pages)


_STR = rb"\((?:\\.|[^\\)])*\)"
_SHOW = re.compile(rb"(\[(?:" + _STR + rb"|[^\]])*\]|" + _STR + rb")\s*(?:TJ|Tj|'|\")", re.S)
_ESC = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


def _unescape(s: bytes) -> str:
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i:i + 1]
        if c == b"\\" and i + 1 < len(s):
            n = s[i + 1:i + 2]
            if n in _ESC:
                out += _ESC[n]; i += 2; continue
            m = re.match(rb"[0-7]{1,3}", s[i + 1:])
            if m:
                out.append(int(m.group(), 8) & 255); i += 1 + len(m.group()); continue
            out += n; i += 2; continue
        out += c; i += 1
    return out.decode("latin-1")


def _pdf_basic(data: bytes) -> str:
    """Fallback reader for simple PDFs (standard fonts, literal strings)."""
    pages = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\n?endstream", data, re.S):
        raw = m.group(1)
        try:
            if raw.rstrip().endswith(b"~>"):
                raw = base64.a85decode(raw.strip()[:-2])
            raw = zlib.decompress(raw)
        except Exception:
            pass
        if b"BT" not in raw:
            continue
        chunks = []
        for sm in _SHOW.finditer(raw):
            block = sm.group(1)
            if block.startswith(b"["):
                pieces = re.findall(_STR + rb"|-?\d+\.?\d*", block)
                txt = "".join(_unescape(p[1:-1]) if p.startswith(b"(") else (" " if float(p) < -200 else "")
                              for p in pieces)
            else:
                txt = _unescape(block[1:-1])
            chunks.append(txt)
        if chunks:
            pages.append(" ".join(chunks))
    return "\n\n".join(pages)


def _pdf_text(data: bytes) -> str:
    text = ""
    try:
        text = _pdf_via_pypdf(data)
    except InputError:
        raise
    except Exception:
        text = ""
    if len(text.split()) < 5:
        try:
            text = _pdf_basic(data) or text
        except Exception:
            pass
    if len(text.split()) < 5:
        raise InputError("No readable text in this PDF (it may be a scan). "
                         "OCR is not included. Export it as TXT or DOCX instead.")
    return text


# ---- public API --------------------------------------------------------------

def read_bytes(name: str, data: bytes) -> str:
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise InputError(f"A file is larger than {MAX_FILE_MB} MB.")
    ext = os.path.splitext(name or "")[1].lower()
    if ext in (".txt", ".md"):
        return _decode_text(data)
    if ext == ".docx":
        return _docx_text(data)
    if ext == ".pdf":
        if not data.startswith(b"%PDF"):
            raise InputError("This file is not a real PDF.")
        return _pdf_text(data)
    raise InputError("Unsupported file type. Use PDF, DOCX, TXT or MD.")


def read_path(path: str) -> str:
    if os.path.getsize(path) > MAX_FILE_MB * 1024 * 1024:
        raise InputError(f"A file is larger than {MAX_FILE_MB} MB.")
    with open(path, "rb") as f:
        return read_bytes(path, f.read())


def prepare(text=None, name=None, data=None) -> str:
    if data is not None:
        out = read_bytes(name or "", data)
    else:
        out = text or ""
    out = out.replace("\x00", " ").strip()
    if not out.split():
        raise InputError("No text provided.")
    return out
