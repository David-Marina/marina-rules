"""Write static rule fact pages and bilingual question pages generated from the data.

    python scripts/build_site.py --out site [--base-url https://example.org/]

Every statement about a rule on these pages is a record field, a source quote, a known gap, a tracking entry or a row
of docs/SCHEMA.md, copied verbatim; the introduction on the index is taken from README.md (and README.zh-CN.md).
Question answers mechanically state the latest open-ended record and the earlier intervals, per exchange;
scripts/site_questions.json contains only question titles and record selectors. Histories must be unbroken.
Nothing depends on the date of the build: two builds of the same data are byte-identical.
Without --base-url no absolute URL of the site is written anywhere (sitemap.xml needs one, so it is written only
with --base-url).

Chinese: fact and original index pages carry a Chinese name in their title, description and a line under the heading, so they can be
found by a Chinese query. The names come from scripts/site_zh.json (display names of families, markets, scopes and
rules — never a value); the values in that line are record fields in their effective_from order, written only where
the page has one unbroken series of plain values per market. All pages carry Open Graph tags; fact pages and the root
also carry a schema.org Dataset description (JSON-LD, a data block: the pages run no script).

Output: index.html, zh/index.html, q/index.html, q/<slug>.html and .md, zh/q/<slug>.html and .md,
<prefix>/index.html, <prefix>/<scope>/index.html, <prefix>/<scope>/<rule>.html and .md,
llms.txt, site.json and, with --base-url, sitemap.xml (lastmod from recorded_at) and robots.txt.
Question pairs have FAQPage JSON-LD and, with --base-url, reciprocal hreflang links.
Known gaps whose (scope, rule) has records are on that fact
page; the others are on their scope page, or on the family index when the scope is not in the registry.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import posixpath
import re
import sys
import time
from collections import Counter, defaultdict
from decimal import Decimal

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
import marina_rules as mr  # noqa: E402

PREFIXES = ("cn", "hk", "us")
FAMILY = {"cn": "China mainland", "hk": "Hong Kong", "us": "United States"}   # data/<prefix>/ directory, by place
NAME_RE = re.compile(r"^[a-z0-9_]+$")
CJK_RE = re.compile(r"[　-ヿ㐀-鿿＀-￯]")
# value shown as a percentage too: fractions of turnover / price (rule name ends in _pct, or is a rate, fee, duty, levy)
PCT_WORDS = ("_rate", "fee", "duty", "levy", "commission_cap", "margin_ratio")

CSS = """
:root{--bg:#fff;--fg:#1b1b1b;--muted:#5d5d5d;--line:#d9d9d9;--head:#f3f3f3;--link:#0b5cad;--quote:#f7f7f2}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#e8e8e8;--muted:#a8a8a8;--line:#3a3a3a;--head:#202020;
--link:#7db8ff;--quote:#1d1d1a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:64rem;margin:0 auto;padding:1rem 16px 3rem}
a{color:var(--link)}
nav{font-size:.9rem;color:var(--muted)}
h1{font-size:1.5rem;line-height:1.3;overflow-wrap:anywhere}
h2{font-size:1.2rem;margin-top:2rem;border-bottom:1px solid var(--line)}
h3{font-size:1rem;overflow-wrap:anywhere}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.88em}
pre{background:var(--head);padding:.6rem;overflow-x:auto}
.wrap{overflow-x:auto;max-width:100%}
table{border-collapse:collapse;margin:.5rem 0}
th,td{border:1px solid var(--line);padding:.25rem .45rem;text-align:left;vertical-align:top}
th{background:var(--head)}
td{overflow-wrap:anywhere}
td:first-child{white-space:nowrap}
p,li{overflow-wrap:anywhere}
table table{margin:0;font-size:.92em}
blockquote{margin:.4rem 0;padding:.4rem .8rem;border-left:4px solid var(--line);background:var(--quote);
white-space:pre-wrap;overflow-wrap:anywhere}
.muted{color:var(--muted)}
dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:.15rem .8rem}
dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere;overflow-x:auto}
ul.src{padding-left:1.1rem}
""".strip()


# --- inputs taken verbatim from the repository --------------------------------------------------------------------
def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _split_row(line: str) -> list:
    """Cells of one Markdown table row; '\\|' is a literal pipe."""
    body = line.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") and not body.endswith("\\|") else body
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", body)]


def schema_definitions(text: str) -> dict:
    """rule → [(section heading, [(column, cell), ...])] from every docs/SCHEMA.md table whose first column is 'rule'.
    Only rows whose first cell is exactly one rule name in backticks count."""
    out: dict = defaultdict(list)
    header, section = None, ""
    for line in text.split("\n"):
        if line.startswith("#"):
            section = line.lstrip("#").strip()
        if not line.startswith("|"):
            header = None
            continue
        cells = _split_row(line)
        if cells and cells[0] == "rule":
            header = cells
            continue
        if header is None or set(line.strip()) <= set("|-: "):
            continue
        m = re.fullmatch(r"`([a-z0-9_]+)`", cells[0])
        if m:
            pairs = list(zip(header[1:], cells[1:len(header)]))
            if len(cells) > len(header):          # an unescaped pipe inside the last cell: keep the text whole
                pairs[-1] = (pairs[-1][0], " | ".join(cells[len(header) - 1:]))
            out[m.group(1)].append((section, pairs))
    return dict(out)


def tracking_meaning(text: str) -> str:
    """The 'Meaning.' paragraph of docs/SCHEMA.md 'Tracking registry', without its label."""
    m = re.search(r"^\*\*Meaning\.\*\* (.+?)\n\n", text, re.S | re.M)
    if not m:
        raise SystemExit("docs/SCHEMA.md: the tracking 'Meaning.' paragraph was not found")
    return " ".join(m.group(1).split())


def readme_intro(text: str) -> list:
    """The first two paragraphs after the README title that are not block quotes (README.md opens with a Chinese
    summary in one): the tag line and the paragraph that follows it."""
    paras = [p.strip() for p in text.split("\n\n")]
    i = next(k for k, p in enumerate(paras) if p.startswith("# "))
    body = [p for p in paras[i + 1:] if not p.startswith(">")]
    return [" ".join(body[0].split()), " ".join(body[1].split())]


def readme_opening(text: str) -> list:
    """Opening paragraphs after the title and before the first second-level heading, verbatim."""
    opening = re.split(r"^## ", text, maxsplit=1, flags=re.M)[0]
    return [p.strip() for p in opening.split("\n\n")[1:] if p.strip()]


def verification_levels(text: str) -> list:
    """(level, meaning) rows of the README 'Verification levels' table."""
    sec = text.split("## Verification levels", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in sec.split("\n"):
        if line.startswith("| `"):
            c = _split_row(line)
            rows.append((c[0].strip("`"), c[1]))
    return rows


# --- rendering helpers --------------------------------------------------------------------------------------------
def esc(s) -> str:
    return html.escape(str(s), quote=True)


def md_inline(text: str) -> str:
    """Escape, then render the inline Markdown used in README / SCHEMA cells: code, bold, italic; links → their text."""
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for p in parts:
        if len(p) > 1 and p.startswith("`") and p.endswith("`"):
            out.append("<code>" + esc(p[1:-1]) + "</code>")
            continue
        p = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", p)
        p = esc(p)
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"(?<![\w*])\*([^*]+?)\*(?![\w*])", r"<em>\1</em>", p)
        out.append(p)
    return "".join(out)


def lang_attr(text: str) -> str:
    return ' lang="zh"' if CJK_RE.search(text or "") else ""


def scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def is_scalar(v) -> bool:
    return not isinstance(v, (dict, list, tuple))


def percent(rule: str, v, unit) -> str | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or unit is not None or not (0 < v < 1):
        return None
    if not (rule.endswith("_pct") or "_pct_" in rule or any(w in rule for w in PCT_WORDS)):
        return None
    d = (Decimal(repr(v)) * 100).normalize()
    return format(d, "f") + "%"


def compact(v) -> str:
    """One-line JSON of a value (sorted keys): the Markdown and table-cell form of dicts and lists."""
    if is_scalar(v):
        return scalar(v)
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(", ", ": "))


def value_html(v) -> str:
    if isinstance(v, dict):
        rows = "".join(f"<tr><th>{esc(k)}</th><td>{value_html(v[k])}</td></tr>" for k in sorted(v, key=str))
        return f'<table class="kv">{rows}</table>'
    if isinstance(v, (list, tuple)):
        if not v:
            return "<code>[]</code>"
        if all(isinstance(x, dict) for x in v):
            keys = sorted({k for x in v for k in x}, key=str)
            head = "".join(f"<th>{esc(k)}</th>" for k in keys)
            body = "".join("<tr>" + "".join(f"<td>{value_html(x[k]) if k in x else ''}</td>" for k in keys) + "</tr>"
                           for x in v)
            return f"<table><tr>{head}</tr>{body}</table>"
        if all(is_scalar(x) for x in v):
            return "<code>[" + ", ".join(esc(scalar(x)) for x in v) + "]</code>"
        return "<ol>" + "".join(f"<li>{value_html(x)}</li>" for x in v) + "</ol>"
    return f"<code>{esc(scalar(v))}</code>"


def record_value_html(r) -> str:
    out = value_html(r.value)
    p = percent(r.rule, r.value, r.unit)
    return out + (f" <span class=\"muted\">({esc(p)})</span>" if p else "")


def record_value_md(r) -> str:
    p = percent(r.rule, r.value, r.unit)
    return "`" + compact(r.value).replace("`", "'") + "`" + (f" ({p})" if p else "")


def cell_md(s) -> str:
    return " ".join(str(s).split()).replace("|", "\\|")


def table_html(head: list, rows: list) -> str:
    """rows hold pre-rendered HTML cells."""
    h = "".join(f"<th>{esc(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="wrap"><table><tr>{h}</tr>{b}</table></div>'


def table_md(head: list, rows: list) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(cell_md(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


PYPI_URL = "https://pypi.org/project/marina-rules/"
REPO_URL = "https://github.com/David-Marina/marina-rules"
DATA_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
SITE_NAME_ZH = "交易制度历史数据"
ZH_VALUES = "有记录以来的取值"     # the first date in the line is where Marina's records begin, not a date of change


# --- Chinese names and the line of values under the heading -------------------------------------------------------
def zh_names() -> dict:
    with open(os.path.join(ROOT, "scripts", "site_zh.json"), encoding="utf-8") as fh:
        return json.load(fh)


def zh_join(a: str, b: str) -> str:
    """Two names as one phrase: no space where two CJK characters meet (创业板 + 涨跌幅限制), a space otherwise."""
    return a + ("" if CJK_RE.match(a[-1:]) and CJK_RE.match(b[:1]) else " ") + b


def zh_markets(zh: dict, markets) -> str:
    """'XSHG+XSHE' / ['XSHE', 'XSHG+XSHE'] → 上交所、深交所 (each exchange once, in order of appearance)."""
    names = []
    for mk in ([markets] if isinstance(markets, str) else markets):
        for m in mk.split("+"):
            if zh["market"][m] not in names:
                names.append(zh["market"][m])
    return "、".join(names)


def zh_value(zh: dict, rule: str, v, unit) -> str | None:
    """A record value as it is written in the Chinese line: a percentage where the page shows one (a zero of such
    a rule is 0%), a plain number with its unit, or 'unlimited' of a price-limit rule. None for anything else
    (tables, flags, other words): such a page gets no line of values."""
    if isinstance(v, bool):
        return None
    if isinstance(v, str):
        return "不设涨跌幅限制" if v == "unlimited" and rule.startswith("price_limit_pct") else None
    if not isinstance(v, (int, float)):
        return None
    pct = percent(rule, v, unit)
    if pct:
        return pct
    if v == 0 and percent(rule, 0.5, unit):
        return "0%"
    num = format(Decimal(repr(v)).normalize(), "f") if isinstance(v, float) else str(v)
    return num + (f" {zh['unit'].get(unit, unit)}" if unit else "")


def zh_runs(zh: dict, rs: list) -> list | None:
    """[(effective_from, value text, market)] for records that follow one another, neighbours with the same value AND
    market merged — or None when the series is not a plain one: a record with a contract selector, a value zh_value
    does not write, an interval that does not start where the previous one ended, or a last record that has ended."""
    rs = sorted(rs, key=lambda r: r.effective_from)
    runs, prev = [], None
    for r in rs:
        text = None if r.contracts else zh_value(zh, r.rule, r.value, r.unit)
        if text is None or (prev is not None and prev.effective_to != r.effective_from):
            return None
        if not runs or runs[-1][1:] != (text, r.market):
            runs.append((r.effective_from, text, r.market))
        prev = r
    return runs if prev is not None and prev.effective_to is None else None


def zh_fact(zh: dict, pfx: str, scope: str, rule: str, rs: list) -> dict:
    """Chinese name, title part, description sentence and visible line of one fact page."""
    name = zh_join(zh["scope"][scope], zh["rule"][rule])
    by_market: dict = defaultdict(list)
    for r in rs:
        by_market[r.market].append(r)
    # one series when the page's records follow one another whatever their market strings (a rule later extended to
    # another exchange): each step then names its exchanges. Otherwise one series per market string, and only if
    # every market has one.
    whole = zh_runs(zh, rs)
    series = {None: whole} if whole else {mk: zh_runs(zh, v) for mk, v in sorted(by_market.items())}
    first = min(r.effective_from for r in rs)
    where = zh_markets(zh, sorted(by_market))
    title = name
    values = short = ""
    if all(series.values()):
        def one(runs):
            named = len({mk for _f, _t, mk in runs}) > 1
            return "；".join(f"{frm} 起 {text}" + (f"（{zh_markets(zh, mk)}）" if named else "") for frm, text, mk in runs)
        if len(series) == 1:
            runs = next(iter(series.values()))
            k = len(runs) - 1                    # the step at which the value became the present one
            while k > 0 and runs[k - 1][1] == runs[-1][1]:
                k -= 1
            # a title dates a change of value; where the records hold one value only, their first date is where the
            # records begin, not when the value began, so it is left out
            title = f"{name}：{runs[k - 1][1]}→{runs[-1][1]}，{runs[k][0]} 起" if k > 0 else f"{name}：{runs[-1][1]}"
            values = one(runs)
            short = values if len(runs) <= 6 else f"{one(runs[:1])}；……；{one(runs[-3:])}"
        else:
            values = short = "；".join(f"{zh_markets(zh, mk)}：{one(runs)}" for mk, runs in series.items())
    tail = (f"共 {len(rs)} 条记录，记录从 {first} 开始；每条附官方文件出处和原文引文。"
            "按交易日查询时，没有记录的日期会报错，不给默认值。")
    return {"name": name, "title": title,
            "line": f"{name}（{where}）" + (f"{ZH_VALUES}：{values}。" if values else "：") + tail,
            "description": f"{name}（{where}）" + (f"{ZH_VALUES}：{short}。" if short else "：") + tail}


def json_ld(obj: dict) -> str:
    """A JSON-LD data block. '<' is written as \\u003c so that no text of a record can close the element."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")


def dataset_ld(name: str, description: str, *, base_url: str | None, path: str, extra: dict) -> dict:
    d = {"@context": "https://schema.org", "@type": "Dataset", "name": name, "description": description,
         "license": DATA_LICENSE_URL, "isAccessibleForFree": True, "version": mr.VERSION,
         "inLanguage": ["en", "zh"],
         "creator": {"@type": "Organization", "name": "marina-rules", "url": REPO_URL}}
    if base_url:
        d["url"] = base_url + ("" if path == "index.html" else path)
    d.update(extra)
    return d


def page(title: str, h1: str, body: str, *, path: str, description: str, nav: list, base_url: str | None,
         zh_line: str | None = None, ld: dict | None = None, lang: str = "en",
         alternates: dict | None = None) -> str:
    """nav: [(label, site-relative target path or None)]. zh_line: plain Chinese text shown under the heading.
    ld: a schema.org object written as a JSON-LD data block."""
    crumbs = " / ".join(f'<a href="{esc(rel(path, t))}">{esc(lab)}</a>' if t else esc(lab) for lab, t in nav)
    canon = f'<link rel="canonical" href="{esc(base_url + path)}">\n' if base_url else ""
    if base_url:
        canon += "".join(f'<link rel="alternate" hreflang="{esc(code)}" href="{esc(base_url + target)}">\n'
                         for code, target in (alternates or {}).items())
    og = [("og:type", "website"), ("og:site_name", "marina-rules"), ("og:title", title),
          ("og:description", description), ("og:locale", "zh_CN" if lang == "zh-CN" else "en_US"),
          ("og:locale:alternate", "en_US" if lang == "zh-CN" else "zh_CN")]
    if base_url:
        og.append(("og:url", base_url + path))
    card = "".join(f'<meta property="{k}" content="{esc(v)}">\n' for k, v in og)
    card += '<meta name="twitter:card" content="summary">\n'
    data = f'<script type="application/ld+json">{json_ld(ld)}</script>\n' if ld else ""
    zh_p = f'<p lang="zh">{esc(zh_line)}</p>\n' if zh_line else ""
    return (f'<!doctype html>\n<html lang="{esc(lang)}">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{esc(title)}</title>\n<meta name=\"description\" content=\"{esc(description)}\">\n{canon}"
            f"{card}{data}"
            f"<style>\n{CSS}\n</style>\n</head>\n<body>\n<main>\n<nav>{crumbs}</nav>\n<h1>{esc(h1)}</h1>\n{zh_p}"
            f"{body}\n<p>marina-rules — point-in-time trading rules as data. "
            f'<a href="{PYPI_URL}">Install from PyPI</a> · <a href="{REPO_URL}">source, data and how to cite</a> · '
            f"CC0 data, MIT code.</p>\n</main>\n</body>\n</html>\n")


def rel(src_page: str, target: str) -> str:
    """Relative link from the page at site path src_page to the file at site path target."""
    return posixpath.relpath(target, posixpath.dirname(src_page) or ".")


def iv(frm, to) -> tuple:
    return (frm if frm else "open", to if to else "open")


# --- the model ----------------------------------------------------------------------------------------------------
def _contract_code(r) -> str | None:
    """A contract code the record's selector covers on its effective_from: a named code if the selector lists one,
    else the first <product><YYMM> from that month on (marina_rules.contract_matches decides)."""
    if not r.contracts:
        return None
    product = r.scope.split("_", 1)[1]
    named = sorted({c for clause in (r.contracts.get("any") or []) for c in ((clause.get("code") or {}).get("in") or [])})
    y, m = int(r.effective_from[:4]), int(r.effective_from[5:7])
    cands = named + [f"{product}{(y + (m - 1 + k) // 12) % 100:02d}{(m - 1 + k) % 12 + 1:02d}" for k in range(61)]
    for code in cands:
        try:
            if mr.contract_matches(r.contracts, code, r.effective_from, r.scope):
                return code
        except ValueError:
            continue
    return None


def latest(recs: list):
    return max(recs, key=lambda r: (r.effective_from, r.market or "", r.id))


def questions() -> list:
    """Titles and selectors only; no rule values, dates or sources may be supplied here."""
    qs = json.loads(_read("scripts/site_questions.json"))
    seen = set()
    for q in qs:
        if set(q) != {"slug", "zh", "en", "targets"}:
            raise ValueError("question must contain only slug, zh, en, targets")
        slug = q["slug"]
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", slug) or slug in seen:
            raise ValueError(f"duplicate or unsafe question slug: {slug}")
        seen.add(slug)
        if any(not q[lang].strip() or any(c.isdigit() for c in q[lang]) for lang in ("zh", "en")):
            raise ValueError(f"question titles must be nonempty and contain no digits: {slug}")
        if not q["targets"]:
            raise ValueError(f"question has no targets: {slug}")
        for t in q["targets"]:
            if set(t) != {"prefix", "scope", "rule", "market"}:
                raise ValueError(f"invalid question target: {slug}")
    return qs


def question_series(q: dict, recs: list) -> list:
    """[(exchange, records)] with continuous coverage through an open-ended record.

    Targets name an individual exchange; a combined-market record applies to each named exchange.
    Ended targets may join a unique successor with the same scope or rule at exactly the boundary
    (e.g. IPO scope changes, or transfer fees changing their calculation basis). Never fill a hole.
    """
    streams, seen = [], set()
    for t in q["targets"]:
        key = tuple(t[k] for k in ("prefix", "scope", "rule", "market"))
        if key in seen:
            raise ValueError(f"duplicate target: {q['slug']} {key}")
        seen.add(key)
        rs = sorted((r for r in recs if r.file.split("/", 1)[0] == t["prefix"]
                     and r.scope == t["scope"] and r.rule == t["rule"]
                     and t["market"] in r.market.split("+")), key=lambda r: (r.effective_from, r.id))
        if (not rs or any(r.contracts for r in rs)
                or any(a.effective_to != b.effective_from for a, b in zip(rs, rs[1:]))):
            raise ValueError(f"missing, conditional or broken question history: {q['slug']} {key}")
        streams.append((t["market"], rs))
    while any(rs[-1].effective_to is not None for _, rs in streams):
        for i, (mk, rs) in enumerate(streams):
            end = rs[-1]
            if end.effective_to is None:
                continue
            successors = [j for j, (other_mk, other) in enumerate(streams)
                          if i != j and mk == other_mk and end.effective_to == other[0].effective_from
                          and end.file.split("/", 1)[0] == other[0].file.split("/", 1)[0]
                          and (end.scope == other[0].scope or end.rule == other[0].rule)]
            if len(successors) != 1:
                raise ValueError(f"no unique open-ended continuation: {q['slug']} {mk} {end.id}")
            j = successors[0]
            streams[i] = (mk, rs + streams[j][1])
            del streams[j]
            break
    return streams


def question_records(series: list) -> list:
    """A shared record appears once in the history table, even when it covers multiple exchanges."""
    unique = {r.id: r for _, rs in series for r in rs}
    return sorted(unique.values(), key=lambda r: (r.scope, r.rule, r.market, r.effective_from, r.id))


def _pct_text(v) -> str:
    return format((Decimal(repr(v)) * 100).normalize(), "f") + "%"


def _session_text(v: dict, chinese: bool) -> str | None:
    """A session_schedule value in words: opening call, continuous trading, closing call (the record's own times)."""
    keys = {"open_call", "continuous", "close_call"}
    if not set(v) <= keys or "continuous" not in v:
        return None
    try:
        cont = ", ".join(f"{a}–{b}" for a, b in v["continuous"])
        oc = v.get("open_call")
        cc = v.get("close_call")
        if chinese:
            parts = ([f"开盘集合竞价 {oc[0]}–{oc[1]}"] if oc else []) + [f"连续竞价 {cont.replace(', ', '、')}"]
            parts += [f"收盘集合竞价 {cc[0]}–{cc[1]}"] if cc else ["无收盘集合竞价"]
            return "，".join(parts)
        parts = ([f"opening call {oc[0]}–{oc[1]}"] if oc else []) + [f"continuous {cont}"]
        parts += [f"closing call {cc[0]}–{cc[1]}"] if cc else ["no closing call"]
        return ", ".join(parts)
    except (TypeError, ValueError, IndexError):
        return None


def answer_value(r, zh: dict, chinese: bool) -> str:
    """A record value in the words of an answer. Every number is the record's own; anything not recognised is the
    one-line JSON of the value, as in the history table."""
    v = r.value
    if isinstance(v, str) and v == "unlimited" and r.rule.startswith("price_limit_pct"):
        return "不设涨跌幅限制" if chinese else "no price limit"
    if isinstance(v, dict) and set(v) == {"up", "down"} and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                              for x in v.values()) and r.unit is None:
        up, down = _pct_text(v["up"]), _pct_text(v["down"])
        return f"上涨 {up}、下跌 {down}" if chinese else f"+{up} / −{down}"
    if isinstance(v, dict) and r.rule == "session_schedule":
        t = _session_text(v, chinese)
        if t is not None:
            return t
    if r.rule == "limit_price_rounding" and v in ROUNDING_WORDS:
        return ROUNDING_WORDS[v][chinese]
    if r.rule == "min_holding_days" and isinstance(v, int) and not isinstance(v, bool) and r.unit is None:
        return f"T+{v}"
    if chinese:
        t = zh_value(zh, r.rule, v, r.unit)
        if t is not None:
            return t
    p = percent(r.rule, v, r.unit)
    if p:
        return p
    if v == 0 and not isinstance(v, bool) and r.unit is None and percent(r.rule, 0.5, None):
        return "0%"                                       # a zero of a percentage rule (percent() leaves it out)
    return compact(v) + (f" {r.unit}" if r.unit else "")


ROUNDING_WORDS = {"half_up_2dp": ("rounded half up", "四舍五入"),
                  "toward_prev_close": ("rounded toward the previous close", "向前收盘价方向取整")}
MAX_EARLIER = 4      # an answer lists at most this many earlier values; the table below it has every record


def answer_text(series: list, zh: dict, lang: str) -> str:
    """Per exchange (and per rule, where a question has several): the value of the latest open-ended record and since
    when, then the earlier values oldest first. Adjacent records with the same scope, rule and value are one period in
    the answer (the table lists each record); beyond MAX_EARLIER earlier periods the oldest are summarised by their
    count and start date. A scope / rule is named where a series changes it (e.g. IPO first day → first five days)."""
    chinese = lang == "zh-CN"

    def label(r):
        return zh_join(zh["scope"][r.scope], zh["rule"][r.rule]) if chinese else f"{r.scope} / {r.rule}"

    several = len({(rs[-1].scope, rs[-1].rule) for _, rs in series}) > 1
    parts = []
    for market, rs in series:
        periods = []                                   # [scope, rule, value, from, to, record]
        for r in rs:
            p = periods[-1] if periods else None
            if p and (p[0], p[1], p[5].unit) == (r.scope, r.rule, r.unit) and p[2] == r.value and p[4] == r.effective_from:
                p[4] = r.effective_to
            else:
                periods.append([r.scope, r.rule, r.value, r.effective_from, r.effective_to, r])
        named = len({(p[0], p[1]) for p in periods}) > 1

        def val(p):
            v = answer_value(p[5], zh, chinese)
            if not named:
                return v
            return f"{v}（{label(p[5])}）" if chinese else f"{v} ({label(p[5])})"

        cur, earlier = periods[-1], periods[:-1]
        dropped = earlier[:-MAX_EARLIER] if len(earlier) > MAX_EARLIER else []
        shown = earlier[len(dropped):]
        head = zh_markets(zh, market) if chinese else market
        if several:
            head += ("·" + label(cur[5])) if chinese else f", {label(cur[5])}"
        if chinese:
            s = f"{head}：{cur[3]} 起为 {val(cur)}"
            if earlier:
                s += "；此前：" + "；".join(f"{p[3]} 至 {p[4]} 前为 {val(p)}" for p in shown)
                if dropped:
                    s += f"；更早还有 {len(dropped)} 个取值，自 {dropped[0][3]} 起（见下表）"
            s += "。"
        else:
            s = f"{head}: {val(cur)} since {cur[3]}"
            if earlier:
                s += "; before that: " + "; ".join(f"{val(p)} from {p[3]} until {p[4]}" for p in shown)
                if dropped:
                    s += f"; {len(dropped)} earlier values from {dropped[0][3]} (see the table)"
            s += "."
        parts.append(s)
    return " ".join(parts)


def query_snippet(r) -> str:
    code = _contract_code(r)
    py = f'mr.rule_at("{r.rule}", "{r.effective_from}", "{r.scope}", "{r.market}"'
    py += f', contract="{code}")' if code else ")"
    cli = f"marina-rules query {r.rule} {r.effective_from} {r.scope} {r.market}"
    if code:
        cli += f" --context contract={code}"
    return f"pip install marina-rules\n\nimport marina_rules as mr\n{py}\n\n{cli}"


def build(base_url: str | None = None) -> dict:
    """site path → bytes. Pure function of the data and the repository's README / docs/SCHEMA.md."""
    if base_url is not None and not base_url.endswith("/"):
        base_url += "/"
    schema_txt, readme_txt = _read("docs/SCHEMA.md"), _read("README.md")
    defs = schema_definitions(schema_txt)
    meaning = tracking_meaning(schema_txt)
    intro = readme_intro(readme_txt)
    intro_zh = readme_intro(_read("README.zh-CN.md"))[0].strip("*")
    zh = zh_names()
    levels = verification_levels(readme_txt)
    citation = mr.citation()
    recs = mr.records()

    groups: dict = defaultdict(list)
    for r in recs:
        pfx = r.file.split("/", 1)[0]
        if pfx not in PREFIXES or not NAME_RE.match(r.scope) or not NAME_RE.match(r.rule):
            raise SystemExit(f"{r.id}: unexpected family / scope / rule name for a path")
        groups[(pfx, r.scope, r.rule)].append(r)
    for k in groups:
        groups[k].sort(key=lambda r: (r.market or "", r.effective_from, r.id))
    registries = {p: mr.scopes(p) for p in PREFIXES}
    gaps = {p: sorted(mr.known_gaps(p), key=lambda g: g["gap_id"]) for p in PREFIXES}
    tracking = {p: mr.tracking_registry(p) for p in PREFIXES}

    files: dict = {}
    manifest_pages: list = []

    def fact_path(p, s, r, ext="html"):
        return f"{p}/{s}/{r}.{ext}"

    def scope_path(p, s):
        return f"{p}/{s}/index.html"

    def gap_rows_html(gs):
        return [[esc(g["gap_id"]), esc(g["market"]), esc(g["rule"]), *(esc(x) for x in iv(g["interval"]["from"], g["interval"]["to"])),
                 esc(g["severity"]), esc(g["status"]), esc(compact(g["contracts"])) if g.get("contracts") else "",
                 f'<span{lang_attr(g["reason"])}>{esc(g["reason"])}</span>'] for g in gs]

    def gap_rows_md(gs):
        return [[g["gap_id"], g["market"], g["rule"], *iv(g["interval"]["from"], g["interval"]["to"]), g["severity"],
                 g["status"], compact(g["contracts"]) if g.get("contracts") else "", g["reason"]] for g in gs]

    gap_head = ["gap", "market", "rule", "from", "to", "severity", "status", "contracts", "reason"]
    placed_gaps: dict = {}

    # ---- fact pages ----
    for (pfx, scope, rule), rs in sorted(groups.items()):
        path, mdpath = fact_path(pfx, scope, rule), fact_path(pfx, scope, rule, "md")
        markets = sorted({r.market for r in rs if r.market})
        h1 = f"{rule} · {scope} · {FAMILY[pfx]} ({', '.join(markets)})"
        zf = zh_fact(zh, pfx, scope, rule, rs)
        title = f"{zf['title']} · {h1} — marina-rules"
        first, last = min(r.effective_from for r in rs), latest(rs)
        desc_en = (f"{rule} for scope {scope} on {', '.join(markets)}: {len(rs)} point-in-time record(s) from {first}, "
                   f"each with its official source and quote. {citation}")
        desc = f"{zf['description']} {desc_en}"
        sc = registries[pfx].get(scope, {})
        b, m = [], [f"# {h1}", "", zf["line"], ""]
        for section, pairs in defs.get(rule, []):
            cells_html = "; ".join(f"{esc(col)}: {md_inline(cell)}" for col, cell in pairs)
            b.append(f'<p><strong>Definition</strong> <span class="muted">(docs/SCHEMA.md, “{esc(section)}”)</span>: '
                     f"<code>{esc(rule)}</code> — {cells_html}</p>")
            m.append(f"**Definition** (docs/SCHEMA.md, “{section}”): `{rule}` — "
                     + "; ".join(f"{col}: {cell}" for col, cell in pairs))
            m.append("")
        if sc.get("description"):
            b.append(f'<p><strong>Scope</strong> <a href="index.html"><code>{esc(scope)}</code></a>: '
                     f"{md_inline(sc['description'])}</p>")
            m += [f"**Scope** `{scope}`: {sc['description']}", ""]
        if sc.get("requires"):
            b.append("<p><strong>Required context</strong>: " + ", ".join(f"<code>{esc(x)}</code>" for x in sc["requires"]) + "</p>")
            m += ["**Required context**: " + ", ".join(f"`{x}`" for x in sc["requires"]), ""]

        # timeline
        has_contracts = any(r.contracts for r in rs)
        head = ["market", "effective_from", "effective_to", "value", "unit", "verification", "published_at", "record"]
        if has_contracts:
            head.append("contracts")
        rows_h, rows_m = [], []
        for r in rs:
            fr, to = iv(r.effective_from, r.effective_to)
            row = [esc(r.market), esc(fr), esc(to), record_value_html(r), esc(r.unit or ""), esc(r.verification),
                   esc(r.published_at or "null"), f'<a href="#{esc(r.id)}"><code>{esc(r.id)}</code></a>']
            rowm = [r.market, fr, to, record_value_md(r), r.unit or "", r.verification, r.published_at or "null",
                    f"`{r.id}`"]
            if has_contracts:
                row.append(esc(compact(r.contracts)) if r.contracts else "")
                rowm.append(compact(r.contracts) if r.contracts else "")
            rows_h.append(row)
            rows_m.append(rowm)
        b += ["<h2>Timeline</h2>", table_html(head, rows_h)]
        m += ["## Timeline", "", table_md(head, rows_m), ""]

        # records with sources
        b.append("<h2>Records and sources</h2>")
        m += ["## Records and sources", ""]
        for r in rs:
            fr, to = iv(r.effective_from, r.effective_to)
            b.append(f'<h3 id="{esc(r.id)}"><code>{esc(r.id)}</code></h3>')
            fields = [("market", esc(r.market)), ("interval", f"[{esc(fr)}, {esc(to)})"), ("value", record_value_html(r))]
            fields += [(k, esc(v)) for k, v in (("unit", r.unit), ("verification", r.verification),
                                                 ("published_at", r.published_at or "null"),
                                                 ("recorded_at", r.recorded_at), ("data file", r.file)) if v]
            if r.contracts:
                fields.append(("contracts", f"<code>{esc(compact(r.contracts))}</code>"))
            b.append("<dl>" + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in fields) + "</dl>")
            m += [f"### `{r.id}`", "", f"- market: {r.market}", f"- interval: [{fr}, {to})",
                  f"- value: {record_value_md(r)}"]
            m += [f"- {k}: {v}" for k, v in (("unit", r.unit), ("verification", r.verification),
                                              ("published_at", r.published_at or "null"),
                                              ("recorded_at", r.recorded_at), ("data file", r.file)) if v]
            if r.contracts:
                m.append(f"- contracts: `{compact(r.contracts)}`")
            if not is_scalar(r.value):
                m += ["", "```json", json.dumps(r.value, ensure_ascii=False, sort_keys=True, indent=1), "```"]
            if r.notes:
                b.append(f'<p><strong>Notes</strong>: <span{lang_attr(r.notes)}>{esc(r.notes)}</span></p>')
                m += ["", f"Notes: {' '.join(r.notes.split())}"]
            if not r.sources:
                b.append(f"<p>No sources ({esc(r.verification)}).</p>")
                m += ["", f"No sources ({r.verification})."]
            m.append("")
            items = []
            for s in r.sources:
                meta = [("publisher", s.get("publisher")), ("title", s.get("title")), ("date", s.get("date")),
                        ("kind", s.get("kind"))]
                head_h = " · ".join(f'<span{lang_attr(str(v))}>{esc(v)}</span>' for _, v in meta if v)
                url = s.get("url") or ""
                hashes = [(k, s.get(k)) for k in ("content_sha256", "hash_kind", "fetched_sha256") if s.get(k)]
                items.append(f"<li>{head_h}<br><a href=\"{esc(url)}\">{esc(url)}</a>"
                             f"<blockquote{lang_attr(s.get('quote') or '')}>{esc(s.get('quote') or '')}</blockquote>"
                             + "<br>".join(f'<span class="muted">{k}</span> <code>{esc(v)}</code>' for k, v in hashes)
                             + "</li>")
                m.append("- " + " · ".join(f"{k}: {v}" for k, v in meta if v))
                m.append(f"  - url: <{url}>")
                for k, v in hashes:
                    m.append(f"  - {k}: `{v}`")
                m.append("")
                m += ["  > " + line for line in (s.get("quote") or "").split("\n")]
                m.append("")
            if items:
                b.append('<ul class="src">' + "".join(items) + "</ul>")

        # known gaps
        gs = [g for g in gaps[pfx] if g["scope"] == scope and g["rule"] == rule]
        for g in gs:
            placed_gaps[(pfx, g["gap_id"])] = path
        b.append("<h2>Known gaps</h2>")
        m += ["## Known gaps", ""]
        if gs:
            b.append(table_html(gap_head, gap_rows_html(gs)))
            m += [table_md(gap_head, gap_rows_md(gs)), ""]
        else:
            b.append("<p>None recorded for this scope and rule.</p>")
            m += ["None recorded for this scope and rule.", ""]

        # tracking
        trows = [(mk, mr.tracked_through(mk, scope)) for mk in markets]
        b += ["<h2>Tracking</h2>",
              table_html(["market", "tracked_through"], [[esc(mk), esc(t or "untracked")] for mk, t in trows]),
              f"<p>{md_inline(meaning)} <span class=\"muted\">(docs/SCHEMA.md, “Tracking registry”)</span></p>"]
        m += ["## Tracking", "", table_md(["market", "tracked_through"], [[mk, t or "untracked"] for mk, t in trows]), "",
              meaning + " (docs/SCHEMA.md, “Tracking registry”)", ""]

        # ask it yourself
        snippet = query_snippet(last)
        req = list(sc.get("requires") or ())
        b += ["<h2>Ask it yourself</h2>",
              f"<pre><code>{esc(snippet)}</code></pre>"]
        m += ["## Ask it yourself", "", "```", snippet, "```", ""]
        if req:
            b.append("<p>The CLI answers through <code>resolve()</code>, which needs the scope's context: "
                     + ", ".join(f"<code>{esc(x)}</code>" for x in req) + " (<code>--context key=value,…</code>; "
                     "<code>marina-rules scopes</code> lists what each scope requires).</p>")
            m += ["The CLI answers through `resolve()`, which needs the scope's context: " + ", ".join(f"`{x}`" for x in req)
                  + " (`--context key=value,…`; `marina-rules scopes` lists what each scope requires).", ""]
        b += ["<h2>Cite</h2>", f"<pre><code>{esc(citation)}</code></pre>",
              f'<p class="muted">Generated from the data of marina-rules {esc(mr.VERSION)}. Same facts as text: '
              f'<a href="{esc(rule)}.md">{esc(rule)}.md</a>. Treat the exchange\'s own notice as authoritative.</p>']
        m += ["## Cite", "", "```", citation, "```", "",
              f"Generated from the data of marina-rules {mr.VERSION}. Treat the exchange's own notice as authoritative.", ""]
        nav = [("marina-rules", "index.html"), (pfx, f"{pfx}/index.html"), (scope, scope_path(pfx, scope)), (rule, None)]
        ends = [r.effective_to for r in rs]
        extra = {"alternateName": zf["name"], "citation": citation, "spatialCoverage": FAMILY[pfx],
                 "temporalCoverage": f"{first}/" + (".." if None in ends else max(ends)),
                 "keywords": [rule, scope, *markets, zh["rule"][rule], zh["scope"][scope], "point-in-time trading rules"],
                 "isBasedOn": sorted({s["url"] for r in rs for s in r.sources if s.get("url")}),
                 "isPartOf": {"@type": "Dataset", "name": "marina-rules", "url": base_url or REPO_URL}}
        if base_url:
            extra["distribution"] = [{"@type": "DataDownload", "encodingFormat": "text/markdown",
                                      "contentUrl": base_url + mdpath}]
        files[path] = page(title, h1, "\n".join(b), path=path, description=desc, nav=nav, base_url=base_url,
                           zh_line=zf["line"], ld=dataset_ld(h1, desc, base_url=base_url, path=path, extra=extra))
        files[mdpath] = "\n".join(m).rstrip("\n") + "\n"
        manifest_pages.append({"path": path, "md": mdpath, "kind": "fact", "prefix": pfx, "scope": scope, "rule": rule,
                               "title": title, "name_zh": zf["name"], "record_ids": [r.id for r in rs],
                               "gap_ids": [g["gap_id"] for g in gs]})

    # ---- bilingual questions ----
    qs = questions()
    for q in qs:
        series = question_series(q, recs)
        rs = question_records(series)
        triples = sorted({(r.file.split("/", 1)[0], r.scope, r.rule) for r in rs})
        qgaps = [(p, g) for p, s, rule in triples for g in gaps[p] if g["scope"] == s and g["rule"] == rule]
        enpath, zhpath = f"q/{q['slug']}.html", f"zh/q/{q['slug']}.html"
        alternates = {"en": enpath, "zh-CN": zhpath, "x-default": enpath}
        for lang, path in (("en", enpath), ("zh-CN", zhpath)):
            chinese = lang == "zh-CN"
            title = q["zh" if chinese else "en"]
            answer = answer_text(series, zh, lang)
            mdpath = path.removesuffix(".html") + ".md"
            history, facts_label, ask, gap_label, context = (("历史记录", "规则详情", "安装和查询", "已知缺口", "适用范围和所需上下文")
                                                          if chinese else
                                                          ("History", "Fact pages", "Ask it yourself", "Known gaps", "Scope and required context"))
            head = (["生效日期", "失效日期（不含）", "取值", "市场", "核验状态", "记录标识", "来源", "范围", "规则", "单位"]
                    if chinese else ["effective_from", "effective_to (exclusive)", "value", "market", "verification",
                                     "record id", "source", "scope", "rule", "unit"])
            rows_h, rows_m = [], []
            for r in rs:
                fr, to = iv(r.effective_from, r.effective_to)
                translated = zh_value(zh, r.rule, r.value, r.unit) if chinese else None
                value = record_value_html(r) + (f" · {esc(translated)}" if translated is not None else "")
                valuemd = record_value_md(r) + (f" · {translated}" if translated is not None else "")
                market = zh_markets(zh, r.market) if chinese else r.market
                scope_name = zh["scope"][r.scope] if chinese else r.scope
                rule_name = zh["rule"][r.rule] if chinese else r.rule
                src_h = "<br>".join(f'<a href="{esc(s["url"])}">{esc(s["title"])}</a>' for s in r.sources)
                # Angle-delimited destinations accommodate source URLs containing parentheses.
                src_m = "; ".join(f'[{s["title"]}](<{s["url"]}>)' for s in r.sources)
                rows_h.append([esc(fr), esc(to), value, esc(market), esc(r.verification),
                               f'<code>{esc(r.id)}</code>', src_h, esc(scope_name), esc(rule_name), esc(r.unit or "")])
                rows_m.append([fr, to, valuemd, market, r.verification, f"`{r.id}`", src_m, scope_name, rule_name, r.unit or ""])
            b = [f'<p class="answer">{esc(answer)}</p>', f"<h2>{history}</h2>", table_html(head, rows_h),
                 f"<h2>{facts_label}</h2>"]
            m = [f"# {title}", "", answer, "", f"## {history}", "", table_md(head, rows_m), "", f"## {facts_label}", ""]
            links = []
            for p, s, rule in triples:
                label = zh_join(zh["scope"][s], zh["rule"][rule]) if chinese else f"{s} / {rule}"
                links.append(f'<li><a href="{esc(rel(path, fact_path(p, s, rule)))}">{esc(label)}</a></li>')
                m.append(f"- [{label}]({rel(mdpath, fact_path(p, s, rule, 'md'))})")
            b.append("<ul>" + "".join(links) + "</ul>")
            snippet = query_snippet(latest(rs))
            b += [f"<h2>{ask}</h2>", f"<pre><code>{esc(snippet)}</code></pre>", f"<h2>{gap_label}</h2>"]
            m += ["", f"## {ask}", "", "```", snippet, "```", "", f"## {gap_label}", ""]
            if qgaps:
                b.append(table_html(gap_head, gap_rows_html([g for _, g in qgaps])))
                m += [table_md(gap_head, gap_rows_md([g for _, g in qgaps])), ""]
            else:
                no_gaps = "这些范围和规则暂无已记录的缺口。" if chinese else "None recorded for these scopes and rules."
                b.append(f"<p>{no_gaps}</p>")
                m += [no_gaps, ""]
            b.append(f"<h2>{context}</h2>")
            m += [f"## {context}", ""]
            for p, s in sorted({(p, s) for p, s, _ in triples}):
                sc = registries[p][s]
                # Copy applicability constraints instead of inferring them from a question title.
                b += [f"<h3>{esc(zh['scope'][s] if chinese else s)}</h3>", f"<p>{md_inline(sc['description'])}</p>",
                      value_html({k: sc[k] for k in ("requires", "asserts", "rule_asserts") if k in sc})]
                m += [f"### {s}", "", sc["description"], "", "```json",
                      json.dumps({k: sc[k] for k in ("requires", "asserts", "rule_asserts") if k in sc},
                                 ensure_ascii=False, sort_keys=True, indent=1), "```", ""]
            b.append(f'<p><a href="{esc(rel(path, mdpath))}">Markdown</a> · '
                     f'<a href="{esc(rel(path, enpath if chinese else zhpath))}">{"English" if chinese else "中文"}</a></p>')
            ld = {"@context": "https://schema.org", "@type": "FAQPage", "inLanguage": lang,
                  "mainEntity": [{"@type": "Question", "name": title,
                                  "acceptedAnswer": {"@type": "Answer", "text": answer}}]}
            files[path] = page(title, title, "\n".join(b), path=path, description=answer,
                               nav=[("marina-rules", "zh/index.html" if chinese else "index.html"),
                                    ("常见问题" if chinese else "Questions", "zh/index.html" if chinese else "q/index.html")],
                               base_url=base_url, lang=lang, alternates=alternates, ld=ld)
            files[mdpath] = "\n".join(m).rstrip() + "\n"
            manifest_pages.append({"path": path, "md": mdpath, "kind": "question", "slug": q["slug"], "lang": lang,
                                   "title": title, "record_ids": [r.id for r in rs],
                                   "question_gaps": [{"prefix": p, "gap_id": g["gap_id"]} for p, g in qgaps]})

    def question_list(path, chinese=False):
        return "<ul>" + "".join(f'<li><a href="{esc(rel(path, ("zh/" if chinese else "") + "q/" + q["slug"] + ".html"))}">'
                                 f'{esc(q["zh" if chinese else "en"])}</a></li>' for q in qs) + "</ul>"

    files["q/index.html"] = page("Questions — marina-rules", "Questions", question_list("q/index.html"),
                                  path="q/index.html", description="Questions", nav=[("marina-rules", "index.html")],
                                  base_url=base_url)
    manifest_pages.append({"path": "q/index.html", "kind": "questions_index"})
    zh_intro = readme_opening(_read("README.zh-CN.md"))
    zh_body = [f"<p>{md_inline(p)}</p>" for p in zh_intro]
    zh_body += ["<h2>常见问题</h2>", question_list("zh/index.html", True), "<h2>市场</h2>",
                "<ul>" + "".join(f'<li><a href="../{p}/index.html">{esc(zh["family"][p])}</a></li>' for p in PREFIXES) + "</ul>"]
    home_alternates = {"en": "index.html", "zh-CN": "zh/index.html", "x-default": "index.html"}
    files["zh/index.html"] = page(SITE_NAME_ZH, SITE_NAME_ZH, "\n".join(zh_body), path="zh/index.html",
                                  description=intro_zh, nav=[("marina-rules", "index.html")], base_url=base_url,
                                  lang="zh-CN", alternates=home_alternates)
    manifest_pages.append({"path": "zh/index.html", "kind": "landing", "lang": "zh-CN"})

    # ---- scope pages ----
    scopes_by_pfx = {p: sorted(set(registries[p]) | {s for (q, s, _r) in groups if q == p}) for p in PREFIXES}
    for pfx in PREFIXES:
        for scope in scopes_by_pfx[pfx]:
            path = scope_path(pfx, scope)
            sc = registries[pfx].get(scope, {})
            rules = sorted(r for (q, s, r) in groups if q == pfx and s == scope)
            h1 = f"{scope} · {FAMILY[pfx]} — scope"
            b = []
            if sc.get("description"):
                b.append(f"<p>{md_inline(sc['description'])}</p>")
            b.append("<dl><dt>required context</dt><dd>"
                     + (", ".join(f"<code>{esc(x)}</code>" for x in sc.get("requires") or ()) or "none") + "</dd>"
                     "<dt>excludes</dt><dd>"
                     + (", ".join((f'<a href="{esc(rel(path, scope_path(pfx, x)))}"><code>{esc(x)}</code></a>'
                                   if x in scopes_by_pfx[pfx] else f"<code>{esc(x)}</code>") for x in sc.get("excludes") or ())
                        or "none") + "</dd></dl>")
            rows, shown = [], []
            for rule in rules:
                rs = groups[(pfx, scope, rule)]
                for mk in sorted({r.market for r in rs}):
                    lr = latest([r for r in rs if r.market == mk])
                    shown.append(lr.id)
                    fr, to = iv(lr.effective_from, lr.effective_to)
                    v = esc(compact(lr.value)) if not is_scalar(lr.value) else esc(scalar(lr.value))
                    p = percent(lr.rule, lr.value, lr.unit)
                    rows.append([f'<a href="{esc(rule)}.html"><code>{esc(rule)}</code></a>', esc(mk),
                                 f"<code>{v}</code>" + (f' <span class="muted">({esc(p)})</span>' if p else "")
                                 + (f" {esc(lr.unit)}" if lr.unit else ""),
                                 esc(fr), esc(to), esc(lr.verification), esc(str(len([r for r in rs if r.market == mk]))),
                                 esc(compact(lr.contracts)) if lr.contracts else ""])
            b.append("<h2>Rules</h2>")
            if rows:
                b.append("<p class=\"muted\">Latest record per rule and market (by effective_from); every record is on "
                         "the rule's page.</p>")
                b.append(table_html(["rule", "market", "latest value", "effective_from", "effective_to", "verification",
                                     "records", "contracts"], rows))
            else:
                b.append("<p>No records under this scope.</p>")
            lone = [g for g in gaps[pfx] if g["scope"] == scope and (pfx, scope, g["rule"]) not in groups]
            for g in lone:
                placed_gaps[(pfx, g["gap_id"])] = path
            if lone:
                b += ["<h2>Known gaps for rules with no records here</h2>", table_html(gap_head, gap_rows_html(lone))]
            nav = [("marina-rules", "index.html"), (pfx, f"{pfx}/index.html"), (scope, None)]
            sz = zh["scope"][scope]
            zline = (f"{sz}（{zh['family'][pfx]}）的交易规则：" + "、".join(zh["rule"][r] for r in rules) + "。" if rules
                     else f"{sz}（{zh['family'][pfx]}）：该范围下暂无规则记录。")
            files[path] = page(f"{sz}交易规则 · {h1} — marina-rules" if CJK_RE.match(sz[-1:]) else
                               f"{sz} 交易规则 · {h1} — marina-rules", h1, "\n".join(b), path=path, base_url=base_url,
                               nav=nav, zh_line=zline,
                               description=f"{zline} Scope {scope} ({FAMILY[pfx]}): {len(rules)} rule(s) with "
                                           f"point-in-time records and sources. {citation}")
            manifest_pages.append({"path": path, "kind": "scope", "prefix": pfx, "scope": scope, "rules": rules,
                                   "gap_ids": [g["gap_id"] for g in lone], "record_ids": shown})

    # ---- family indexes ----
    for pfx in PREFIXES:
        path = f"{pfx}/index.html"
        h1 = f"{FAMILY[pfx]} — scopes and rules"
        rows = []
        for scope in scopes_by_pfx[pfx]:
            sc = registries[pfx].get(scope, {})
            n = len([1 for (q, s, _r) in groups if q == pfx and s == scope])
            rows.append([f'<a href="{esc(rel(path, scope_path(pfx, scope)))}"><code>{esc(scope)}</code></a>',
                         f'<span lang="zh">{esc(zh["scope"][scope])}</span>',
                         md_inline(sc.get("description") or ""),
                         ", ".join(f"<code>{esc(x)}</code>" for x in sc.get("requires") or ()), esc(str(n))])
        n_rec = sum(len(v) for (q, _s, _r), v in groups.items() if q == pfx)
        b = [f"<p>{esc(str(n_rec))} records in <code>data/{esc(pfx)}/</code>, "
             f"{esc(str(len([1 for k in groups if k[0] == pfx])))} rule pages, "
             f"{esc(str(len(gaps[pfx])))} known gaps.</p>",
             "<h2>Scopes</h2>", table_html(["scope", "中文名", "description", "required context", "rules"], rows),
             "<h2>Tracking registry</h2>"]
        if tracking[pfx]:
            b.append(table_html(["market", "scopes", "tracked_through", "basis"],
                                [[esc(e["market"]), esc(", ".join(e["scopes"])) if e.get("scopes") else "all",
                                  esc(e["tracked_through"]), esc(e["basis"])] for e in tracking[pfx]]))
        b.append(f"<p>{md_inline(meaning)} <span class=\"muted\">(docs/SCHEMA.md, “Tracking registry”)</span></p>")
        orphan = [g for g in gaps[pfx] if (pfx, g["gap_id"]) not in placed_gaps]
        for g in orphan:
            placed_gaps[(pfx, g["gap_id"])] = path
        if orphan:
            b += ["<h2>Known gaps for scopes not in the registry</h2>", table_html(gap_head, gap_rows_html(orphan))]
        nav = [("marina-rules", "index.html"), (pfx, None)]
        fz = f"{zh['family'][pfx]}市场交易制度历史数据：按生效日期记录的交易规则，每条附官方出处。"
        files[path] = page(f"{zh['family'][pfx]}交易规则历史数据 · {h1} — marina-rules", h1, "\n".join(b), path=path,
                           base_url=base_url, nav=nav, zh_line=fz,
                           description=f"{fz} Point-in-time trading rules for {FAMILY[pfx]}, as data. {citation}")
        manifest_pages.append({"path": path, "kind": "family", "prefix": pfx, "gap_ids": [g["gap_id"] for g in orphan]})

    # ---- root ----
    fam_counts = {p: sum(len(v) for (q, _s, _r), v in groups.items() if q == p) for p in PREFIXES}
    ver_counts = dict(sorted(Counter(r.verification for r in recs).items()))
    lvl = dict(levels)
    b = [f"<p><strong>{md_inline(intro[0].strip('*'))}</strong> {md_inline(intro[1])}</p>",
         f"<pre><code>{esc(citation)}</code></pre>",
         '<h2>常见问题 / Questions</h2><p><a href="q/index.html">English questions</a> · '
         '<a href="zh/index.html">中文问题与介绍</a></p>',
         "<h2>Market families</h2>",
         table_html(["family", "records", "rule pages", "scopes"],
                    [[f'<a href="{p}/index.html">{esc(FAMILY[p])} (<code>{p}</code>)</a> '
                      f'<span lang="zh">{esc(zh["family"][p])}</span>', esc(str(fam_counts[p])),
                      esc(str(len([1 for k in groups if k[0] == p]))), esc(str(len(scopes_by_pfx[p])))] for p in PREFIXES]),
         "<h2>Verification levels</h2>",
         table_html(["level", "records", "meaning (README)"],
                    [[f"<code>{esc(k)}</code>", esc(str(v)), md_inline(lvl.get(k, ""))] for k, v in ver_counts.items()]),
         "<h2>Install and query</h2>",
         "<pre><code>pip install marina-rules\nmarina-rules query &lt;rule&gt; &lt;date&gt; &lt;scope&gt; [market]"
         "</code></pre>",
         '<p>Every rule page as text: <a href="llms.txt">llms.txt</a>. Manifest: <a href="site.json">site.json</a>.</p>']
    root_desc = intro_zh + " " + re.sub(r"[*`]", "", intro[0] + " " + intro[1])
    root_extra = {"alternateName": f"Marina：{SITE_NAME_ZH}", "citation": citation, "sameAs": [REPO_URL, PYPI_URL],
                  "keywords": ["point-in-time trading rules", "backtesting", "China A-shares", "price limit",
                               "stamp duty", "tick size", "交易制度", "涨跌停", "涨跌幅限制", "印花税", "最小报价单位",
                               "回测"]}
    if base_url:
        root_extra["distribution"] = [{"@type": "DataDownload", "encodingFormat": "application/json",
                                       "contentUrl": base_url + "site.json"}]
    files["index.html"] = page(f"marina-rules — point-in-time trading rules · {SITE_NAME_ZH}（涨跌停、印花税、最小报价单位）",
                               "marina-rules", "\n".join(x for x in b if x), path="index.html", base_url=base_url,
                               nav=[("marina-rules", None)], zh_line=intro_zh, description=root_desc,
                               alternates=home_alternates,
                               ld=dataset_ld("marina-rules", root_desc, base_url=base_url, path="index.html",
                                             extra=root_extra))
    manifest_pages.append({"path": "index.html", "kind": "root"})

    # ---- llms.txt ----
    def url(p):
        return (base_url + p) if base_url else p
    facts = [x for x in manifest_pages if x["kind"] == "fact"]
    lt = ["# marina-rules", "", "> " + re.sub(r"[*`]", "", intro[0] + " " + intro[1]), "",
          citation, "", "Install and query:", "", "    pip install marina-rules",
          "    marina-rules query <rule> <date> <scope> [market]", "",
          "## Market families", ""]
    lt += [f"- [{FAMILY[p]} ({p})]({url(p + '/index.html')})" for p in PREFIXES]
    lt += [f"- [中文介绍与问题]({url('zh/index.html')})", f"- [English questions]({url('q/index.html')})",
           "", "## Questions", ""]
    lt += [f"- [{x['title']}]({url(x['md'])})" for x in manifest_pages if x["kind"] == "question"]
    lt += ["", "## Rule pages (Markdown)", ""]
    lt += [f"- [{x['rule']} · {x['scope']} · {x['prefix']}]({url(x['md'])}): {x['name_zh']}" for x in facts]
    files["llms.txt"] = "\n".join(lt) + "\n"

    if base_url:
        by_id = {r.id: r for r in recs}
        dataset_lastmod = max(r.recorded_at for r in recs)
        lastmods = {p["path"]: max((by_id[rid].recorded_at for rid in p.get("record_ids", [])),
                                   default=dataset_lastmod) for p in manifest_pages}
        locs = sorted(p for p in files if p.endswith(".html"))
        files["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                + "".join(f"<url><loc>{esc(base_url + p)}</loc><lastmod>{esc(lastmods[p])}</lastmod></url>\n"
                                          for p in locs) + "</urlset>\n")
        files["robots.txt"] = f"User-agent: *\nAllow: /\nSitemap: {base_url}sitemap.xml\n"

    missing = [k for p in PREFIXES for k in ((p, g["gap_id"]) for g in gaps[p]) if k not in placed_gaps]
    if missing:
        raise SystemExit(f"known gaps not placed on any page: {missing}")
    manifest_pages.sort(key=lambda x: x["path"])
    counts = {"records": len(recs), "fact_pages": len(facts), "scope_pages": sum(1 for x in manifest_pages if x["kind"] == "scope"),
              "family_pages": len(PREFIXES), "known_gaps": sum(len(gaps[p]) for p in PREFIXES),
              "questions": len(qs), "question_pages": len(qs) * 2,
              "by_family": fam_counts, "by_verification": ver_counts}
    files["site.json"] = json.dumps({"citation": citation, "version": mr.VERSION, "code_version": mr.__version__,
                                     "counts": counts,
                                     "pages": manifest_pages}, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    return {k: v.encode("utf-8") for k, v in sorted(files.items())}


def write(out: str, files: dict) -> None:
    for p, data in files.items():
        dst = os.path.join(out, *p.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(data)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write static rule fact pages generated from the data.")
    ap.add_argument("--out", default="site", help="output directory (default: site)")
    ap.add_argument("--base-url", default=None, help="absolute URL the site will be served from; enables sitemap.xml")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    files = build(a.base_url)
    write(a.out, files)
    n_fact = json.loads(files["site.json"])["counts"]["fact_pages"]
    print(f"{len(files)} files, {n_fact} rule pages, {sum(len(v) for v in files.values())} bytes "
          f"in {time.perf_counter() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
