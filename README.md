# Marina — point-in-time trading rules (marina-rules)

> **中文简介** · A 股、期货、港股、美股**交易制度的历史数据**：涨跌停（涨跌幅限制）、印花税和过户费的历次调整、最小报价单位、交易时段、T+N，每条都写明从哪天起生效、依据哪份官方文件。回测和 AI Agent 按成交日取当天的规则，查不到就报错、不猜。`pip install marina-rules` · 中文入门：[README.zh-CN.md](https://github.com/David-Marina/marina-rules/blob/main/README.zh-CN.md) · 每条规则一页的网页版：[david-marina.github.io/marina-rules](https://david-marina.github.io/marina-rules/)

**Auditable backtests: the exchange trading rules in force on each day, as data with sources.**

Price limits, fees, trading sessions, ticks, settlement — every record says *when* a rule took effect and *where* it was published. A backtest asks for the rule of each trade date instead of hard-coding today's; `marina-check` then verifies every fill against the rules of its day and, when nothing was relaxed and nothing was found, emits a stamp that anyone holding the same fill log and the same rules version can recompute; `citation()` names the exact, byte-pinned rules a result ran under.

A backtest that hard-codes today's rules gets earlier trades wrong. [`examples/hardcoded_vs_marina.py`](https://github.com/David-Marina/marina-rules/blob/main/examples/hardcoded_vs_marina.py) prints these five fills and a sixth (a convertible bond) side by side — the number a backtest gets from today's rule, and the number that applied on the trade date:

| fill | hard-coded with today's rule | rule of that day |
|---|---|---|
| ChiNext, 2020-08-21, previous close 10.00: limit-up / limit-down | 12.00 / 8.00 | 11.00 / 9.00 |
| ST main-board stock, 2024-06-14, previous close 10.00 | 11.00 / 9.00 | 10.50 / 9.50 |
| Main-board IPO in its first five days, 2024-01-30 | 11.00 / 9.00 | no limit |
| Sell 100,000 on 2008-04-23: stamp duty + transfer fee | 51.00 | 302.55 |
| Sell 100,000 on 2023-08-25 | 51.00 | 101.00 |

```python
import marina_rules as mr                                # pip install marina-rules
mr.limit_price(10.00, "chinext", "2020-08-21", "XSHE")   # (11.0, 9.0): the 10% band of that day, not today's 20%
mr.rule_at("stamp_duty_sell", "2023-08-25")              # 0.001: halved to 0.0005 from 2023-08-28
```

What a stamp certifies is deliberately narrow: the fills respected these rules. It says nothing about look-ahead in prices, survivorship or overfitting. `as_of` closes one more gap: it answers only from rules that had been published by a given date, so a backtest cannot use a rule change before it was announced (a rule whose publication date was not located is refused, not assumed).

Use it to check that a backtest applied the rules in force on each day — China A-share daily price limits (limit-up / limit-down), stamp duty and transfer fees, tick sizes and sessions; futures margins, limits and fees; Hong Kong and US equity rules — and to validate a fill log against them (`marina-check`). It holds rules only: no prices, index constituents, ST or suspension lists, adjustment factors or trading calendars.

```
rules: marina-rules@2026.11.23 sha256:3e159d81e1175d71 code: marina-rules-core@1.0.0
```

Marina is to trading rules what the [tz database](https://www.iana.org/time-zones) is to time zones and what [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars) is to trading days: small, boring, free, and meant to be the one copy everyone imports instead of the thousand copies everyone gets slightly wrong.

> **Status: 2026.11.23.** 2879 records — 1423 `verified`, 1455 `single-source`, 1 `unverified` — each traced to primary sources with quotes and content hashes. **Maturity differs by market:** China A-share, CFFEX, SHFE and INE records are mostly `verified`; CZCE, GFEX, Hong Kong and US records are mostly `single-source` — a first pass, to be read as such ([counts per market](#coverage), [what the levels mean](#verification-levels)). China A-shares: price limits, fees, sessions, ticks and holding periods, measured from 2006-07-01; CFFEX stock-index futures from 2010; CFFEX treasury bond futures from 2013; SHFE (20 products, incl. night sessions), INE (5 products), CZCE (28 products, mostly `single-source`) and GFEX (5 products, no sessions yet): margin, price limits, fees and same-day round trips from 2024-01-01; Hong Kong shares and ETFs from 2010; US stocks and ETFs from 2010. DCE, crypto and other markets are not covered. Details per market: [Coverage](#coverage). Treat the exchange's own notice as authoritative, always.

What changed in each release, and which backtests a release asks you to re-run: [CHANGELOG.md](https://github.com/David-Marina/marina-rules/blob/main/CHANGELOG.md).

## Why

Every backtest engine, every trading agent, and every research notebook re-implements the same handful of rules — "ChiNext limit is 20%" — and a large share of them get the *date* wrong (it was 10% before 2020-08-24), the *scope* wrong (ST stocks differ), or the *rounding* wrong (SSE and SZSE round half up, BSE toward the previous close; `round()` does neither). These errors used to live in one firm's code. Now that AI agents write backtests by the thousand, the same error gets copied by the thousand.

A shared, cited, versioned table fixes this the way tzdata fixed time zones: not by being authoritative, but by being **the same for everyone** and **traceable to the source**.

How often does it matter? [`examples/fixed_parameters.py`](https://github.com/David-Marina/marina-rules/blob/main/examples/fixed_parameters.py)
counts it on daily bars. On the sample shipped with this repository — two ChiNext stocks, 786 trading days before
2020-08-24 — 7 closes were at limit-up and 2 at limit-down under the 10% band of the day; a band fixed at today's 20%
sees all nine as ordinary prices and lets the order through. On costs: a backtest that uses today's stamp duty leaves
out 0.05% of the portfolio a year for each time the portfolio is sold in a year, from 2008-09-19 to 2023-08-28.
Point the script at your own bars for your own count.

## Use

```bash
pip install marina-rules       # the rules, and (as a dependency) the code that reads them — nothing is fetched at run time
pip install -U marina-rules    # every week or so: newer rules; the code is upgraded only when they need it
# or take the JSON / SQLite dump attached to each data release on GitHub — same bytes, same digest
```

Marina is two packages, like the time-zone database and its readers. **`marina-rules`** is the one you install and
upgrade: it holds the rules and is versioned by date (`YYYY.MM.DD`), with a release whenever the data changes —
usually weekly. **`marina-rules-core`** is the code that reads them (lookups, the fill checker, the adapters, the
command line): semantic versions from `1.0.0`, released only when a feature or a fix is ready. `marina-rules` depends
on it, so `pip install marina-rules` installs both; `pip install -U marina-rules-core` takes a new code release
without waiting for the next data release. You import `marina_rules` either way. At import the code checks that it can
read the installed data and, if not, says which of the two packages to upgrade. Releases up to 2026.11.16 were one
package holding both; `pip install -U marina-rules` upgrades from them like from any other version.

```python
import marina_rules as mr

mr.rule_at("stamp_duty_sell", "2023-08-28")           # 0.0005
mr.rule_at("price_limit_pct", "2020-08-21", "chinext", "XSHE")   # 0.10
mr.limit_price(10.00, "chinext", "2021-03-01", "XSHE") # (12.0, 8.0)  — exchange rounding
mr.limit_price(10.00, "ipo_first5_main", "2024-01-30", "XSHG+XSHE")  # None — unlimited band
mr.rule_at("stamp_duty_sell", "2005-01-01")            # KeyError — no defaults, ever
mr.citation()   # 'rules: marina-rules@<data version> sha256:<16 hex> code: marina-rules-core@<code version>'

# Pre-flight a whole backtest window before running it:
mr.coverage("XSHE", "chinext", ["price_limit_pct"], "2019-01-01", "2026-10-19")
# {'status': 'complete', 'gaps': [], 'conflicts': [], 'verification': 'verified',
#  'required_context': ['board', 'st_status', 'listing_day_index'], 'excludes': [...], ...}
```

Dates are ISO `YYYY-MM-DD` strings or `date` / `datetime` objects (a timestamp such as `2020-08-23 09:30:00` counts as
its day). Any other spelling — `20200823`, `2020/8/23`, an integer — raises `ValueError` and names the ISO form. It is
refused rather than parsed because record intervals are compared as ISO text: read as given, `20200102` would select
the rule of a later period.

```bash
python -m marina_rules.diff <old> <new>     # in a clone: what changed, and what must be re-run; git tags or data directories
```

### Find out what can be asked

A rule is answered only under the name it is recorded with, for a scope that exists. Look the names up instead of
guessing them — from Python or from the command line (`marina-rules` and `python -m marina_rules` are the same program):

```python
mr.scopes()                          # scope → description, and the context it requires ("hk" / "us" for those registries)
mr.rules_for("cffex_if", "CCFX")     # {'margin_ratio': [[from, to], …], 'price_limit_pct_of_prev_settlement': […], …}
mr.statutory_fee_floor(86420.00, "sell", "2023-08-28", "XSHG")   # 44.0742 — stamp duty + transfer fee of one fill
mr.statutory_fee_components(86420.00, "sell", "2023-08-28", "XSHG")   # the same, per rule, with record ids
mr.skill_text()                      # the usage notes (SKILL.md) shipped inside the package
```

```bash
marina-rules                                   # lists the subcommands
marina-rules scopes                            # add hk or us for those registries
marina-rules rules cffex_if CCFX               # rule names of one scope, first / last date (--intervals for all)
marina-rules query price_limit_pct 2024-06-14 st_main XSHE --context board=main_board,st_status=true
marina-rules fees 86420 sell 2023-08-28 XSHG   # components, record ids and their sum
marina-rules skill                             # the usage notes
```

When a lookup finds nothing, the refusal says what does exist: a `KeyError` message names the rules the scope has (or
the intervals the rule has), and a decision from `resolve()` carries the same as `alternatives`
(`scope_rules`, `similar_rules`, `rule_intervals`, `similar_scopes`). Names only, never a value — a similar name is a
different rule (`price_limit_pct` is a fraction of the previous close; futures scopes carry
`price_limit_pct_of_prev_settlement`), so read its definition and ask again. `tick_size` falls back to the `stock`
family for mainland securities scopes only: a futures, Hong Kong or US scope asked for `tick_size` is refused.

`coverage()` answers "can Marina serve every (rule, day) in this window for this scope?" — `complete`,
`partial` (with the exact gaps), or `unsupported`. It also tells you what you must already know about
each security to select the scope legitimately (`required_context`): Marina holds rules, never a
security's ST or listing history, and it will not guess them for you. Gaps carry `known_gap_ids`
when they match [`data/cn/known_gaps.yaml`](https://github.com/David-Marina/marina-rules/blob/main/data/cn/known_gaps.yaml) (Hong Kong: [`data/hk/known_gaps.yaml`](https://github.com/David-Marina/marina-rules/blob/main/data/hk/known_gaps.yaml); US: [`data/us/known_gaps.yaml`](https://github.com/David-Marina/marina-rules/blob/main/data/us/known_gaps.yaml)) — the list of things Marina
knows it does not cover (pre-2006 sessions and convertibles, the 2013 T+0 switch for bond/money/gold ETFs…), each with
a reason and a status, so "unsupported" can be cited rather than worked around. Agents: read [SKILL.md](https://github.com/David-Marina/marina-rules/blob/main/SKILL.md).

The data is plain YAML under [`data/`](https://github.com/David-Marina/marina-rules/tree/main/data/). You do not need the Python package; read the files from any language.

### Ask from an AI assistant: the MCP server

The same questions can be put to the dataset by an AI assistant through the
[Model Context Protocol](https://modelcontextprotocol.io), without writing code. The server runs locally over stdio.

```bash
pip install "marina-rules[mcp]"   # adds the MCP Python SDK; the server needs Python 3.10+, the rest of the package 3.9+
marina-rules-mcp                  # the same server: marina-rules mcp, python -m marina_rules.mcp_server
```

Add it to the MCP client's configuration (most clients read this `mcpServers` shape; where the file lives differs per
client). If the client does not start in the environment where the package is installed, give the full path to
`marina-rules-mcp`.

```json
{
  "mcpServers": {
    "marina-rules": {"command": "marina-rules-mcp"}
  }
}
```

| tool | answers |
|---|---|
| `resolve` | one rule on one trading day for one scope: the decision of `resolve()`, acted on only when `status` is `DETERMINED` |
| `limit_price` | limit-up / limit-down price from the previous close; `unlimited: true` when no daily limit applied |
| `statutory_fees` | stamp duty and transfer fee of one A-share stock fill, per component and summed (commission not included) |
| `coverage` | whether every (rule, day) of a backtest window can be answered for a scope, with the gaps |
| `list_scopes` | the scopes of `cn`, `hk` or `us` and the context each requires |
| `list_rules` | the rule names a scope holds, with their first and last dates |
| `check_fills` | the `marina-check` checks on up to 500 fills passed inline as JSON (not a file path) |
| `citation` | the citation line and version of the dataset |

Every answer carries `citation`. Arguments the library refuses (a date not written `YYYY-MM-DD`, an unknown side) and
questions with no record in force come back as tool errors whose text says what to change or what is missing; no value
is filled in. The usage notes (SKILL.md) are offered as the resource `marina-rules://skill`.

What it does not do: it is read-only and deterministic, uses no network, and reads no file but the dataset shipped
in the package. Like the package, it holds rules only — no prices, ST or suspension lists, constituents or trading
calendar; a security's board, ST status and listing day are the caller's to supply.

Without MCP, one line in your project's `AGENTS.md` or `CLAUDE.md` is enough for a coding assistant:

```
Exchange trading rules (A-share price limits 涨跌停, stamp duty 印花税, fees, ticks, sessions, futures margins): use the
Python package marina-rules (pip install marina-rules); run `marina-rules skill` once for the usage notes; never
hard-code a rule value; act only on status DETERMINED.
```

<!-- mcp-name: io.github.David-Marina/marina-rules -->

### Cite it

Put `mr.citation()` in every result you publish. A result without it cannot be reproduced; a result with it can be re-run by anyone against the same bytes. For a reference list, [`CITATION.cff`](https://github.com/David-Marina/marina-rules/blob/main/CITATION.cff) names the project; the version and digest still come from `mr.citation()`.

```
rules: marina-rules@2026.11.23 sha256:3e159d81e1175d71 code: marina-rules-core@1.0.0
```

`marina-rules@…` is the data version (`mr.VERSION`, the version of the `marina-rules` package) and `sha256:…` the
first 16 hex of `mr.dataset_digest()`, computed over the rule files themselves: two results citing the same digest ran
against byte-identical rules. `code: marina-rules-core@…` is the code that read them (`mr.__version__`); a code release
changes how questions are answered only where its CHANGELOG entry says so. `marina-rules version` prints the same line.
Tools that read the line up to the digest keep working: the code version is appended after it.

### Which version to use

A data release goes out most Mondays: rule changes, corrections, and the date through which each market's sources were
checked. The code changes far less often, when a new function or a fix is ready; a data release that needs newer code
requires it, and pip installs it. Old versions of both stay installable — that is what makes a citation re-runnable.

- **Research you will publish or compare later:** pin both versions the citation names
  (`pip install "marina-rules==<data version>" "marina-rules-core==<code version>"`) and cite it. A citation without
  `code:` comes from a release up to 2026.11.16, which carried its own code: `marina-rules==<version>` alone pins it.
- **Anything that asks about recent or current dates:** upgrade weekly (`pip install -U marina-rules`) and pass
  `require_tracked=True`. An installed
  version knows the last date its sources were checked (`tracked_through`); asked about a later date it warns that
  the answer is carried forward, and with `require_tracked=True` it refuses instead.
- **After upgrading:** each
  [CHANGELOG](https://github.com/David-Marina/marina-rules/blob/main/CHANGELOG.md) entry opens with three lines: which rules changed, what was corrected, and whether
  anything is incompatible. In a clone of the repository, `python -m marina_rules.diff <old tag> <new tag>` lists every
  changed record and the intervals to re-run.
- **The code:** `pip install -U marina-rules` upgrades it only when the new data requires it. To take a code release
  sooner — a new function, a fix — run `pip install -U marina-rules-core`; its CHANGELOG entry
  (`## [marina-rules-core X.Y.Z]`) says what changed and whether any answer differs.

A published version is not deleted. When one turns out to give wrong answers, the release that fixes it says so at
the top of its [CHANGELOG](https://github.com/David-Marina/marina-rules/blob/main/CHANGELOG.md) entry, with what to re-run.

### Check a fill log

```bash
python -m marina_rules.check fills.csv [--strict] [--no-tick] [--band-tolerance-pct X] [--assume-seasoned] [--assume-not-st] [--rows] [--top-codes N]
python -m marina_rules.check --list-scopes

# an engine's own trade export: adapt it and check it in one go (or write the adapted rows with `marina-rules adapt`)
marina-check trades.csv --format rqalpha --bars daily.csv --bars-format tushare \
             --listing stock_basic.csv --listing-format tushare --st stock_st.csv --st-format tushare
marina-rules adapt --list-formats
```

**Engine exports.** `--format` reads the trades of RQAlpha (`trades.csv` of `--report`), vn.py (`TradeData` rows),
backtrader (the `Transactions` analyzer), 掘金 gm (execution reports) or — `generic`, the default — any table with
common column names, with `--map field=column`, `--side-values`, `--side-from-sign` and `--date-format` for the rest.
What an engine does not export is joined from a data vendor's tables: `--bars` (previous close, day high / low and,
for baostock, ST) in the layout of Tushare `daily`, baostock or RQData; `--listing` (listing dates); `--st` (one row
per security and day on which it was ST, e.g. Tushare `stock_st`). Each format is a declared reading of named columns
and states what that reading rests on (`--list-formats`); JoinQuant, the RiceQuant platform, PTrade and QMT have no
format because their exports could not be read from a primary source, Qlib because it writes no fill log and trades
at adjusted prices. No row is dropped and nothing is guessed: a cell that cannot be read is passed through as written, so
the checker refuses the row; two columns, or the fills and a joined table, that give one field different values are
refused the same way (`--map field=COLUMN` says which column a field is). The adapter's report (`adapter` in the
output) counts such cells and rows by reason and lists the columns it did not use. The previous close
is taken only from a column the vendor documents as the day's limit reference — never computed — and the bars must be
unadjusted. Without ST information a main-board, ChiNext or STAR row is `SCOPE_UNDETERMINED`; `--assume-not-st`
treats such rows as not ST (a relaxation: no stamp, `assumed_not_st` counts them, and an ST stock is then checked
against the wider ordinary band). The stamp of an adapted run commits to the adapted rows.

Verifies each fill against the rules in force that day — no buys above limit-up, no sells below limit-down, prices on the tick in force, fees not below the statutory floor — and emits a `rules-verified@<data version>:<hash>` stamp when clean. The stamp is recomputable by anyone holding the same log and the same dataset, and commits to every column a check used (date, code, side, price, prev_close, scope, market, decimals, fee, turnover, and day_high / day_low when the log has them — canonical row format in the `marina_rules.check` docstring).

Findings: `ROW_INVALID` (missing date, code or side; price / prev_close not a finite number greater than 0 — also for unlimited scopes; a `fee`, `turnover`, `decimals`, `list_date` or context cell that is present but cannot be read, e.g. `nan`; a date that is not `YYYY-MM-DD`; or two cells of the row that state different things — `st` and `st_status`, a `market` or `board` that is not the stock code's, a trade before its `list_date`), `SCOPE_CONTEXT_CONFLICT` (the row names a scope that the row itself contradicts — scope `main_board` with `st` true, or an IPO-window scope of the main board on a ChiNext code — as `resolve()` refuses such context), `ROWS_DISAGREE` (two rows of one code on one day with different previous closes, scopes or markets), `PRICE_OFF_TICK` (price not a multiple of the instrument family's `tick_size` that day, exact decimal comparison), `LIMIT_BUY_ABOVE_UP`, `LIMIT_SELL_BELOW_DOWN`, `PRICE_OUTSIDE_BAND`, `FEE_BELOW_STATUTORY`, `RULE_MISSING`, `MARKET_REQUIRED`, `MARKET_UNSUPPORTED` (the checks are China A-share only: a Hong Kong or US row — market `XHKG`, `XNYS`, `XNAS` or scope `hk_stock` / `hk_etf` / `us_stock` / `us_etf` — is reported, not checked), `SCOPE_UNDETERMINED`, `PRICE_OUTSIDE_DAY_RANGE`, `DAY_RANGE_INVALID`.

**`prev_close` must be on the same price basis as `price`** — both unadjusted, as traded. On an ex-rights / ex-dividend day it is the exchange's ex-rights reference price, never a back- or forward-adjusted close. A log that mixes bases is off by a constant factor per stock. The output's `hints` name such codes (a hint, not a finding): either ≥ 3 rows of one code beyond the band by ≥ 5 % of the limit, or ≥ 20 rows on one side whose median excess is ≥ 1.5 % — in both cases with price / prev_close ratios within a factor 1.5 of each other. Slippage of a few tenths of a percent never reaches either threshold; a single bad row never fires.

**Day range (optional `day_high`, `day_low`, same basis as `price`).** When both are given, the fill must lie within the day's range, else `PRICE_OUTSIDE_DAY_RANGE` (with `day_high`, `day_low`, `excess`, `excess_pct`). This is a data-consistency check, not an exchange rule: it catches a price-basis mismatch that never leaves a wide (20 %) band, and these rows feed the hints too. A finding says the fill price and the day's range disagree; it cannot say which of the two is wrong.

**Scope.** `--list-scopes` prints every A-share scope the checker accepts, from the registry. Instead of a `scope` you may leave the cell empty and give context columns named like the registry keys — `board`, `st` (or `st_status`), `listing_day_index`, and `issue_regime` / `delisting_day_index` where they matter; the scope is then chosen from the registry's own asserts (`marina_rules.equity.pick_scope`) and a row that fits no scope, or several, gets `SCOPE_UNDETERMINED` (never a guess). Without a `board` cell the board comes from `marina_rules.equity.board_for_code(code)` — a convenience based on the exchanges' code-allocation conventions for A-share stocks, not a sourced record and not part of the dataset digest.

No listing-day index? Give `list_date` instead: Marina has no trading calendar, so it does not count trading days; a trade more than 60 calendar days after `list_date` is treated as past every listing window (the registry's windows end within 5 trading days, and 60 days exceeds that even across a three-week market closure), a trade on `list_date` itself is listing day 1, and any other trade inside those 60 days has no index — a scope that depends on it stays `SCOPE_UNDETERMINED` unless `listing_day_index` is given. A stock suspended for weeks within its first five trading days needs `listing_day_index`. Or pass `--assume-seasoned`: rows with neither are treated as past the listing window — a relaxation, so no stamp; `assumed_seasoned` counts the rows whose scope depended on it and `row_status` marks them.

**Model-price logs.** Backtest fills are quote ± slippage, not exchange prices. `--no-tick` skips `PRICE_OFF_TICK`; `--band-tolerance-pct X` lets a fill outside the band (or the day range) by at most X % of the violated bound pass, counted in `within_tolerance`. Any relaxation (`--no-tick`, a tolerance, `--assume-seasoned`, `--assume-not-st`, or a `decimals` cell that is not the recorded tick) makes the run *relaxed*: `options` records what was used and **no stamp is issued** (`stamp_withheld` says why) — a stamp only ever certifies a run with nothing relaxed. (`--strict` is a different thing: it makes the checks use only records that are not `unverified`; runs with and without it can both be stamped, with different stamps.) The tolerance also absorbs small price-basis errors (rows of an affected stock that exceed a limit by less than the tolerance), so read a relaxed run together with `hints` and `summary.by_code`.

**Exit codes:** 0 = no findings under the options used (`clean`; in a relaxed run this is not a verification), 1 = findings, 2 = usage error (bad option, unreadable file). Scripts should read `relaxed`, `within_tolerance`, `assumed_seasoned`, `assumed_not_st` and `decimals_override` from the JSON, not just the exit code.

**Reading the output.** `counts` counts findings: an out-of-band buy above limit-up is both `LIMIT_BUY_ABOVE_UP` and `PRICE_OUTSIDE_BAND` (the `LIMIT_*` rows are a subset). `rows_with_findings` counts rows; `summary` breaks rows, rows with findings and findings down by scope, year and side, lists the top 20 codes (`--top-codes N`) by rows with findings with their median excess (`by_code`), and buckets tolerated excesses (`within_tolerance_excess`: ≤0.1 %, ≤0.25 %, ≤0.5 %, ≤1 %, >1 %). Band findings carry `limit_up`, `limit_down`, `violated_limit`, `excess` and `excess_pct` as numbers. `--rows` adds `row_status`, one entry per input row in order (`row`, `scope`, `status`: ok / within_tolerance / findings + `checks`), to join back to the log, and lists every row index in `hints` (otherwise the first 20 plus the total).

```json
{"options": {"strict": false, "tick": false, "band_tolerance_pct": 0.5, "assume_seasoned": false, "assume_not_st": false},
 "relaxed": true, "clean": false, "rules_verified": false, "stamp": null,
 "rows_with_findings": 1, "within_tolerance": 1, "assumed_seasoned": 0, "assumed_not_st": 0,
 "row_status": [{"row": 1, "scope": "chinext", "status": "within_tolerance",
                 "within_tolerance": [{"check": "PRICE_OUTSIDE_BAND", "limit_up": 12.0, "limit_down": 8.0,
                                       "violated_limit": "limit_up", "excess": 0.04, "excess_pct": 0.333333}]},
                {"row": 2, "scope": "main_board", "status": "findings", "checks": ["LIMIT_BUY_ABOVE_UP", "PRICE_OUTSIDE_BAND"]}]}
```

**What a stamp never rests on.** A `decimals` cell is accepted only when it equals the tick recorded for that scope, date and market; any other value is your own price grid — the row is still checked on it, but the run is relaxed and unstamped (`decimals_override` counts such rows). Fees are checked only on rows that give both `fee` and `turnover`, and the price grid only where a tick is recorded for the row: `fee_check` and `tick_check` report how many rows were and were not checked, and a stamp says nothing about the fees or the grid of the rest. Where no tick is recorded, the limit prices of an A-share stock are rounded at 0.01 (dates before 2006-07-01, known gap G-0005); a fund or B-share row is `RULE_MISSING` instead, because Marina has no grid to round its limits at. A cell the checker reads that is present but unreadable is `ROW_INVALID`, never skipped — also when the log comes through `--format`, where two columns or two tables that give one field different values are refused the same way (`row_error`) instead of being settled; column names are read in any case and without surrounding white space, and columns that are not read are listed (`columns_not_read`; for a `--format` run, `adapter.columns_not_used`). What a row does not say is not demanded: a `scope` cell with no context beside it is taken as given. The fee floor is that of A-share stocks: the fee of a fund, convertible bond or B-share row is not checked. Not checked at all: whether `turnover` equals price × quantity.

**What the stamp does not mean:** it says nothing about look-ahead bias, survivorship, capacity, or statistical validity. It says only that the fills respected the rules in this dataset. Name it accordingly.

### Audit the rules against your own data

```bash
python scripts/audit_bars.py /path/to/daily_bars --complete-from-listing
```

A price-limit rule is falsifiable: after it takes effect, no close may move beyond the band. This script counts violations per rule. A violation means the rule is wrong or your data is — either way you want to know. Marina was first audited this way against 9.1 million A-share bars; see [`docs/audit-2026-10-24.md`](https://github.com/David-Marina/marina-rules/blob/main/docs/audit-2026-10-24.md). The primary-source audit that followed, and the four corrections it produced, is in [`docs/sources-audit-2026-10-24.md`](https://github.com/David-Marina/marina-rules/blob/main/docs/sources-audit-2026-10-24.md).

## Coverage

| Market | Records (`verified` / `single-source` / `unverified`) | Price limits | Fees | Sessions / auctions | Tick & lot | Settlement | Margin |
|---|---|---|---|---|---|---|---|
| China A-share (XSHG, XSHE, BJSE) | 146 (114 / 31 / 1) | ✅ incl. B-share, ETF, convertible, delisting, REIT; one-tick floor per exchange (explicit `false` where none) | ✅ 31 records (stamp duty both sides from 2005-01-24, transfer fee incl. SSE par-value basis before 2015-08-01, commission cap/minimum for stocks, funds, REITs, SSE convertibles 2006-07-01..2021-12-31 and SZSE convertible cap 2006-12-30..2014-08-25; BJSE and later convertible commission unresolved) | ✅ `session_schedule` per exchange since 2006 (stocks, funds, convertibles, REITs, BJSE) | ✅ tick (stocks, B shares, funds, convertibles, BJSE) | ✅ `min_holding_days` (stocks, B shares, BJSE, convertibles, REITs, fund types) | n/a |
| CFFEX stock-index futures (CCFX: IF, IH, IC, IM) | 67 (62 / 5 / 0) | ✅ `price_limit_pct_of_prev_settlement` from each listing day (IF 2010-04-16), incl. the ±7% week of 2016-01 | ✅ `trans_fee_rate`, `close_today_fee_rate`, `delivery_fee_rate` (from 2015) | ✅ from listing | — | ✅ same-day round trip (`min_holding_days` 0) | ✅ non-hedge `margin_ratio` from 2015-09-07 |
| CFFEX treasury bond futures (CCFX: TF, T, TS, TL) | 61 (53 / 8 / 0) | ✅ from each listing day (TF 2013-09-06) | ✅ `trans_fee_per_lot`, `delivery_fee_per_lot` | ✅ from listing | — | ✅ same-day round trip | ✅ non-hedge (TF 2015-03-16 → 2015-09-12 a known gap) |
| SHFE (XSGE: CU, AL, ZN, PB, NI, SN, AO, AD, AU, AG, RB, WR, HC, SS, FU, BU, RU, SP, BR, OP) | 1044 (846 / 198 / 0) | ✅ from 2024-01-01 (AD, OP from listing) | ✅ trading and close-today fees (rate or per lot; where contracts are priced apart, by `contract`, some intervals known gaps) | ✅ incl. night session (`night`, `day_call`) | — | ✅ same-day round trip | ✅ speculative, from 2024-01-01 |
| INE (XINE: SC, LU, NR, BC, EC) | 281 (233 / 48 / 0) | ✅ from 2024-01-01 | ✅ trading and close-today fees (SC by `contract`) | ✅ incl. night session (EC: day only, from listing 2023-08-18) | — | ✅ same-day round trip | ✅ speculative, from 2024-01-01 |
| CZCE (XZCE: AP, CF, CJ, CY, PK, SR, OI, RM, TA, MA, SA, FG, UR, PF, PX, SH, SF, SM, PR, PL, SO, WH, RS, PM, RI, JR, LR, ZC) | 876 (27 / 849 / 0) | ✅ from 2024-01-01 (PR from 2024-08-30, PL from 2025-07-22, SO ordinary band from 2026-11-13; thinly traded products partly known gaps) | ✅ trading and close-today fees (tiers by `contract`; SO from 2026-11-12) | PF and PR only | — | ✅ same-day round trip (SO from 2026-11-12) | ✅ speculative, from 2024-01-01; SO is a known gap |
| GFEX (SI, LC, PS, PT, PD) | 220 (66 / 154 / 0) | ✅ from 2024-01-01 (PS from 2024-12-26, PT and PD from 2025-11-27) | ✅ trading and close-today fee rates | — (not yet recorded) | — | ✅ same-day round trip | ✅ speculative, from 2024-01-01 |
| Hong Kong (XHKG: shares, ETFs) | 75 (6 / 69 / 0) | ✅ none (`unlimited`); intraday pre-opening ±15% (`opening_auction_limit_pct`, from 2020-10-19; before it a known gap), closing-auction ±5% (`closing_auction_limit_pct`) and VCM triggers (`vcm_trigger_pct`) recorded as separate rules; the short-selling tick rule (`short_sale_price_test`) is a short-sale restriction, and the CTS quotation spread limit (`order_spread_limit`) and order-price multiple check (`order_price_multiple_limit`) are order-entry checks, not price limits | ✅ stamp duty both sides, SFC / AFRC levies, Investor Compensation levy (suspended: 0), trading fee, trading tariff, settlement fee (ETF stamp duty before 2015-02-13 is a known gap) | ✅ shares, ordinary full day (CAS phase-in 2016-07-25 → 2019-10-08 and ETFs are known gaps) | ✅ spread table (`tick_size_table`): shares; ETFs by Part (context `spread_table`; Part B ETFs under scope `hk_etf_part_b`); board lot not recorded | ✅ T+2 (`settlement_cycle_days`), same-day resale (`min_holding_days` 0) | n/a |
| US equities (XNYS, XNAS: common stocks, ETFs) | 107 (14 / 93 / 0) | — (no record: known gaps G-US-0001 / G-US-0002); intraday LULD bands (`luld_band`), market-wide circuit-breaker levels (`mwcb_decline_levels`) and single-stock trading-pause thresholds (`single_stock_pause_pct`, 2011-08-08 → 2013-04-08) recorded as separate rules; the Rule 201 short-sale price test (`short_sale_price_test`) is a short-sale restriction, not a price limit | ✅ SEC Section 31 fee, FINRA TAF (sells; fee holiday 2026-10-01 → 2027-01-01); CAT LLC fee and historical assessment per executed equivalent share (`cat_fee_per_share`, `cat_historical_assessment_per_share`, from September / October 2024) | ✅ per primary listing exchange: core session and opening / closing crosses (NYSE-listed stocks; Nasdaq-listed stocks and ETFs), Nasdaq `extended_hours` from 2013-03-18 (NYSE ETFs and NYSE extended hours are known gaps) | ✅ Rule 612 minimum quotation increment (`min_quote_increment`) | ✅ T+3 → T+2 → T+1 (`settlement_cycle_days`), same-day resale (`min_holding_days` 0); account-level pattern-day-trader minimum (`pattern_day_trader_min_equity`, to 2026-06-04) | n/a |
| DCE (Dalian Commodity Exchange) | not covered | — | — | — | — | — | — |
| Crypto | not covered | — | — | — | — | — | — |

Blank cells are blank on purpose. A missing rule raises `KeyError`; it does not return a guess.

- **China A-share** also records the SSE STAR growth-tier risk disclosure requirement (`retail_risk_disclosure_required`,
  from 2025-07-13; the caller supplies `star_growth_tier`).
- **Futures**: Marina records the product-level speculative (non-hedge) margin, the ordinary-day band and the exchange's
  own fees. Where one product carried different values for different contracts, the record carries a contract selector
  (pass `contract`) or the interval is a known gap — never one value for all. The share of `single-source` records
  differs a lot by exchange (CZCE almost all, GFEX most; see the table); each record's `notes` say why. Commodity
  futures coverage starts 2024-01-01.
- **DCE is not covered**: no Dalian Commodity Exchange product has a record or a coverage target.

**Coverage statement (2026.11.23).** China A-shares from 2006-07-01: **137 targets, 97.25% of target-days**
(688,714 / 708,198 target-days to 2026-11-23; 130 targets complete; `python scripts/coverage_report.py`). Every gap that
remains is listed as `unresolved` in [`coverage/cn_targets.yaml`](https://github.com/David-Marina/marina-rules/blob/main/coverage/cn_targets.yaml) and counts as **not covered**:
convertible-bond commission cap — SZSE 2006-07-01 → 2006-12-30 and 2014-08-25 → open, SSE 2021-12-31 → open — and minimum —
SZSE 2006-07-01 → open, SSE 2021-12-31 → open (no official text states a level, or says there is none, for those periods); BJSE
stock commission cap / minimum 2021-11-15 → open (no official text sets one); the context-free ChiNext delisting scope
2020-08-24 → 2020-12-31 (answered by the split scopes `delisting_chinext_pre0824` / `delisting_chinext_post0824`, G-0016). CI
fails on any gap not so listed. Coverage targets exist for China A-shares only; for the other markets the table above and
each market's `known_gaps.yaml` are the statement.

**Tracked through** — the last date for which the official sources were checked for rule changes
(`data/<prefix>/tracking.yaml`; [what it means](#what-the-dates-mean-and-dont)):

| Market group | `tracked_through` | Checked against |
|---|---|---|
| China A-share (XSHG, XSHE) | 2026-11-20 | listing pages of SSE, SZSE, CSDC and MOF rules and notices, diffed weekly; new titles matching rule keywords reviewed by title |
| SHFE (XSGE) | 2026-11-18 | notices and daily settlement parameters, every trading day from 2024-01-02 |
| INE (XINE) | 2026-11-18 | daily settlement and trading parameters, every trading day from 2024-01-02; notices from 2026-11-03 only as republished on shfe.com.cn |
| CZCE (XZCE), GFEX | 2026-11-18 | daily settlement parameters, every trading day from 2024-01-02; notice lists read for the window (attachments of two CZCE rule amendments not read) |
| Hong Kong (XHKG) | 2026-11-18 | HKEX register of rule amendments, fee, trading-hours and minimum-spread pages; IRD stamp-duty pages; government press releases. The SFC's own news list and HKEX circulars outside the CT series were not read for 2026-11-04 onward |
| US equities (XNYS, XNAS) | 2026-11-17 | SEC fee-rate advisories, FINRA trading-activity-fee page, CAT fee alerts, Nasdaq equity trader alerts, SEC documents in the Federal Register; NYSE trader updates and FINRA regulatory notices not read for 2026-11-04 onward |
| BSE (BJSE), stock-trading scopes | 2026-11-18 | the rules in force in BSE's trading-management column, read in full; superseded editions, other BSE notices and fee notices not read |
| BJSE under scope `stock` (stamp duty, transfer fee), CFFEX (CCFX) | not tracked | every open-ended answer is a carry-forward |

A record whose market includes BJSE (e.g. the `XSHG+XSHE+BJSE` stamp duty) is tracked for a query with market `XSHG` or
`XSHE`, and untracked for `BJSE` or for a query without a market.

## Scope — what Marina will and will not contain

**In:** rules that change *whether an order fills, at what price, or at what cost* — price limits, trading hours and auction windows, tick size and lot size, price cages, T+N settlement, statutory fees, exchange margin requirements. Trading calendars are not included: use `exchange_calendars`.

**Out, permanently:** constituent lists, ST/suspension lists, borrow lists, prices, adjustment factors, anything with an owner or a license. Those are *data*; Marina holds *rules*. This boundary is what lets tzdata survive forty years without a legal department, and we are not going to be cleverer than tzdata.

## What the dates mean (and don't)

Each record carries three dates: `effective_from` (when the rule applied), `published_at` (when the
official notice was issued — `null` when only later restatements were located), and `recorded_at`
(when the record entered Marina). **`recorded_at` is not "known at".** Marina was assembled after the
fact; it does not by itself let you prove that a backtest avoided look-ahead on rule changes. If that
matters, pass `as_of`: answer only from rules officially published on or before that date.

```python
import marina_rules as mr
from marina_rules.contract import resolve
ctx = {"board": "main_board", "st_status": True}
resolve("price_limit_pct", "2026-07-06", "st_main", "XSHG+XSHE", ctx, as_of="2026-04-23")["status"]  # 'NOT_YET_PUBLISHED'
resolve("price_limit_pct", "2026-07-06", "st_main", "XSHG+XSHE", ctx, as_of="2026-04-24")["result"]["value"]  # 0.1
mr.rule_at("price_limit_pct", "2024-06-14", "st_main", "XSHG+XSHE", as_of="2024-06-14")  # raises PublicationUnknown
```

A rule published after `as_of` is `NOT_YET_PUBLISHED` / `NotYetPublished` — never answered with the older rule; a record
with `published_at: null` is `UNKNOWN_PUBLICATION` / `PublicationUnknown`. CLI: `--as-of YYYY-MM-DD`. Exact semantics
and what is out of scope: [docs/SCHEMA.md](https://github.com/David-Marina/marina-rules/blob/main/docs/SCHEMA.md#as_of--as-officially-published-on-2026102607).

**An open end is not a forecast.** A record still in force has `effective_to: null`. Releases are weekly at most, and some
markets were researched once up to a cut-off date, so an exchange may have changed a rule that Marina has not caught up
with. `mr.tracked_through(market, scope=None)` gives the last date for which the maintainer checked the official sources
of that market for changes (`None` = not tracked; table under [Coverage](#coverage)). On or before it, an open-ended
record states what the sources said; after it, the value is the last checked rule **carried forward, not a finding**.
Every `resolve()` answer carries `tracking: {tracked_through, beyond}`, and a determined answer from an open-ended record
beyond that date (or on an untracked market) carries the warning `CARRY_FORWARD_BEYOND_TRACKED` (`CARRY_FORWARD_UNTRACKED`).
A closed record is never flagged: its end date is sourced. To refuse carry-forwards instead, opt in:

```python
mr.tracked_through("XSGE")                                                          # '2026-11-18'
resolve("session_schedule", "2026-11-20", "shfe_cu", "XSGE")["warnings"]             # ['CARRY_FORWARD_BEYOND_TRACKED']
resolve("session_schedule", "2026-11-20", "shfe_cu", "XSGE", require_tracked=True)["status"]  # 'BEYOND_TRACKING'
mr.rule_at("session_schedule", "2026-11-20", "shfe_cu", "XSGE", require_tracked=True)  # raises BeyondTracking (a KeyError)
```

`coverage()` reports `tracking` and the `beyond_tracking` ranges (`partial` only with `require_tracked=True`); `marina
check` counts the rows dated beyond it (not findings; the stamp is unchanged). CLI: `--require-tracked`. The registry is
not part of the dataset digest: moving a tracking date forward with no rule change does not change the citation.

## One answer shape for every language: the decision contract

```bash
python -m marina_rules.contract price_limit_pct 2024-06-14 st_main XSHE --context board=main_board,st_status=true
python -m marina_rules.contract --schema          # JSON Schema of the answer
python -m marina_rules.contract --capabilities    # what can be asked, generated from the data (add `hk` for Hong Kong, `us` for US equities)
```

`resolve()` returns one dict with `status ∈ {DETERMINED, MISSING_CONTEXT, OUT_OF_COVERAGE, CONFLICT,
UNVERIFIED, NOT_YET_PUBLISHED, UNKNOWN_PUBLICATION, BEYOND_TRACKING}` (`NOT_YET_PUBLISHED` / `UNKNOWN_PUBLICATION` only with `as_of`, `BEYOND_TRACKING` only with `require_tracked=True`), a `result` only when determined, the record and evidence refs, `known_gap_ids`, `tracking` and `warnings`, `alternatives` (what exists instead, on `OUT_OF_COVERAGE` only), the
ruleset version and hash, and a `reason` in plain words. It is the boundary other languages, agents
and logs should see; the Python exceptions remain for in-process use.

## Upgrading: `diff_rules`

`python -m marina_rules.diff <from> <to>` lists every change between two tags of this repository (or two directories
holding the data) and classifies each as **correction** (Marina was wrong about the past — results computed under the old
version on that interval were computed with a wrong rule), **regime_change** (the rule itself changed
on that date), **coverage_added**, **rename**, **bookkeeping** or **metadata**. It ends with the
`(market, scope, rule, interval)` list you must re-run. Both versions are pinned by dataset digest.
Marina does not estimate P&L impact; that is what the interval is for.

With the package installed, compare the dataset you had with the one you have now. Before upgrading, note the data
version (`marina-rules version`); afterwards fetch the old one and diff the two directories:

```bash
pip download "marina-rules==<old version>" --no-deps -d old/ && python -m zipfile -e old/*.whl old/
python -m marina_rules.diff old/marina_rules/data "$(python -c 'import marina_rules as mr; print(mr.DATA_DIR)')"
```

## Conformance vectors — check *your* implementation, in any language

[`conformance/vectors/`](https://github.com/David-Marina/marina-rules/tree/main/conformance/) holds 590 input→expected pairs whose expected values come from
the exchange texts and hand arithmetic quoted in each vector's `oracle`, not from running Marina.
Regime switches one day before and on the day, ST vs non-ST, IPO windows, both exchanges' one-tick
floors, funds, convertibles, fees, missing and contradictory context, known gaps. Marina itself is
tested against them in CI; the first run caught a real defect. `python conformance/run.py`.

## Rule fact pages

`scripts/build_site.py` turns the data into static pages, one per market family, scope and rule: every record of that
rule with its interval, value, verification level, sources, verbatim quotes and content hashes, plus the known gaps,
the tracked-through date and the exact call that answers it. Definitions are copied from the rule tables in
[docs/SCHEMA.md](https://github.com/David-Marina/marina-rules/blob/main/docs/SCHEMA.md); no statement about a rule is written by hand (only fixed labels and headings
are). Each page also has a Markdown twin, and the generated site carries its own `llms.txt` index of them. Two builds of the same data are
byte-identical.

Eighteen question pages, in English (`q/`) and Chinese (`zh/q/`) — "How has the ChiNext price limit changed?",
"印花税历次调整" and the like — open with an answer composed from the records (the value in force, since when, and
the earlier values), followed by the full history with sources; only the question titles are written by hand.
`zh/` is a Chinese landing page. `sitemap.xml` dates each page by the latest `recorded_at` of the records it shows.

```bash
python scripts/build_site.py --out site
```

The pages of the current release are published at **<https://david-marina.github.io/marina-rules/>** (rebuilt from the
data at each release), with a `sitemap.xml` and an `llms.txt` that lists every rule page as Markdown.

## Errata

When data contradicts a rule, so far the data has been wrong every time. [`errata/`](https://github.com/David-Marina/marina-rules/tree/main/errata/) records each case with a sample and a one-command detector you can run on your own bars (stale pct-change columns; sub-¥1 adjusted-price rounding; issuer-specific ex-rights formulas in reorganisation conversions). Contributions welcome under the same bar: sample + detector + the fact that settles it.

## Verification levels

Every record carries one of three levels, in the data, in the open:

| level | meaning |
|---|---|
| `verified` | ≥1 official primary source (exchange / ministry / depository) states this value and date, **or** ≥2 independent authoritative sources agree. Every source carries a verbatim `quote` and a content hash of the fetched document (text for HTML, bytes for PDF) — mandatory, enforced at load time |
| `single-source` | one source, or an official source where date or value had to be inferred |
| `unverified` | secondary sources only, or sources disagree (the disagreement is recorded in `notes`) |

`strict=True` in the API refuses `unverified` records. Release tags include all levels; the level is part of the record, not hidden in a changelog.

## Contributing

Yes, please — this only works as a commons. One record per pull request, with the primary source linked. CI checks the schema, the sources, interval overlap, and runs the audit on the sample bars. See [CONTRIBUTING.md](https://github.com/David-Marina/marina-rules/blob/main/CONTRIBUTING.md) and [GOVERNANCE.md](https://github.com/David-Marina/marina-rules/blob/main/GOVERNANCE.md). Found a wrong rule, a missing one, or a rule an exchange has just changed? [Open an issue](https://github.com/David-Marina/marina-rules/issues/new/choose) — the forms ask for the official source and nothing else you would have to look up.

## Acknowledgements

The China A-share timeline was cross-checked against the rule histories compiled in the MIT-licensed PyPI package [`data-backtest-live-common`](https://pypi.org/project/data-backtest-live-common/) (2026-09), whose anonymous author did careful work on the fee and limit chronology, and against [`exchange_calendars`](https://github.com/gerrymanoim/exchange_calendars) for calendar conventions. If you are the dbl_common maintainer: please open an issue; this table should have your name on it.

## License

Data (`data/`, `docs/`; in the `marina-rules` package): [CC0 1.0](https://github.com/David-Marina/marina-rules/blob/main/LICENSE-DATA) — no rights reserved.
Code (`src/`, `scripts/`, `tests/`; the `marina-rules-core` package and the module `marina_rules`): [MIT](https://github.com/David-Marina/marina-rules/blob/main/LICENSE).

## About the name

This project is named after my wife, Marina. This repository was published on **13 November 2026**, our wedding anniversary.

A rules table is an unglamorous thing: a few hundred lines of dates, percentages, and citations. But every one of those lines is a mistake that someone, somewhere, no longer has to make. If this table spares even a few people a wrong number, a bad trade, or a wasted week, then it has done what I hoped it would do on the day it was named — bring a little more good into the world, in her name.

It is free for everyone, forever. No rights reserved.

— David Li, 13 November 2026

---

**关于名字**

项目以我爱人 Marina 的名字命名。这个仓库发布于 **2026 年 11 月 13 日**，我们的结婚纪念日。

一张规则表是件很不起眼的东西：几百行日期、百分比和出处。但其中每一行，都是某个人在某个地方不必再犯的一个错误。如果这张表能让哪怕几个人少写错一个数字、少做错一笔交易、少白费一周时间，它就做到了命名那天我希望它做到的事——以她的名字，给这个世界多带来一点好。

它对所有人免费，永远如此。不保留任何权利。
