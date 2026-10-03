"""Offline self-check:  python tests/test_all.py   (no internet, no extra installs)"""
import io, os, sys, time, unittest, zipfile, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import netguard
netguard.install()
import ingest, report, splitter, ai_signals

S = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples")
def rd(n):
    with open(os.path.join(S, n), encoding="utf-8") as f:
        return f.read()


def make_docx(paragraphs, extra=b""):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>").encode() + extra
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", xml)
    return b.getvalue()


class Net(unittest.TestCase):
    def test_outside_is_blocked(self):
        r = netguard.probe()
        self.assertTrue(r["all_blocked"])
        self.assertEqual(r["real_attempts_blocked"], netguard.blocked_count())

    def test_loopback_allowed(self):
        import socket
        srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
        c = socket.create_connection(("127.0.0.1", srv.getsockname()[1]), timeout=2)
        c.close(); srv.close()


class Ingest(unittest.TestCase):
    def test_txt_docx(self):
        self.assertIn("hello", ingest.prepare(name="a.txt", data=b"hello world again and again"))
        t = ingest.prepare(name="a.docx", data=make_docx(["First paragraph here.", "Second one follows."]))
        self.assertIn("First paragraph", t)

    def test_docx_xml_bomb_refused(self):
        evil = make_docx(["x"], extra=b'<!DOCTYPE lolz [<!ENTITY a "aaaa">]>')
        with self.assertRaises(ingest.InputError):
            ingest.prepare(name="e.docx", data=evil)

    def test_bad_types(self):
        for name, data in (("x.exe", b"MZ"), ("x.pdf", b"not a pdf"), ("x.docx", b"not zip")):
            with self.assertRaises(ingest.InputError):
                ingest.prepare(name=name, data=data)

    def test_pdf_both_readers(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab not installed (only needed to build a test PDF)")
        b = io.BytesIO(); c = canvas.Canvas(b)
        c.drawString(72, 750, "Photosynthesis converts sunlight into chemical energy in plants every day."); c.save()
        data = b.getvalue()
        self.assertIn("Photosynthesis", ingest._pdf_via_pypdf(data))
        self.assertIn("Photosynthesis", ingest._pdf_basic(data))


class Engine(unittest.TestCase):
    src = rd("source_article.txt")

    def test_verbatim_and_reworded_found(self):
        r = report.analyze(text=rd("demo_submission.txt"), sources=[("src", self.src)], use_library=False)
        kinds = [s["match_type"] for s in r["sentences"]]
        self.assertEqual(kinds.count("verbatim"), 1)
        self.assertEqual(kinds.count("reworded"), 2)
        self.assertGreater(r["plagiarism_pct"], 40)

    def test_unrelated_text_is_clean(self):
        for f in ("human_style.txt", "academic_human.txt", "ai_style.txt"):
            r = report.analyze(text=rd(f), sources=[("src", self.src)], use_library=False)
            self.assertEqual(r["plagiarism_pct"], 0.0, f)

    def test_no_sources_is_not_zero_percent(self):
        r = report.analyze(text=rd("human_style.txt"), use_library=False)
        self.assertIsNone(r["plagiarism_pct"])

    def test_ai_style_scores_above_human_style(self):
        a = report.analyze(text=rd("ai_style.txt"), use_library=False)["ai_pct"]
        h = report.analyze(text=rd("human_style.txt"), use_library=False)["ai_pct"]
        self.assertGreater(a, 65); self.assertLess(h, 35)

    def test_deterministic(self):
        a = report.analyze(text=rd("demo_submission.txt"), sources=[("s", self.src)], use_library=False)
        b = report.analyze(text=rd("demo_submission.txt"), sources=[("s", self.src)], use_library=False)
        a["stats"].pop("seconds"); b["stats"].pop("seconds")
        self.assertEqual(a, b)

    def test_reasons_add_up(self):
        r = report.analyze(text=rd("ai_style.txt"), use_library=False)
        self.assertTrue(all("signal" in x and "points" in x for x in r["reasons"]))

    def test_short_text_never_confident(self):
        r = report.analyze(text="Furthermore, it is important to note that this plays a crucial role.", use_library=False)
        self.assertEqual(r["reliability"], "low")

    def test_abbreviation_split(self):
        s = splitter.split_sentences("Dr. Rao met Mr. Singh at the lab. They talked for an hour about results.")
        self.assertEqual(len(s), 2)


class Speed(unittest.TestCase):
    def test_large_document_is_fast(self):
        random.seed(1)
        vocab = [f"word{i}" for i in range(4000)]
        make = lambda n: " ".join(" ".join(random.choice(vocab) for _ in range(random.randint(8, 25))) + "." for _ in range(n))
        text, source = make(6000), make(6000)        # roughly 100,000 words each
        t = time.perf_counter()
        r = report.analyze(text=text, sources=[("big", source)], use_library=False)
        dt = time.perf_counter() - t
        print(f"\n  {r['stats']['words']:,} words vs {r['stats']['source_words']:,} source words: {dt:.2f} s")
        self.assertLess(dt, 15)


if __name__ == "__main__":
    unittest.main(verbosity=1)
