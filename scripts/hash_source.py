"""Fetch a source document and print the content_sha256 to paste into a record.

    python scripts/hash_source.py https://www.szse.cn/... [--quote "text to confirm"]

Uses a browser-like User-Agent and a cookie jar (some exchange sites require both). Prints size,
sha256, detected title, and — if --quote is given — whether the quote appears verbatim in the page text.
Never paste a hash you did not compute from the document yourself.
"""
from __future__ import annotations
import argparse, hashlib, html, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from marina_rules.sourcehash import content_sha256, html_to_text  # noqa: E402

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

def fetch(url: str) -> bytes:
    jar = tempfile.mktemp(suffix=".jar")
    best = b""
    for _ in range(3):  # some CDNs truncate intermittently; keep the longest of three
        r = subprocess.run(["curl", "-sL", "--max-time", "60", "-A", UA, "-c", jar, "-b", jar, url],
                           capture_output=True, timeout=90)
        if len(r.stdout) > len(best):
            best = r.stdout
    return best

def to_text(b: bytes) -> str:
    for enc in ("utf-8", "gb18030"):
        try:
            t = b.decode(enc); break
        except UnicodeDecodeError:
            continue
    else:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("url"); ap.add_argument("--quote")
    a = ap.parse_args()
    b = fetch(a.url)
    if len(b) < 200:
        print(f"fetch failed or empty ({len(b)} bytes). Try opening in a browser and saving the file, then: shasum -a 256 <file>", file=sys.stderr)
        return 1
    h, kind = content_sha256(b, a.url)
    print(f"bytes:          {len(b)}")
    print(f"content_sha256: {h}")
    print(f"hash_kind:      {kind}   ({'extracted text — stable across CMS re-renders' if kind == 'text' else 'raw bytes'})")
    t = html_to_text(b) if kind == "text" else ""
    m = re.search(r"<title>(.*?)</title>", b.decode("utf-8", "ignore"), re.S)
    if m: print(f"title:  {html.unescape(m.group(1)).strip()[:120]}")
    if a.quote:
        ok = a.quote.strip() in t
        print(f"quote:  {'FOUND verbatim' if ok else 'NOT FOUND — fix the quote or the URL'}")
        return 0 if ok else 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
