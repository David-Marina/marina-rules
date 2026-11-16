"""The MCP server (marina_rules.mcp_server).

Without the MCP SDK (any Python, 3.9 included): the tools as plain functions — ``run_tool(name, arguments)`` gives what
the library gives, plus the citation, and turns a refusal into a ``ToolFailure`` whose text says what to change; the
entry point says what to install and exits 2; ``import marina_rules`` never touches the SDK.

With the SDK (``pytest.importorskip("mcp")``): the same answers through a real MCP client, in memory and over stdio.
"""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys

import pytest

import marina_rules as mr
from marina_rules import mcp_server as ms
from marina_rules.check import check_rows
from marina_rules.contract import resolve

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
CITE = mr.citation()
TOOL_NAMES = ["resolve", "limit_price", "statutory_fees", "coverage", "list_scopes", "list_rules", "check_fills",
              "citation"]
ST_CTX = {"board": "main_board", "st_status": True}
ROWS = [  # an ST fill inside its 5% band and a ChiNext fill above the pre-reform 10% band
    {"date": "2024-06-14", "code": "600001", "side": "buy", "price": "10.49", "prev_close": "10.00",
     "scope": "st_main", "market": "XSHG"},
    {"date": "2020-08-21", "code": "300001", "side": "buy", "price": "11.50", "prev_close": "10.00",
     "scope": "chinext", "market": "XSHE"},
]


def _json(x):
    return json.loads(json.dumps(x, ensure_ascii=False))


def _failure(name, args):
    with pytest.raises(ms.ToolFailure) as e:
        ms.run_tool(name, args)
    text = str(e.value)
    assert text.endswith(CITE), text
    return text


def _subprocess(code, env_extra=None):
    env = dict(os.environ, PYTHONPATH=SRC, **(env_extra or {}))
    return subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, env=env, timeout=120)


# ------------------------------------------------------------------------------------------- without the SDK
def test_the_tools_are_the_documented_eight_with_descriptions_and_search_words():
    assert list(ms.TOOLS) == TOOL_NAMES and sorted(ms.DESCRIPTIONS) == sorted(ms.TITLES) == sorted(TOOL_NAMES)
    words = " ".join(ms.DESCRIPTIONS.values()) + ms.INSTRUCTIONS + ms.SERVER_DESCRIPTION
    for w in ("涨跌停", "印花税", "price limit", "stamp duty", "tick size", "trading sessions", "futures margin",
              "backtest validation", "point-in-time", "DETERMINED", "YYYY-MM-DD", "ISO 10383"):
        assert w in words, w
    for w in ("no prices", "no ST", "no trading calendar"):           # says what it does not hold
        assert w in ms.INSTRUCTIONS, w
    assert "DETERMINED" in ms.DESCRIPTIONS["resolve"] and "do not fill in a value" in ms.DESCRIPTIONS["resolve"]
    assert len(ms.SERVER_DESCRIPTION) < 300


def test_resolve_is_the_library_decision_plus_the_citation():
    got = ms.run_tool("resolve", {"rule": "price_limit_pct", "trade_date": "2024-06-14", "scope": "st_main",
                                  "market": "XSHE", "context": ST_CTX})
    want = resolve("price_limit_pct", "2024-06-14", "st_main", "XSHE", ST_CTX)
    assert got.pop("citation") == CITE and got == want and want["status"] == "DETERMINED"
    miss = ms.run_tool("resolve", {"rule": "price_limit_pct", "trade_date": "2024-06-14", "scope": "st_main",
                                   "market": "XSHE"})
    assert miss["status"] == "MISSING_CONTEXT" and miss["result"] is None and miss["citation"] == CITE
    assert miss["missing_context"] == resolve("price_limit_pct", "2024-06-14", "st_main", "XSHE")["missing_context"]


def test_limit_price_matches_the_library_and_says_unlimited():
    got = ms.run_tool("limit_price", {"prev_close": 10.0, "scope": "chinext", "date": "2020-08-21", "market": "XSHE"})
    assert (got["limit_up"], got["limit_down"]) == mr.limit_price(10.0, "chinext", "2020-08-21", "XSHE") == (11.0, 9.0)
    assert got["unlimited"] is False and got["price_limit_pct"] == 0.1 and got["citation"] == CITE
    assert got["record_id"] == mr.record_at("price_limit_pct", "2020-08-21", "chinext", "XSHE").id
    ipo = ms.run_tool("limit_price", {"prev_close": 10, "scope": "ipo_first5_main", "date": "2024-01-30",
                                      "market": "XSHG+XSHE"})
    assert mr.limit_price(10.0, "ipo_first5_main", "2024-01-30", "XSHG+XSHE") is None
    assert ipo["unlimited"] is True and ipo["limit_up"] is None and "unlimited" in ipo["note"]


def test_statutory_fees_match_the_library():
    got = ms.run_tool("statutory_fees", {"turnover": 86420.0, "side": "sell", "date": "2023-08-28", "market": "XSHG"})
    assert got["status"] == "DETERMINED" and got["citation"] == CITE
    assert got["components"] == mr.statutory_fee_components(86420.0, "sell", "2023-08-28", "XSHG")
    assert got["statutory_fee_floor"] == pytest.approx(44.0742, abs=1e-9)
    assert got["statutory_fee_floor"] == mr.statutory_fee_floor(86420.0, "sell", "2023-08-28", "XSHG")


def test_coverage_scopes_rules_and_citation_match_the_library():
    got = ms.run_tool("coverage", {"market": "XSHE", "scope": "chinext", "rules": ["price_limit_pct"],
                                   "start": "2019-01-01", "end": "2026-10-19"})
    assert got == mr.coverage("XSHE", "chinext", ["price_limit_pct"], "2019-01-01", "2026-10-19")
    assert got["citation"] == CITE
    sc = ms.run_tool("list_scopes", {"market_prefix": "hk"})
    assert set(sc["scopes"]) == set(mr.scopes("hk")) and sc["citation"] == CITE
    assert ms.run_tool("list_scopes", {})["scopes"]["chinext"]["requires"] == list(mr.scopes()["chinext"]["requires"])
    rl = ms.run_tool("list_rules", {"scope": "cffex_if", "market": "CCFX"})
    assert rl["rules"]["price_limit_pct_of_prev_settlement"]["from"] == "2010-04-16" and rl["citation"] == CITE
    assert ms.run_tool("list_rules", {"scope": "cffex_if", "market": "CCFX", "intervals": True})["rules"] == \
        mr.rules_for("cffex_if", "CCFX")
    assert "chinext" in ms.run_tool("list_rules", {"scope": "chinex"})["similar_scopes"]
    c = ms.run_tool("citation", {})
    assert c["citation"] == CITE and c["version"] == mr.VERSION and c["dataset_sha256"] == mr.dataset_digest()


def test_check_fills_is_check_rows_on_the_inline_rows():
    got = ms.run_tool("check_fills", {"rows": ROWS})
    assert got == check_rows([dict(r) for r in ROWS]) and got["citation"] == CITE
    assert [f["check"] for f in got["findings"]] == ["LIMIT_BUY_ABOVE_UP", "PRICE_OUTSIDE_BAND"]
    clean = ms.run_tool("check_fills", {"rows": ROWS[:1]})
    assert clean["rules_verified"] is True and clean["stamp"] == check_rows([dict(ROWS[0])])["stamp"]
    # numbers and booleans are read as the CSV text they stand for
    typed = [dict(ROWS[0], price=10.49, prev_close=10, scope="", board="main_board", st_status=True,
                  listing_day_index=500)]
    as_text = [dict(ROWS[0], price="10.49", prev_close="10", scope="", board="main_board", st_status="true",
                    listing_day_index="500")]
    assert ms.run_tool("check_fills", {"rows": typed, "per_row": True}) == check_rows(as_text, per_row=True)


@pytest.mark.parametrize("name,args,needle", [
    ("limit_price", {"prev_close": 10.0, "scope": "chinext", "date": "20200821"}, "2020-08-21"),
    ("resolve", {"rule": "price_limit_pct", "trade_date": "2024/06/14", "scope": "st_main"}, "2024-06-14"),
    ("coverage", {"market": "XSHE", "scope": "chinext", "rules": ["price_limit_pct"], "start": "2020-01-01",
                  "end": "2019-01-01"}, "end must be after start"),
    ("statutory_fees", {"turnover": 1000.0, "side": "hold", "date": "2023-08-28"}, "buy' or 'sell"),
    ("limit_price", {"prev_close": -1, "scope": "chinext", "date": "2020-08-21"}, "greater than 0"),
    ("limit_price", {"prev_close": True, "scope": "chinext", "date": "2020-08-21"}, "must be a number"),
    ("limit_price", {"prev_close": 10.0, "scope": "x" * 65, "date": "2020-08-21"}, "longer than 64"),
    ("resolve", {"rule": "price_limit_pct", "trade_date": "2024-06-14", "context": "st"}, "context must be an object"),
    ("resolve", {"rule": "price_limit_pct", "trade_date": "2024-06-14", "context": {"board": ["a"]}}, "context["),
    ("resolve", {"rule": "price_limit_pct", "trade_date": "2024-06-14", "min_verification": "sure"},
     "min_verification"),
    ("list_scopes", {"market_prefix": "jp"}, "cn, hk, us"),
    ("check_fills", {"rows": "fills.csv"}, "JSON array"),
    ("check_fills", {"rows": []}, "rows is empty"),
    ("check_fills", {"rows": [ROWS[0]] * (ms.MAX_ROWS + 1)}, f"at most {ms.MAX_ROWS}"),
    ("check_fills", {"rows": [dict(ROWS[0], note={"a": 1})]}, "row 1 note"),
    ("check_fills", {"rows": ROWS, "band_tolerance_pct": -1}, "band_tolerance_pct"),
    ("coverage", {"market": "XSHE", "scope": "chinext", "rules": ["r"] * (ms.MAX_RULES + 1), "start": "2020-01-01",
                  "end": "2021-01-01"}, f"at most {ms.MAX_RULES}"),
    ("resolve", {"rule": "price_limit_pct"}, "trade_date"),                     # a required argument left out
    ("resolve", {"rule": "price_limit_pct", "trade_date": "2024-06-14", "colour": "red"}, "colour"),
])
def test_bad_arguments_are_refused_with_what_to_change(name, args, needle):
    text = _failure(name, args)
    assert text.startswith("invalid argument: ") and needle in text, text


def test_no_answer_in_the_dataset_is_an_error_never_a_value():
    text = _failure("statutory_fees", {"turnover": 1000.0, "side": "sell", "date": "1985-01-01", "market": "XSHG"})
    assert text.startswith("not answered: ") and "do not substitute" in text and "stamp_duty_sell" in text
    text = _failure("limit_price", {"prev_close": 10.0, "scope": "cffex_if", "date": "2024-01-02", "market": "CCFX"})
    assert text.startswith("not answered: ") and "price_limit_pct" in text
    assert _failure("no_such_tool", {}).startswith("unknown tool")
    # resolve never raises for a data reason: the refusal is a status, and a status is not a value
    d = ms.run_tool("resolve", {"rule": "stamp_duty_sell", "trade_date": "1985-01-01"})
    assert d["status"] == "OUT_OF_COVERAGE" and d["result"] is None


def test_import_marina_rules_does_not_import_the_server_or_the_sdk():
    p = _subprocess("import sys, marina_rules as mr, marina_rules.cli, marina_rules.check, marina_rules.contract\n"
                    "assert mr.limit_price(10.0, 'chinext', '2021-03-01', 'XSHE') == (12.0, 8.0)\n"
                    "print(sorted(m for m in sys.modules if m == 'mcp' or m.startswith(('mcp.', 'marina_rules.mcp'))))")
    assert p.returncode == 0 and p.stdout.strip() == "[]", p.stderr


def test_the_server_module_imports_without_the_sdk():
    p = _subprocess("import sys; sys.modules['mcp'] = None\n"
                    "import marina_rules.mcp_server as ms\n"
                    "print(ms.run_tool('limit_price', {'prev_close': 10.0, 'scope': 'chinext', 'date': '2020-08-21', "
                    "'market': 'XSHE'})['limit_up'])\n"
                    "print(ms.sdk_problem())")
    assert p.returncode == 0, p.stderr
    first, second = p.stdout.strip().splitlines()
    assert first == "11.0" and 'pip install "marina-rules[mcp]"' in second


@pytest.mark.parametrize("launch", [
    "import runpy; runpy.run_module('marina_rules.mcp_server', run_name='__main__')",     # python -m …mcp_server
    "from marina_rules.mcp_server import main; raise SystemExit(main())",                # marina-rules-mcp
    "from marina_rules.cli import main; raise SystemExit(main(['mcp']))",                 # marina-rules mcp
])
def test_without_the_sdk_the_entry_point_says_what_to_install_and_exits_2(launch):
    p = _subprocess("import sys; sys.modules['mcp'] = None\n" + launch)
    assert p.returncode == 2 and p.stdout == "", (p.stdout, p.stderr)
    assert 'pip install "marina-rules[mcp]"' in p.stderr and "works" in p.stderr
    if sys.version_info < (3, 10):
        assert "Python 3.10" in p.stderr


@pytest.mark.skipif(importlib.util.find_spec("mcp") is not None and sys.version_info >= (3, 10),
                    reason="the MCP SDK is installed here")
def test_on_this_python_without_the_sdk_python_dash_m_exits_2():
    env = dict(os.environ, PYTHONPATH=SRC)
    p = subprocess.run([sys.executable, "-B", "-m", "marina_rules.mcp_server"], capture_output=True, text=True,
                       env=env, timeout=120, stdin=subprocess.DEVNULL)
    assert p.returncode == 2 and "marina-rules[mcp]" in p.stderr and p.stdout == ""
    assert subprocess.run([sys.executable, "-B", "-m", "marina_rules", "version"], capture_output=True, text=True,
                          env=env, timeout=120).stdout.strip() == CITE


def test_help_and_stray_arguments(capsys):
    assert ms.main(["--help"]) == 0 and "mcpServers" in capsys.readouterr().out
    assert ms.main(["--port", "8080"]) == 2 and "stdio only" in capsys.readouterr().err


def test_registry_entry_agrees_with_the_package_and_the_readme():
    # server.json is the MCP Registry entry; the registry checks the README (the PyPI description) for the mcp-name line
    with open(os.path.join(ROOT, "server.json"), encoding="utf-8") as fh:
        entry = json.load(fh)
    with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as fh:
        core_py = fh.read()            # marina-rules-core, the code: its extra names the SDK
    with open(os.path.join(ROOT, "packages", "marina-rules", "pyproject.toml"), encoding="utf-8") as fh:
        py = fh.read()                 # marina-rules, the package people install: the command and its own extra
    assert entry["name"] == ms.REGISTRY_NAME and entry["version"] == mr.VERSION
    assert entry["$schema"].startswith("https://static.modelcontextprotocol.io/schemas/")
    assert len(entry["description"]) <= 100 and entry["description"].isascii()
    (pkg,) = entry["packages"]
    assert (pkg["registryType"], pkg["identifier"], pkg["version"]) == ("pypi", "marina-rules", mr.VERSION)
    assert pkg["transport"] == {"type": "stdio"} and [a["value"] for a in pkg["packageArguments"]] == ["mcp"]
    assert [a["value"] for a in pkg["runtimeArguments"]] == [ms.SDK_REQUIREMENT] and ms.SDK_REQUIREMENT in core_py
    assert 'name = "marina-rules-core"' in core_py and 'mcp = ["marina-rules-core[mcp]' in py
    assert 'name = "marina-rules"' in py and 'marina-rules-mcp = "marina_rules.mcp_server:main"' in py
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()
    assert f"<!-- mcp-name: {ms.REGISTRY_NAME} -->\n" in readme


# ------------------------------------------------------------------------------------------------ with the SDK
@pytest.fixture(scope="module")
def sdk():
    if sys.version_info < (3, 10):
        pytest.skip("the MCP SDK needs Python 3.10+")
    return pytest.importorskip("mcp")


def _in_memory(sdk, body):
    async def go():
        async with sdk.Client(ms.build_server(), raise_exceptions=True) as client:
            return await body(client)
    return asyncio.run(go())


def test_in_memory_lists_every_tool_read_only_with_schemas(sdk):
    async def body(c):
        return await c.list_tools(), await c.list_resources(), await c.read_resource(ms.SKILL_URI)
    tools, resources, skill = _in_memory(sdk, body)
    by_name = {t.name: t for t in tools.tools}
    assert sorted(by_name) == sorted(TOOL_NAMES)
    for name, t in by_name.items():
        assert t.description == ms.DESCRIPTIONS[name] and t.title == ms.TITLES[name]
        a = t.annotations
        assert a.read_only_hint is True and a.open_world_hint is False and a.destructive_hint is False
        assert t.output_schema["type"] == "object"
    assert by_name["limit_price"].input_schema["required"] == ["prev_close", "scope", "date"]
    assert by_name["resolve"].input_schema["properties"]["trade_date"]["description"] == "YYYY-MM-DD"
    assert [r.uri for r in resources.resources] == [ms.SKILL_URI]
    assert skill.contents[0].text == mr.skill_text() and skill.contents[0].mime_type == "text/markdown"


def test_in_memory_answers_are_the_library_answers(sdk):
    calls = {
        "limit": ("limit_price", {"prev_close": 10, "scope": "chinext", "date": "2020-08-21", "market": "XSHE"}),
        "fees": ("statutory_fees", {"turnover": 86420, "side": "sell", "date": "2023-08-28", "market": "XSHG"}),
        "missing": ("resolve", {"rule": "price_limit_pct", "trade_date": "2024-06-14", "scope": "st_main",
                                "market": "XSHE"}),
        "st": ("resolve", {"rule": "price_limit_pct", "trade_date": "2024-06-14", "scope": "st_main",
                           "market": "XSHE", "context": ST_CTX}),
        "coverage": ("coverage", {"market": "XSHE", "scope": "chinext", "rules": ["price_limit_pct"],
                                  "start": "2019-01-01", "end": "2026-10-19"}),
        "scopes": ("list_scopes", {"market_prefix": "us"}),
        "rules": ("list_rules", {"scope": "cffex_if", "market": "CCFX"}),
        "check": ("check_fills", {"rows": ROWS, "per_row": True}),
        "citation": ("citation", {}),
        "bad_date": ("limit_price", {"prev_close": 10, "scope": "chinext", "date": "2020/08/21"}),
        "no_rule": ("statutory_fees", {"turnover": 1000, "side": "sell", "date": "1985-01-01", "market": "XSHG"}),
        "bad_type": ("limit_price", {"prev_close": "ten", "scope": "chinext", "date": "2020-08-21"}),
        "too_many": ("check_fills", {"rows": [ROWS[0]] * (ms.MAX_ROWS + 1)}),
    }

    async def body(c):
        return {k: await c.call_tool(name, args) for k, (name, args) in calls.items()}
    r = _in_memory(sdk, body)
    ok = {k: v for k, v in r.items() if not v.is_error}
    assert sorted(ok) == ["check", "citation", "coverage", "fees", "limit", "missing", "rules", "scopes", "st"]
    for k, v in ok.items():
        assert v.structured_content["citation"] == CITE, k
        assert json.loads(v.content[0].text) == v.structured_content, k      # the text block is the same JSON
    s = {k: v.structured_content for k, v in ok.items()}
    assert (s["limit"]["limit_up"], s["limit"]["limit_down"]) == mr.limit_price(10.0, "chinext", "2020-08-21", "XSHE")
    assert s["limit"] == _json(ms.run_tool(*calls["limit"]))
    assert s["fees"]["components"] == _json(mr.statutory_fee_components(86420.0, "sell", "2023-08-28", "XSHG"))
    assert s["fees"]["statutory_fee_floor"] == pytest.approx(44.0742, abs=1e-9)
    assert s["missing"]["status"] == "MISSING_CONTEXT" and s["missing"]["result"] is None
    want = _json(resolve("price_limit_pct", "2024-06-14", "st_main", "XSHE", ST_CTX))
    assert {k: v for k, v in s["st"].items() if k != "citation"} == want
    assert s["coverage"] == _json(mr.coverage("XSHE", "chinext", ["price_limit_pct"], "2019-01-01", "2026-10-19"))
    assert set(s["scopes"]["scopes"]) == set(mr.scopes("us"))
    assert s["rules"] == _json(ms.run_tool(*calls["rules"]))
    assert s["check"] == _json(check_rows([dict(x) for x in ROWS], per_row=True))
    assert s["citation"]["dataset_sha256"] == mr.dataset_digest()
    for k in ("bad_date", "no_rule", "bad_type", "too_many"):
        assert r[k].is_error and r[k].structured_content is None, k
    text = {k: r[k].content[0].text for k in ("bad_date", "no_rule", "bad_type", "too_many")}
    assert "invalid argument" in text["bad_date"] and "2020-08-21" in text["bad_date"] and CITE in text["bad_date"]
    assert "not answered" in text["no_rule"] and "do not substitute" in text["no_rule"]
    assert "prev_close" in text["bad_type"]
    assert f"at most {ms.MAX_ROWS}" in text["too_many"]


@pytest.mark.parametrize("mode", ["legacy", "auto"])      # legacy = the initialize handshake most clients use today
def test_stdio_smoke(sdk, mode):
    params = sdk.StdioServerParameters(command=sys.executable, args=["-B", "-m", "marina_rules.mcp_server"],
                                       env={"PYTHONPATH": SRC})

    async def go():
        async with sdk.Client(params, mode=mode) as c:
            tools = await c.list_tools()
            limit = await c.call_tool("limit_price", {"prev_close": 10, "scope": "chinext", "date": "2020-08-21",
                                                      "market": "XSHE"})
            bad = await c.call_tool("resolve", {"rule": "price_limit_pct", "trade_date": "20240614"})
            return c.server_info, c.instructions, tools, limit, bad
    info, instructions, tools, limit, bad = asyncio.run(asyncio.wait_for(go(), 120))
    assert info.name == "marina-rules" and info.version == mr.VERSION
    assert "DETERMINED" in instructions and "涨跌停" in instructions
    assert sorted(t.name for t in tools.tools) == sorted(TOOL_NAMES)
    assert not limit.is_error and (limit.structured_content["limit_up"], limit.structured_content["limit_down"]) == \
        (11.0, 9.0) and limit.structured_content["citation"] == CITE
    assert bad.is_error and "2024-06-14" in bad.content[0].text
