# -*- coding: utf-8 -*-
"""Remove every em-dash from the site. Idempotent; safe to run anytime.

Em-dashes are banned in this project. This tool rewrites them to commas (in
prose) or hyphens (in code comments). The em-dash character is referenced via
chr(0x2014) so the literal never appears in this source file either.
"""
import os, re, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EM = chr(0x2014)   # the em-dash character, without writing it literally

def fix_content(s):
    # attribution: "<cite>(em-dash) Name" -> "<cite>Name"
    s = s.replace("<cite>&mdash; ", "<cite>")
    s = s.replace("<cite>" + EM + " ", "<cite>")
    # spaced em-dash (entity and literal) -> comma
    s = s.replace(" &mdash; ", ", ")
    s = s.replace(" " + EM + " ", ", ")
    # spaced on one side only -> drop
    s = s.replace("&mdash; ", "")
    s = s.replace(EM + " ", "")
    s = s.replace(" &mdash;", "")
    s = s.replace(" " + EM, "")
    # any remaining bare em-dash -> comma
    s = s.replace("&mdash;", ", ")
    s = s.replace(EM, ", ")
    # tidy artifacts (same-line only; never touch newlines or leading indentation)
    s = re.sub(r",[ \t]*,", ",", s)
    s = re.sub(r"[ \t]+,", ",", s)
    s = re.sub(r",[ \t]*\.", ".", s)
    s = re.sub(r",[ \t]*(</p>|</span>|</li>|</h[1-4]>)", r"\1", s)
    return s

def fix_comment(s):
    # code comments: em-dash -> hyphen
    return s.replace(" " + EM + " ", " - ").replace(EM, "-").replace(" &mdash; ", " - ")

files = []
for pat in ("*.html", "about/*.html", "governance/*.html", "amenities/*.html",
            "community/*.html", "contact/*.html", "photos/*.html"):
    files += glob.glob(os.path.join(ROOT, pat))
files.append(os.path.join(ROOT, "_tools", "build.py"))

changed = 0
for f in files:
    with open(f, encoding="utf-8") as fh:
        orig = fh.read()
    new = fix_content(orig)
    if new != orig:
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(new)
        changed += 1
        print("fixed", os.path.relpath(f, ROOT))

for f in (os.path.join(ROOT, "assets", "css", "site.css"),
          os.path.join(ROOT, "assets", "js", "site.js")):
    with open(f, encoding="utf-8") as fh:
        orig = fh.read()
    new = fix_comment(orig)
    if new != orig:
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(new)
        changed += 1
        print("fixed", os.path.relpath(f, ROOT))

print("\n%d files updated" % changed)
