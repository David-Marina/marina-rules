"""Rule fact pages (scripts/build_site.py): every statement comes from the data or docs/SCHEMA.md, every record and
known gap is on exactly one page, the output is deterministic and self-contained."""
import html
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import Counter
from html.parser import HTMLParser

import pytest

import marina_rules as mr

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_spec = importlib.util.spec_from_file_location("build_site", os.path.join(ROOT, "scripts", "build_site.py"))
site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(site)

ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "main", "nav", "h1", "h2", "h3", "p", "a", "strong",
                "em", "code", "pre", "span", "div", "table", "tr", "th", "td", "ul", "ol", "li", "dl", "dt", "dd",
                "blockquote", "br", "link", "script"}
LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
ZH_LINE_RE = re.compile(r'<h1>[^<]*</h1>\n<p lang="zh">([^<]*)</p>')


def _tree(d):
    out = {}
    for base, _dirs, names in os.walk(d):
        for n in names:
            p = os.path.join(base, n)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, d).replace(os.sep, "/")] = fh.read()
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """One build through the command line (another hash seed), one in-process, one with --base-url."""
    a, b, c = (tmp_path_factory.mktemp(n) for n in ("site_a", "site_b", "site_c"))
    env = dict(os.environ, PYTHONHASHSEED="12345", PYTHONPATH=os.path.join(ROOT, "src"))
    proc = subprocess.run([sys.executable, "-B", os.path.join(ROOT, "scripts", "build_site.py"), "--out", str(a)],
                          cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    site.write(str(b), site.build())
    site.write(str(c), site.build("https://example.org/rules"))
    return {"dir": str(a), "files": _tree(str(a)), "other": _tree(str(b)), "based": _tree(str(c)),
            "stdout": proc.stdout}


@pytest.fixture(scope="module")
def manifest(built):
    return json.loads(built["files"]["site.json"])


@pytest.fixture(scope="module")
def text(built):
    return {k: v.decode("utf-8") for k, v in built["files"].items()}


def _triples():
    return {(r.file.split("/", 1)[0], r.scope, r.rule) for r in mr.records()}


def _facts(manifest):
    return [p for p in manifest["pages"] if p["kind"] == "fact"]


# --- 2, 7, 8: deterministic, complete, fast ------------------------------------------------------------------------
def test_two_builds_are_byte_identical(built):
    assert built["files"] == built["other"]


def test_fact_page_count_matches_the_data(built, manifest):
    triples = _triples()
    assert manifest["counts"]["fact_pages"] == len(triples) == len(_facts(manifest))
    assert {(p["prefix"], p["scope"], p["rule"]) for p in _facts(manifest)} == triples
    for pfx, scope, rule in triples:
        assert f"{pfx}/{scope}/{rule}.html" in built["files"] and f"{pfx}/{scope}/{rule}.md" in built["files"]
    assert manifest["counts"]["records"] == len(mr.records())
    assert manifest["citation"] == mr.citation()
    assert manifest["version"] == mr.VERSION and manifest["code_version"] == mr.__version__


def test_build_reports_pages_and_time(built):
    m = re.search(r"(\d+) files, (\d+) rule pages, \d+ bytes in ([\d.]+) s", built["stdout"])
    assert m and int(m.group(1)) == len(built["files"]) and int(m.group(2)) == len(_triples())
    assert float(m.group(3)) < 60


# --- 3: every record on exactly one page, with value, interval, sources ---------------------------------------------
def test_every_record_is_on_exactly_one_fact_page(text, manifest):
    where = Counter(i for p in _facts(manifest) for i in p["record_ids"])
    assert set(where) == {r.id for r in mr.records()} and set(where.values()) == {1}
    html_hits = Counter(m for k, t in text.items() if k.endswith(".html") for m in re.findall(r'<h3 id="([^"]+)">', t))
    md_hits = Counter(m for k, t in text.items() if k.endswith(".md") for m in re.findall(r"^### `([^`]+)`$", t, re.M))
    assert html_hits == md_hits == where


def test_record_values_intervals_sources_and_quotes_are_on_its_page(text, manifest):
    recs = {r.id: r for r in mr.records()}
    for p in _facts(manifest):
        h, md = text[p["path"]], text[p["md"]]
        for rid in p["record_ids"]:
            r = recs[rid]
            to = r.effective_to or "open"
            assert f"[{r.effective_from}, {to})" in h and f"- interval: [{r.effective_from}, {to})" in md, rid
            assert f"- value: `{site.compact(r.value)}`" in md, rid
            if site.is_scalar(r.value):
                assert f"<code>{html.escape(site.scalar(r.value))}</code>" in h, rid
            for s in r.sources:
                assert html.escape(s["url"]) in h and s["url"] in md, rid
                assert html.escape(s["quote"]) in h and s["quote"] in md, rid
                assert s["content_sha256"] in h and s["content_sha256"] in md, rid


def test_percent_rendering_keeps_the_raw_value(text):
    h = text["cn/chinext/price_limit_pct.html"]
    assert "<code>0.2</code> <span class=\"muted\">(20%)</span>" in h
    assert site.percent("stamp_duty_sell", 0.0005, None) == "0.05%"
    assert site.percent("tick_size", 0.01, "CNY") is None
    assert site.percent("min_holding_days", 1, None) is None


def test_structured_values_are_tables_not_python_reprs(text, manifest):
    recs = {r.id: r for r in mr.records()}
    n = 0
    for p in _facts(manifest):
        for rid in p["record_ids"]:
            v = recs[rid].value
            if site.is_scalar(v):
                continue
            n += 1
            assert repr(v) not in text[p["path"]] and repr(v) not in text[p["md"]], rid
            assert html.escape(repr(v)) not in text[p["path"]], rid
            assert json.dumps(v, ensure_ascii=False, sort_keys=True, indent=1) in text[p["md"]], rid
        if any(not site.is_scalar(recs[i].value) for i in p["record_ids"]):
            assert "<table class=\"kv\">" in text[p["path"]] or "<td><table>" in text[p["path"]], p["path"]
    assert n == sum(1 for r in mr.records() if not site.is_scalar(r.value))


# --- 1: statements come from the data or the docs -------------------------------------------------------------------
def test_definitions_are_verbatim_schema_rows(text, manifest):
    schema = open(os.path.join(ROOT, "docs", "SCHEMA.md"), encoding="utf-8").read()
    defs = site.schema_definitions(schema)
    for p in _facts(manifest):
        md = text[p["md"]]
        got = re.findall(r"^\*\*Definition\*\* \(docs/SCHEMA\.md, “(.+?)”\): `([a-z0-9_]+)` — (.*)$", md, re.M)
        assert [(s, r) for s, r, _ in got] == [(s, p["rule"]) for s, _ in defs.get(p["rule"], [])]
        for (_s, _r, cells), (_sec, pairs) in zip(got, defs.get(p["rule"], [])):
            assert cells == "; ".join(f"{c}: {v}" for c, v in pairs)
            for _c, v in pairs:
                assert v in schema or v.replace("|", "\\|") in schema


def test_unknown_rule_gets_no_definition():
    assert "no_such_rule" not in site.schema_definitions(open(os.path.join(ROOT, "docs", "SCHEMA.md"), encoding="utf-8").read())
    rows = site.schema_definitions("## X\n\n| rule | value | meaning |\n|---|---|---|\n| `a_b` | `x` \\| `y` | m |\n"
                                   "| `c` / `d` | v | m |\n")
    assert rows == {"a_b": [("X", [("value", "`x` | `y`"), ("meaning", "m")])]}


def test_prose_is_taken_from_readme_and_schema(text):
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    schema = open(os.path.join(ROOT, "docs", "SCHEMA.md"), encoding="utf-8").read()
    for para in site.readme_intro(readme):
        assert para in " ".join(readme.split())
    assert site.tracking_meaning(schema) in " ".join(schema.split())
    assert "carry-forward" in site.tracking_meaning(schema)
    assert site.md_inline(site.tracking_meaning(schema)) in text["cn/chinext/price_limit_pct.html"]
    assert site.tracking_meaning(schema) in text["cn/chinext/price_limit_pct.md"]


def test_tracking_dates_are_the_registry_lookup(text, manifest):
    recs = {r.id: r for r in mr.records()}
    for p in _facts(manifest):
        for mk in sorted({recs[i].market for i in p["record_ids"]}):
            t = mr.tracked_through(mk, p["scope"]) or "untracked"
            assert f"| {mk} | {t} |" in text[p["md"]], (p["path"], mk)


def test_ask_it_yourself_returns_the_latest_record(text, manifest):
    recs = {r.id: r for r in mr.records()}
    for p in _facts(manifest):
        md = text[p["md"]]
        call = next(l for l in md.split("\n") if l.startswith("mr.rule_at("))
        cli = next(l for l in md.split("\n") if l.startswith("marina-rules query "))
        last = max((recs[i] for i in p["record_ids"]), key=lambda r: (r.effective_from, r.market or "", r.id))
        assert eval(call, {"mr": mr}) == last.value, call     # noqa: S307 — generated by the build, data only
        assert cli.startswith(f"marina-rules query {p['rule']} {last.effective_from} {p['scope']} {last.market}")
        assert mr.citation() in md


# --- 4: known gaps -----------------------------------------------------------------------------------------------
def test_every_known_gap_is_placed_once_where_documented(text, manifest):
    placed = Counter((p.get("prefix"), g) for p in manifest["pages"] for g in p.get("gap_ids", []))
    allg = {(pfx, g["gap_id"]): g for pfx in ("cn", "hk", "us") for g in mr.known_gaps(pfx)}
    assert set(placed) == set(allg) and set(placed.values()) == {1}
    triples = _triples()
    for p in manifest["pages"]:
        for gid in p.get("gap_ids", []):
            g = allg[(p["prefix"], gid)]
            has_page = (p["prefix"], g["scope"], g["rule"]) in triples
            if p["kind"] == "fact":
                assert (p["scope"], p["rule"]) == (g["scope"], g["rule"])
            elif p["kind"] == "scope":
                assert not has_page and p["scope"] == g["scope"]
            else:
                assert p["kind"] == "family" and g["scope"] not in mr.scopes(p["prefix"])
            assert html.escape(gid) in text[p["path"]] and html.escape(g["reason"]) in text[p["path"]]


# --- 5, 6: well-formed, escaped, self-contained ---------------------------------------------------------------------
class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.links, self.h1, self.attrs = Counter(), [], 0, []

    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1
        self.attrs.append((tag, dict(attrs)))
        for k, v in attrs:
            if k in ("href", "src"):
                self.links.append(v)


def test_html_pages_are_well_formed_and_links_resolve(built, text):
    files = built["files"]
    for k, t in text.items():
        if not k.endswith(".html"):
            continue
        assert t.startswith('<!doctype html>\n<html lang="en">'), k
        p = _Page()
        p.feed(t)
        assert set(p.tags) <= ALLOWED_TAGS, (k, set(p.tags) - ALLOWED_TAGS)
        assert p.tags["h1"] == 1 and p.tags["title"] == 1 and p.tags["main"] == 1, k
        assert ("meta", {"charset": "utf-8"}) in p.attrs, k
        assert any(tag == "meta" and a.get("name") == "viewport" for tag, a in p.attrs), k
        assert t.count("<script") == len(LD_RE.findall(t)) <= 1, k      # a JSON-LD data block, never a script
        assert "@import" not in t and "src=" not in t, k
        anchors = set(re.findall(r' id="([^"]+)"', t))
        for href in p.links:
            if href.startswith(("http://", "https://")):
                continue
            target, _, frag = href.partition("#")
            if target:
                dest = os.path.normpath(os.path.join(os.path.dirname(k), target)).replace(os.sep, "/")
                assert dest in files, (k, href)
            else:
                assert frag in anchors, (k, href)
    for k, t in text.items():
        if k.endswith(".md") or k == "llms.txt":
            for target in re.findall(r"\]\(([^)]+)\)", t):
                dest = os.path.normpath(os.path.join(os.path.dirname(k), target)).replace(os.sep, "/")
                assert dest in files, (k, target)


def test_quotes_with_markup_characters_are_escaped(text, manifest):
    recs = {r.id: r for r in mr.records()}
    seen = Counter()
    for p in _facts(manifest):
        h = text[p["path"]]
        for rid in p["record_ids"]:
            for s in recs[rid].sources:
                q = s["quote"]
                for ch in "<&\"'":
                    if ch in q:
                        seen[ch] += 1
                        assert html.escape(q) in h
                if "<" in q:
                    assert q not in h            # the raw text would have opened a tag
    assert all(seen[ch] for ch in "<&\"'"), seen


def test_output_is_utf8_and_holds_no_local_paths(built):
    for k, v in built["files"].items():
        t = v.decode("utf-8")
        assert "/Users/" not in t and built["dir"] not in t and ROOT not in t, k
        assert k == k.lower() and " " not in k


def test_no_absolute_site_urls_without_base_url(built):
    assert "sitemap.xml" not in built["files"]
    assert not any(b"example.org" in v for v in built["files"].values())
    assert b'rel="canonical"' not in built["files"]["index.html"]


def test_base_url_adds_sitemap_and_absolute_links(built):
    based = built["based"]
    sm = based["sitemap.xml"].decode("utf-8")
    locs = re.findall(r"<loc>([^<]+)</loc>", sm)
    assert locs and all(u.startswith("https://example.org/rules/") for u in locs)
    assert len(locs) == sum(1 for k in based if k.endswith(".html"))
    assert "https://example.org/rules/cn/chinext/price_limit_pct.md" in based["llms.txt"].decode("utf-8")
    assert set(based) - {"sitemap.xml", "robots.txt"} == set(built["files"])
    assert based["robots.txt"].decode("utf-8") == "User-agent: *\nAllow: /\nSitemap: https://example.org/rules/sitemap.xml\n"
    page = built["files"]["cn/chinext/price_limit_pct.html"].decode("utf-8")
    assert "https://pypi.org/project/marina-rules/" in page and "https://github.com/David-Marina/marina-rules" in page


def test_llms_txt_lists_every_fact_page(text, manifest):
    t = text["llms.txt"]
    for p in _facts(manifest):
        assert f"]({p['md']})" in t
    for pfx in ("cn", "hk", "us"):
        assert f"]({pfx}/index.html)" in t
    assert "pip install marina-rules" in t and mr.citation() in t


def test_index_counts_match_the_data(text):
    t = text["index.html"]
    assert html.escape(mr.citation()) in t
    for level, n in Counter(r.verification for r in mr.records()).items():
        assert f"<td><code>{level}</code></td><td>{n}</td>" in t


# --- Chinese names, share cards, dataset markup ----------------------------------------------------------------------
def test_every_family_market_scope_and_rule_has_a_chinese_name_and_no_name_is_left_over():
    zh = site.zh_names()
    recs = mr.records()
    scopes = {r.scope for r in recs} | {s for p in ("cn", "hk", "us") for s in mr.scopes(p)}
    assert set(zh["scope"]) == scopes
    assert set(zh["rule"]) == {r.rule for r in recs}
    assert set(zh["market"]) == {m for r in recs for m in r.market.split("+")}
    assert set(zh["family"]) == {"cn", "hk", "us"}
    for names in (zh["scope"], zh["rule"], zh["market"], zh["family"], zh["unit"]):
        assert all(isinstance(v, str) and v.strip() == v and v for v in names.values())
    assert len(set(zh["scope"].values())) == len(zh["scope"])           # two scopes never share a name


def test_every_page_has_a_chinese_line_and_a_share_card(text, manifest):
    for k, t in text.items():
        if not k.endswith(".html"):
            continue
        line = ZH_LINE_RE.search(t)
        assert line and site.CJK_RE.search(line.group(1)), k
        title = re.search(r"<title>([^<]*)</title>", t).group(1)
        assert site.CJK_RE.search(title), k
        for prop in ("og:type", "og:site_name", "og:title", "og:description", "og:locale"):
            assert f'<meta property="{prop}" content="' in t, (k, prop)
        assert f'<meta property="og:title" content="{title}">' in t, k
        assert '<meta name="twitter:card" content="summary">' in t and "og:url" not in t, k
    for p in _facts(manifest):
        zh = site.zh_names()
        name = site.zh_join(zh["scope"][p["scope"]], zh["rule"][p["rule"]])
        assert p["name_zh"] == name and p["title"].startswith(name)
        assert html.unescape(ZH_LINE_RE.search(text[p["path"]]).group(1)) in text[p["md"]]


def test_the_chinese_title_states_the_record_values(text):
    t = text["cn/chinext/price_limit_pct.html"]
    assert "<title>创业板涨跌幅限制：10%→20%，2020-08-24 起 · price_limit_pct · chinext · China mainland (XSHE) — " in t
    assert site.ZH_VALUES + "：2009-10-30 起 10%；2020-08-24 起 20%。共 2 条记录，记录从 2009-10-30 开始" in t
    assert mr.rule_at("price_limit_pct", "2020-08-21", "chinext", "XSHE") == 0.1
    assert mr.rule_at("price_limit_pct", "2020-08-24", "chinext", "XSHE") == 0.2
    # a rule later extended to another exchange: each step names its exchanges, the title dates the change of value
    t = text["cn/stock/stamp_duty_sell.html"]
    assert "<title>A 股股票印花税（卖出）：0.1%→0.05%，2023-08-28 起 · " in t
    assert "2008-04-24 起 0.1%（上交所、深交所）；2021-11-15 起 0.1%（上交所、深交所、北交所）；" in t
    t = text["cn/stock/transfer_fee_each_side.html"]
    assert "2006-07-01 起 0.00255%（深交所）；2015-08-01 起 0.002%（上交所、深交所）" in t
    # exchanges with different values are never merged; tables and words get a name but no values
    assert "深交所：2006-07-01 起 0.01 港元；上交所：2006-07-01 起 0.001 美元" in text["cn/b_share/tick_size.html"]
    assert "<title>B 股最小报价单位 · tick_size" in text["cn/b_share/tick_size.html"]
    # one value since the records begin: the title gives the value and no date (the records' first date is not the
    # date the value began: 0.01 was the A-share tick before 2006-07-01 too, known gap G-0005)
    assert "<title>A 股股票最小报价单位：0.01 元 · tick_size · stock" in text["cn/stock/tick_size.html"]
    assert "记录从 2006-07-01 开始" in text["cn/stock/tick_size.html"]
    assert site.ZH_VALUES not in text["cn/stock/limit_price_rounding.html"]
    assert site.ZH_VALUES not in text["hk/hk_stock/tick_size_table.html"]


def test_every_value_in_a_chinese_line_is_a_record_of_that_page(text, manifest):
    recs = {r.id: r for r in mr.records()}
    zh = site.zh_names()
    seen = 0
    for p in _facts(manifest):
        line = html.unescape(ZH_LINE_RE.search(text[p["path"]]).group(1))
        if site.ZH_VALUES + "：" not in line:
            continue
        rs = [recs[i] for i in p["record_ids"]]
        assert not any(r.contracts for r in rs), p["path"]
        assert max(rs, key=lambda r: r.effective_from).effective_to is None, p["path"]
        body = line.split(site.ZH_VALUES + "：", 1)[1].split("。共 ", 1)[0]
        steps = re.findall(r"(\d{4}-\d{2}-\d{2}) 起 ([^；（]+)", body)
        assert steps, p["path"]
        for frm, val in steps:
            assert any(r.effective_from == frm and site.zh_value(zh, r.rule, r.value, r.unit) == val for r in rs), \
                (p["path"], frm, val)
            seen += 1
    assert seen > 300


def test_a_series_with_a_hole_an_end_or_a_contract_selector_gets_no_values():
    zh = site.zh_names()

    class R:
        def __init__(self, frm, to, value, market="XSHE", contracts=None, unit=None):
            self.effective_from, self.effective_to, self.value, self.market = frm, to, value, market
            self.contracts, self.unit, self.rule = contracts, unit, "price_limit_pct"
    ok = [R("2010-01-01", "2020-01-01", 0.1), R("2020-01-01", None, 0.2)]
    assert site.zh_runs(zh, ok) == [("2010-01-01", "10%", "XSHE"), ("2020-01-01", "20%", "XSHE")]
    assert site.zh_runs(zh, [R("2010-01-01", "2019-01-01", 0.1), R("2020-01-01", None, 0.2)]) is None      # hole
    assert site.zh_runs(zh, [R("2010-01-01", "2020-01-01", 0.1), R("2015-01-01", None, 0.2)]) is None      # overlap
    assert site.zh_runs(zh, [R("2010-01-01", "2020-01-01", 0.1)]) is None                                  # ended
    assert site.zh_runs(zh, [R("2010-01-01", None, 0.1, contracts={"any": []})]) is None
    assert site.zh_runs(zh, [R("2010-01-01", None, {"up": 0.1, "down": 0.1})]) is None
    assert site.zh_runs(zh, [R("2010-01-01", None, True)]) is None
    assert site.zh_value(zh, "stamp_duty_buy", 0.0, None) == "0%" and site.zh_value(zh, "tick_size", 0.001, "USD") == "0.001 美元"
    assert site.zh_value(zh, "min_holding_days", 1, None) == "1" and site.zh_value(zh, "price_limit_pct", "unlimited", None) == "不设涨跌幅限制"
    assert site.zh_value(zh, "limit_price_rounding", "half_up_2dp", None) is None


def test_dataset_markup_is_valid_json_and_cannot_be_closed_by_a_record(built, text, manifest):
    based = {k: v.decode("utf-8") for k, v in built["based"].items()}
    for p in _facts(manifest) + [{"path": "index.html"}]:
        k = p["path"]
        (raw,) = LD_RE.findall(text[k])
        assert "<" not in raw, k
        d = json.loads(raw)
        assert d["@context"] == "https://schema.org" and d["@type"] == "Dataset" and d["name"], k
        assert 50 <= len(d["description"]) <= 5000, (k, len(d["description"]))
        assert d["license"] == "https://creativecommons.org/publicdomain/zero/1.0/" and d["version"] == mr.VERSION
        assert d["creator"]["name"] == "marina-rules" and d["isAccessibleForFree"] is True
        assert "url" not in d and "distribution" not in d, k           # no absolute site URL without --base-url
        b = json.loads(LD_RE.findall(based[k])[0])
        assert b["url"].startswith("https://example.org/rules/") and b["distribution"][0]["contentUrl"] in \
            {"https://example.org/rules/" + x for x in built["based"]}, k
    chinext = json.loads(LD_RE.findall(text["cn/chinext/price_limit_pct.html"])[0])
    assert chinext["alternateName"] == "创业板涨跌幅限制" and chinext["temporalCoverage"] == "2009-10-30/.."
    assert chinext["spatialCoverage"] == "China mainland" and "涨跌幅限制" in chinext["keywords"]
    urls = {s["url"] for r in mr.records() if r.scope == "chinext" and r.rule == "price_limit_pct" for s in r.sources}
    assert set(chinext["isBasedOn"]) == urls
    assert site.json_ld({"q": "</script><b>"}) == '{"q":"\\u003c/script>\\u003cb>"}'
    scope_page = text["cn/chinext/index.html"]
    assert not LD_RE.findall(scope_page) and "<title>创业板交易规则 · chinext" in scope_page
    assert 'og:url" content="https://example.org/rules/cn/chinext/price_limit_pct.html"' in \
        based["cn/chinext/price_limit_pct.html"]
