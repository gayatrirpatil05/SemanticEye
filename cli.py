"""Command line:  python cli.py --text "..." | --file report.pdf  [--source a.txt b.docx]  [--selftest]"""
import netguard
netguard.install()

import argparse
import json
import os

import ingest
import report

ap = argparse.ArgumentParser()
ap.add_argument("--text")
ap.add_argument("--file")
ap.add_argument("--source", nargs="*", default=[])
ap.add_argument("--selftest", action="store_true", help="prove that outside connections are blocked")
a = ap.parse_args()
if a.selftest:
    print(json.dumps(netguard.probe(), indent=2))
else:
    srcs = [(os.path.basename(p), ingest.read_path(p)) for p in a.source]
    if a.file:
        with open(a.file, "rb") as f:
            res = report.analyze(name=a.file, data=f.read(), sources=srcs)
    else:
        res = report.analyze(text=a.text, sources=srcs)
    print(json.dumps(res, indent=2))
