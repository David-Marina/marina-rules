"""Write static rule fact pages: one page per (market family, scope, rule), generated from the data.

    python scripts/build_site.py --out site [--base-url https://example.org/]

Every statement about a rule on these pages is a record field, a source quote, a known gap, a tracking entry or a row
of docs/SCHEMA.md, copied verbatim; the introduction on the index is taken from README.md (and README.zh-CN.md).
Nothing is summarised and nothing depends on the date of the build: two builds of the same data are byte-identical.
Without --base-url no absolute URL of the site is written anywhere (sitemap.xml needs one, so it is written only
with --base-url).

Chinese: each page carries a Chinese name in its title, description and a line under the heading, so that it can be
found by a Chinese query. The names come from scripts/site_zh.json (display names of families, markets, scopes and
rules — never a value); the values in that line are record fields in their effective_from order, written only where
the page has one unbroken series of plain values per market. Each page also carries Open Graph tags and a schema.org
Dataset description (JSON-LD, a data block: the pages run no script).

Output: index.html, <prefix>/index.html, <prefix>/<scope>/index.html, <prefix>/<scope>/<rule>.html and .md,
llms.txt, site.json and, with --base-url, sitemap.xml and robots.txt. Known gaps whose (scope, rule) has records are on that fact
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
            head = f"{runs[k - 1][1]}→{runs[-1][1]}" if k > 0 else runs[-1][1]
            title = f"{name}：{head}，{runs[k][0]} 起"
            values = one(runs)
            short = values if len(runs) <= 6 else f"{one(runs[:1])}；……；{one(runs[-3:])}"
        else:
            values = short = "；".join(f"{zh_markets(zh, mk)}：{one(runs)}" for mk, runs in series.items())
    tail = (f"共 {len(rs)} 条按生效日期记录的规则，最早自 {first} 起；每条附官方文件出处和原文引文，"
            "可按交易日查询当日有效的规则。")
    return {"name": name, "title": title,
            "line": f"{name}（{where}）" + (f"历次取值：{values}。" if values else "：") + tail,
            "description": f"{name}（{where}）" + (f"历次调整：{short}。" if short else "历次调整记录：") + tail}


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
         zh_line: str | None = None, ld: dict | None = None) -> str:
    """nav: [(label, site-relative target path or None)]. zh_line: plain Chinese text shown under the heading.
    ld: a schema.org object written as a JSON-LD data block."""
    crumbs = " / ".join(f'<a href="{esc(rel(path, t))}">{esc(lab)}</a>' if t else esc(lab) for lab, t in nav)
    canon = f'<link rel="canonical" href="{esc(base_url + path)}">\n' if base_url else ""
    og = [("og:type", "website"), ("og:site_name", "marina-rules"), ("og:title", title),
          ("og:description", description), ("og:locale", "en_US"), ("og:locale:alternate", "zh_CN")]
    if base_url:
        og.append(("og:url", base_url + path))
    card = "".join(f'<meta property="{k}" content="{esc(v)}">\n' for k, v in og)
    card += '<meta name="twitter:card" content="summary">\n'
    data = f'<script type="application/ld+json">{json_ld(ld)}</script>\n' if ld else ""
    zh_p = f'<p lang="zh">{esc(zh_line)}</p>\n' if zh_line else ""
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
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
        code = _contract_code(last)
        py = f'mr.rule_at("{rule}", "{last.effective_from}", "{scope}", "{last.market}"'
        py += f', contract="{code}")' if code else ")"
        cli = f"marina-rules query {rule} {last.effective_from} {scope} {last.market}"
        if code:
            cli += f" --context contract={code}"
        req = list(sc.get("requires") or ())
        b += ["<h2>Ask it yourself</h2>",
              f"<pre><code>pip install marina-rules\n\nimport marina_rules as mr\n{esc(py)}\n\n{esc(cli)}</code></pre>"]
        m += ["## Ask it yourself", "", "```", "pip install marina-rules", "", "import marina_rules as mr", py, "", cli, "```", ""]
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
            rows = []
            for rule in rules:
                rs = groups[(pfx, scope, rule)]
                for mk in sorted({r.market for r in rs}):
                    lr = latest([r for r in rs if r.market == mk])
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
                                   "gap_ids": [g["gap_id"] for g in lone]})

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
    lt += ["", "## Rule pages (Markdown)", ""]
    lt += [f"- [{x['rule']} · {x['scope']} · {x['prefix']}]({url(x['md'])}): {x['name_zh']}" for x in facts]
    files["llms.txt"] = "\n".join(lt) + "\n"

    if base_url:
        locs = sorted(p for p in files if p.endswith(".html"))
        files["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                + "".join(f"<url><loc>{esc(base_url + p)}</loc></url>\n" for p in locs) + "</urlset>\n")
        files["robots.txt"] = f"User-agent: *\nAllow: /\nSitemap: {base_url}sitemap.xml\n"

    missing = [k for p in PREFIXES for k in ((p, g["gap_id"]) for g in gaps[p]) if k not in placed_gaps]
    if missing:
        raise SystemExit(f"known gaps not placed on any page: {missing}")
    manifest_pages.sort(key=lambda x: x["path"])
    counts = {"records": len(recs), "fact_pages": len(facts), "scope_pages": sum(1 for x in manifest_pages if x["kind"] == "scope"),
              "family_pages": len(PREFIXES), "known_gaps": sum(len(gaps[p]) for p in PREFIXES),
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
    n_fact = sum(1 for p in files if p.endswith(".html") and not p.endswith("index.html"))
    print(f"{len(files)} files, {n_fact} rule pages, {sum(len(v) for v in files.values())} bytes "
          f"in {time.perf_counter() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
