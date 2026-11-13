"""Weekly source watch — the cheapest honest layer of automation.

It does NOT try to understand notices. It does three mechanical things:

1. **Source drift.** Re-fetch every cited source and compare its *content* hash (extracted text for HTML,
   bytes for PDF) to the one recorded. A mismatch means the document's text changed or the URL now serves
   something else; the record needs a human re-check. CMS re-renders do not trigger this.
2. **Listing-page diff.** Fetch each watched listing page, extract (date, title, url) items, and compare
   with the last snapshot in ``watch/state.json``. New items whose title hits a rule keyword are reported.
3. **Report.** Print a Markdown report (``ops/weekly.sh`` saves it under ``ops/reports/``). Never edits
   data, never merges, never contacts a code host: scheduled jobs are local-only, and anything that needs
   a public issue goes through the maintainer's queue by hand.

Keywords are deliberately broad; false positives cost a glance, misses cost a wrong rule.

Usage:
    python scripts/source_watch.py                 # print report
    python scripts/source_watch.py --no-drift      # skip re-hashing sources (faster)
    python scripts/source_watch.py --no-save-state # do not write watch/state.json (dry runs)

``--github`` (which used to open a tracking issue) is disabled: it prints a refusal and exits 3.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
import marina_rules as mr  # noqa: E402
from marina_rules.sourcehash import content_sha256  # noqa: E402

STATE = os.path.join(ROOT, "watch", "state.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

WATCH = {
    "SSE trading rules": "http://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/",
    "SSE news": "https://www.sse.com.cn/aboutus/mediacenter/hotandd/",
    "SZSE business rules": "https://www.szse.cn/lawrules/rule/allrules/bussiness/index.html",
    "SZSE notices": "https://www.szse.cn/disclosure/notice/general/index.html",
    "CSDC notices": "https://www.chinaclear.cn/zdjs/gszb/index.shtml",
    "MOF announcements": "https://www.mof.gov.cn/gkml/caizhengwengao/",
}
KEYWORDS = ["涨跌幅", "交易规则", "印花税", "过户费", "手续费", "经手费", "佣金", "保证金", "涨跌停", "申报价格",
            "最小变动", "交易时间", "集合竞价", "结算", "风险警示", "退市整理", "T+", "实施细则", "特别规定"]


def fetch(url: str, timeout: int = 60, tries: int = 3) -> bytes:
    """Longest of ``tries`` fetches — exchange CDNs intermittently return truncated pages."""
    jar = tempfile.mktemp(suffix=".jar")
    best = b""
    for _ in range(tries):
        try:
            r = subprocess.run(["curl", "-sL", "--max-time", str(timeout), "-A", UA, "-c", jar, "-b", jar, url],
                               capture_output=True, timeout=timeout + 30)
            if len(r.stdout) > len(best):
                best = r.stdout
        except Exception:
            pass
    return best


def items_from_listing(base: str, b: bytes) -> list[dict]:
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        t = b.decode("gb18030", "ignore")
    out = []
    # generic: an <a href=...>title</a> near a YYYY-MM-DD within 300 chars
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
        href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not title or len(title) < 6:
            continue
        window = t[m.end(): m.end() + 300] + t[max(0, m.start() - 300): m.start()]
        d = re.search(r"(20\d\d)[-./年](\d{1,2})[-./月](\d{1,2})", window)
        date = f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d else ""
        if href.startswith("/"):
            from urllib.parse import urljoin
            href = urljoin(base, href)
        out.append({"date": date, "title": html.unescape(title)[:120], "url": href})
    # dedupe by url
    seen, uniq = set(), []
    for it in out:
        if it["url"] in seen:
            continue
        seen.add(it["url"]); uniq.append(it)
    return uniq


def load_state() -> dict:
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return {"listings": {}, "last_run": None}


def save_state(st: dict) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def run(check_drift: bool = True, save: bool = True) -> dict:
    today = dt.date.today().isoformat()
    report = {"date": today, "drift": [], "new_items": [], "unreachable": [], "listings_checked": 0}

    if check_drift:
        seen_urls = {}
        for r in mr.records():
            for s in r.sources:
                seen_urls.setdefault(s["url"], (r.id, s.get("content_sha256")))
        for url, (rid, sha) in seen_urls.items():
            b = fetch(url)
            if len(b) < 200:
                report["unreachable"].append({"record": rid, "url": url}); continue
            got, _kind = content_sha256(b, url)
            if sha and got != sha:
                report["drift"].append({"record": rid, "url": url, "recorded": sha[:16], "now": got[:16], "bytes": len(b)})

    st = load_state()
    for name, url in WATCH.items():
        b = fetch(url)
        if len(b) < 500:
            report["unreachable"].append({"listing": name, "url": url}); continue
        items = items_from_listing(url, b)
        report["listings_checked"] += 1
        prev = {i["url"] for i in st["listings"].get(name, [])}
        for it in items:
            if it["url"] in prev:
                continue
            hit = [k for k in KEYWORDS if k in it["title"]]
            if hit and st["listings"].get(name) is not None:  # first run only seeds, does not report
                report["new_items"].append({"listing": name, **it, "keywords": hit})
        st["listings"][name] = items[:200]
    st["last_run"] = today
    if save:
        save_state(st)
    return report


def to_markdown(rep: dict) -> str:
    L = [f"# Source watch — {rep['date']}", ""]
    L.append(f"Listings checked: {rep['listings_checked']} · source drift: {len(rep['drift'])} · "
             f"new keyword hits: {len(rep['new_items'])} · unreachable: {len(rep['unreachable'])}")
    L.append("")
    if rep["drift"]:
        L += ["## ⚠️ Source drift (document changed since we hashed it — re-check the record)", ""]
        for d in rep["drift"]:
            L.append(f"- `{d['record']}` — {d['url']}  \n  recorded `{d['recorded']}…` → now `{d['now']}…` ({d['bytes']} bytes)")
        L.append("")
    if rep["new_items"]:
        L += ["## 🆕 New notices matching rule keywords (human: is this a rule change?)", ""]
        for it in sorted(rep["new_items"], key=lambda x: x["date"], reverse=True):
            L.append(f"- {it['date'] or '????-??-??'} · **{it['listing']}** · [{it['title']}]({it['url']}) · _{', '.join(it['keywords'])}_")
        L.append("")
    if rep["unreachable"]:
        L += ["## Unreachable this run (not an error by itself)", ""]
        for u in rep["unreachable"]:
            L.append(f"- {u.get('record') or u.get('listing')} — {u['url']}")
        L.append("")
    if not (rep["drift"] or rep["new_items"]):
        L.append("Nothing needs a human this week.")
    L += ["", "_Generated by `scripts/source_watch.py`. It reads listing pages and re-hashes sources; it does not interpret notices or edit data._"]
    return "\n".join(L)


GITHUB_DISABLED = "disabled: GitHub writes are not allowed from scheduled jobs (use the maintainer's queue)"


if __name__ == "__main__":
    if "--github" in sys.argv:
        print(GITHUB_DISABLED, file=sys.stderr)
        sys.exit(3)
    rep = run(check_drift="--no-drift" not in sys.argv, save="--no-save-state" not in sys.argv)
    print(to_markdown(rep))
