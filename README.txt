SemanticEye - offline plagiarism and AI-pattern checker

RUN
  Windows: double-click run_ui.bat      Mac/Linux: ./run_ui.sh
  Command line: python cli.py --text "Several sentences here." --source reference.txt
  Prove it is offline: python cli.py --selftest      Run checks: python tests/test_all.py

WHAT IT DOES
  Paste text (no word limit) or upload PDF / DOCX / TXT / MD (up to 50 MB each).
  Plagiarism : compares against sources you paste, upload, or keep in the library/ folder.
               Finds verbatim copying (word fingerprints) and reworded copying (stems + a built-in
               synonym map). Each flag shows the source sentence and highlights the copied words.
  AI pattern : explainable statistics (sentence rhythm, stock phrases, vocabulary, personal voice).
               Every point of the score is listed under "Why this score".
  Report     : Report ID (SHA-256 based), copy or download a plain-text report (flagged sentences only).

FILES
  app.py        local web server (127.0.0.1 only, random session key, strict security headers)
  ui_page.html  the interface            netguard.py  blocks all outbound network + counts attempts
  ingest.py     reads TXT/MD/DOCX/PDF from memory       splitter.py  sentence splitting
  plagiarism.py fingerprints + concept matching + library    ai_signals.py  explainable AI-pattern score
  report.py     combines everything     textutil.py  tokens, stemming, synonym map    config.py  settings
  vendor/       bundled pypdf (pure Python) used only to read PDFs
  samples/      demo and calibration texts       tests/  automated checks

LIMITS (read these before presenting results)
  - Offline means it cannot search the web or a global database. It finds copying only from text
    you give it. With no sources it shows "n/a", never a misleading 0%.
  - The AI-pattern score is a statistical resemblance to machine style, not proof of authorship.
    It is English-oriented and can misfire on non-native English, formal academic prose and templates.
  - Reworded detection uses stemming and a small synonym map (about 60 groups). Heavy paraphrase
    with unrelated vocabulary will be missed.
  - Scanned PDFs need OCR, which is not included.
