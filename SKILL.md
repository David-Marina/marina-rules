---
name: marina-rules
description: Look up point-in-time exchange trading rules (price limits, fees, ticks, sessions, margins) with citations before running or trusting a backtest. Use when writing a backtest, simulating fills, computing limit prices or statutory fees, or checking a fill log — China A-shares, China futures (CFFEX, SHFE, INE, CZCE, GFEX), Hong Kong and US equities — or when a result must be reproducible against a cited rule set.
---

# Using Marina rules in a backtest or agent

Marina is a dataset of *when* a trading rule took effect and *where* it was published. It is not a
backtest engine and knows nothing about any particular security's history. The correct path is short
and the order matters.

Install: `pip install marina-rules` (Python ≥ 3.9; the rules ship in the package and the code, marina-rules-core, comes
with it as a dependency; no network at run time). Covered:
China A-shares, CFFEX / SHFE / INE / CZCE / GFEX futures, Hong Kong and US equities. Not covered: DCE, crypto, and
anything that is data rather than a rule — prices, ST or suspension lists, constituents, trading calendars.

From an MCP client instead of Python: `pip install "marina-rules[mcp]"` and run `marina-rules-mcp` (stdio). Its tools
(`resolve`, `limit_price`, `statutory_fees`, `coverage`, `list_scopes`, `list_rules`, `check_fills`, `citation`) give
the answers of the functions below as JSON with `citation`; a lookup that would raise comes back as a tool error.
The path and the stopping rules here apply unchanged.

## The path

```
1. Fix market, scope, rules, [start, end)     what are you about to simulate?
2. coverage(...)                               can Marina answer for the whole window?
3. Supply the context the scope requires       ST status? listing-day index? issue regime?
4. rule_at / limit_price per fill              never a default, never "today's" value
5. citation() into the result                  so anyone can re-run against the same bytes
6. On KeyError / RuleConflict / partial: STOP   report what is missing; do not substitute
```

## 0. Names first: ask for what exists

```python
mr.scopes()                         # scope → description, requires   ("hk" / "us" for those registries)
mr.rules_for("cffex_if", "CCFX")    # rule names this scope has, each with its [from, to) intervals
```

A rule is answered only under its recorded name, for a registered scope. Do not guess a name from another market:
stocks and funds carry `price_limit_pct` (fraction of the previous close), futures carry
`price_limit_pct_of_prev_settlement`; Hong Kong has `tick_size_table`, the US `min_quote_increment`, and neither has
`tick_size` (nor does any futures scope — the A-share tick never answers for them). When a lookup refuses, the
`KeyError` message and the decision's `alternatives` list what the scope does have. That is a pointer, not an answer:
ask again under the listed name if — and only if — it is the quantity you need; "not covered" is the right answer
only after that check. The same listing from a shell: `marina-rules rules <scope> [market]`, `marina-rules scopes`.

A-share board scopes (`main_board`, `chinext`, `star`, `st_main`, the listing-window and delisting scopes …) carry
the price limit only. Stamp duty, transfer fee, commission cap, sessions and holding period of an A-share stock are
recorded under scope `stock`; ask for them there (`mr.rules_for("stock")`, `marina-rules fees …`).

Markets are ISO 10383 codes (`XSHG`, `XSHE`, `BJSE`, `XHKG`, `XNYS`, `XNAS`, `CCFX`, `XSGE`, `XINE`, `XZCE`, `GFEX`),
not exchange abbreviations: `SZSE` or `SSE` is refused, and the refusal lists the codes the scope is recorded on
(`alternatives.markets`).

**Dates are `YYYY-MM-DD`.** A `date` / `datetime` object is accepted, and so is a timestamp string that starts with the
ISO day. Everything else raises `ValueError` — `20200102`, `2020/1/2`, an integer, `None` — because intervals are
compared as ISO text and another spelling would pick the wrong period. Convert before asking, never after a refusal
by trial and error:

```python
day = f"{s[:4]}-{s[4:6]}-{s[6:]}"          # s = "20200102" (the usual A-share data-vendor format)
day = ts.date()                            # a pandas Timestamp / datetime works as it is
```

## 1–2. Pre-flight the window, don't discover gaps mid-run

```python
import marina_rules as mr

cov = mr.coverage(market="XSHE", scope="chinext", rules=["price_limit_pct"],
                  start="2019-01-01", end="2026-10-19")
assert cov["status"] == "complete", cov          # 'partial' lists gaps/conflicts; 'unsupported' = not covered
cov["required_context"]   # e.g. ['board', 'st_status', 'listing_day_index']
cov["verification"]       # weakest level among the records you will rely on
```

`complete` is a statement about *these rules, this scope, this interval* and nothing else. If you
also need fees, ask for them: `rules=["price_limit_pct", "stamp_duty_sell", "transfer_fee_each_side"]`.

## 3. Context is yours to supply; Marina will not infer it

`required_context` tells you what you must already know about each security on each day to pick the
scope legitimately. Typical mistakes this prevents:

| you don't know… | then you cannot select… | because |
|---|---|---|
| whether the stock was ST **on that date** | `main_board` vs `st_main` | the bands differ (10% vs 5% before 2026-07-06) |
| trading-day index since listing | `chinext` vs `ipo_first5_chinext` | first 5 days are unlimited |
| approval vs registration IPO | `ipo_day1_main` vs `ipo_first5_main` in Feb–Apr 2023 | different regimes coexisted |

Using "today's" ST list for history is the single most common error; it is how the maintainers'
own dataset was wrong for two years. If you lack point-in-time ST status, say so in the result and
exclude ST-ambiguous securities rather than assuming non-ST.

Scopes that must not both be selected for one security/day are listed in `cov["excludes"]`.

## 4. Query per fill — through the contract if you are not Python, or want one shape

```python
from marina_rules.contract import resolve
d = resolve("price_limit_pct", "2024-06-14", "st_main", "XSHE",
            context={"board": "main_board", "st_status": True}, min_verification="single-source")
d["status"]   # DETERMINED | MISSING_CONTEXT | OUT_OF_COVERAGE | CONFLICT | UNVERIFIED (more opt-in ones: 4c, 4e)
d["result"]   # only on DETERMINED: {value, effective_from, effective_to, published_at, unit}
d["reason"]   # one sentence you can put in a log verbatim
```

`python -m marina_rules.contract --schema` prints the JSON Schema; `--capabilities` prints what can be
asked at all (rules × scopes × markets, context vocabulary, known gaps). It is large (about 190 KB): an agent
meeting Marina for the first time should start with `marina-rules scopes` and `marina-rules rules <scope> [market]`
and open capabilities for the detail it then needs. The contract never raises for data reasons; anything but
`DETERMINED` is a stop, and `MISSING_CONTEXT` also catches context that **contradicts** the scope
(`st_status=True` with scope `main_board`; `board=star` with `main_board`; `listing_day_index=1` with
`main_board` after 2023-04-10; `listing_day_index=1` with `convertible`). A key passed as `null` counts as
missing. Each scope's constraints are data (`asserts` in `data/cn/scopes.yaml`, mirrored in capabilities.json).
SHFE exchange fees (market `XSGE`, speculative only) come per product either as a rate (`trans_fee_rate`, a fraction of
turnover) or per lot (`trans_fee_per_lot`, `unit: CNY`); closing a same-day position uses `close_today_fee_rate` /
`close_today_fee_per_lot` instead of the opening fee — capabilities.json says which rule a scope has. Where one product's
contracts are priced apart (gold and silver throughout) the answer is `OUT_OF_COVERAGE` with a known gap: do not
substitute the most common contract's fee.
Hong Kong (market `XHKG`, scopes `hk_stock` / `hk_etf`) has its own registry and gaps in `data/hk/`; `coverage()` and
`resolve()` pick it from the market, and `--capabilities hk` (capabilities-hk.json) lists it. Its spread table is
`tick_size_table` (a list of price bands, not `tick_size`). For an ETF it needs context `spread_table` (`part_a` before
2020-06-01, `part_d` from it, under `hk_etf`; a Part B ETF is scope `hk_etf_part_b` with `part_b`): which Part the ETF
trades under is yours to supply, and only this rule asks for it. `closing_auction_limit_pct` and `vcm_trigger_pct` describe
CAS / VCM securities only, and whether a security is one is yours to supply. `opening_auction_limit_pct` (the
pre-opening ±15% band) starts 2020-10-19; before it is a known gap (the old session had no percentage band).
`investor_compensation_levy_each_side` is 0: the levy is suspended, a sourced fact, not a default. Hong Kong
`short_sale_price_test` is `{restriction, duration}` (`not_below_best_ask` for shares, `exempt` for ETFs; never
`'none'`), a different shape from the US one; it applies to designated securities only, and which ones are designated is
yours to supply. `order_spread_limit` (continuous trading only) is `{max_spreads, wider_pct, reference}`: the boundary is
the wider of `max_spreads` spreads (count them on the security's `tick_size_table`) and `wider_pct` of the reference price
(`null` = spreads only); never apply `max_spreads` alone once `wider_pct` is set. `order_price_multiple_limit` is
`{max_multiple, reference}`: reject a price ≥ N × reference or ≤ reference / N (equality rejected). US equities (markets
`XNYS` / `XNAS`, scopes `us_stock` / `us_etf`) likewise live in `data/us/`, listed by `--capabilities us`
(capabilities-us.json); there `price_limit_pct` is a known gap, not `unlimited`. `session_schedule` and
`extended_hours` are per exchange: pass the security's primary listing exchange (`XNYS` or `XNAS`), never
`XNYS+XNAS`; `luld_band` is a tier map, and the security's LULD tier (and a leveraged ETP's ratio) is yours to supply;
`single_stock_pause_pct` is a group map, and whether the security is an S&P 500 / Russell 1000 constituent or a
designated ETP is yours to determine. `cat_fee_per_share` / `cat_historical_assessment_per_share` are USD per executed
equivalent share, charged to each side's CAT Executing Broker, not a customer rate. `short_sale_price_test` is `'none'`
(a string: no price test) before 2011-02-28 and the Rule 201 mapping from it; `pattern_day_trader_min_equity` is an
account rule for margin accounts, and from 2026-06-04 it is a known gap (brokers switch to intraday margin one by one
until 2027-10-20) — do not assume either regime.

## 4b. Or the in-process API — and let it raise

```python
up, dn = mr.limit_price(prev_close, scope, date, market)   # exchange half-up rounding
stamp = mr.rule_at("stamp_duty_sell", date)                 # fraction of sell turnover
```

- `KeyError`: no rule in force → the window is not covered; do not fall back to another date or scope.
- `RuleConflict`: two records in force → dataset error; report the record ids, do not pick one.
- `limit_price(...) is None`: band is *unlimited* — this is an answer, distinct from "unknown".
- `ValueError` from `limit_price`: prev_close is so low the band rounds below one tick, and whether the
  exchange floors it at ±1 tick depends on the market (SZSE since 2011, SSE only since 2023-04-10).
  Pass `market=`. This only triggers below ≈¥0.10; ordinary prices never need it.
- `strict=True` excludes `unverified` records. It still admits `single-source`; decide your own bar.

Statutory fees of an A-share stock fill: `mr.statutory_fee_floor(turnover, side, date, market)` returns stamp duty of
that side plus the transfer fee, in CNY; `mr.statutory_fee_components(...)` gives each amount with its record id. Use
them instead of adding the rates yourself (0.0005 + 0.00001 is 0.00051, and the transfer fee was charged on par value
on the SSE before 2015-08-01 — the function leaves that component out and says so). Commission is not included.

## 4c. Avoiding look-ahead on rule changes: `as_of`

```python
mr.rule_at("price_limit_pct", "2026-07-06", "st_main", "XSHG+XSHE", as_of="2026-04-24")   # 0.1 (published 2026-04-24)
mr.rule_at("price_limit_pct", "2026-07-06", "st_main", "XSHG+XSHE", as_of="2026-04-23")   # NotYetPublished
mr.coverage("XSHE", "chinext", ["price_limit_pct"], "2020-01-01", "2021-01-01", as_of="2020-01-01")["not_yet_published"]
```

`as_of` = "only rules officially published on or before this date". `NotYetPublished` / `NOT_YET_PUBLISHED`: the rule in
force was not public yet — Marina does **not** hand you the older rule; decide yourself. `PublicationUnknown` /
`UNKNOWN_PUBLICATION`: the record's publication date was never located (`published_at: null`) — unknown, stop and report.
Without `as_of` nothing changes.

## 4d. Futures fees that differ by contract: pass the contract

```python
mr.rule_at("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE", contract="au2509")   # 20 (near-three-months tier)
mr.rule_at("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE", contract="au2510")   # 10
mr.rule_at("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE")                      # ContractRequired
resolve("trans_fee_per_lot", "2025-07-10", "shfe_au", "XSGE", {"contract": "au2510"})["result"]["value"]   # 10
```

Some exchange fees are set per contract (named contracts, month tiers that roll towards expiry). Those records carry a
`contracts` selector; without a contract Marina answers `ContractRequired` / `MISSING_CONTEXT` (`contract`) and never
picks a tier. Passing `contract` where nothing differs by contract is harmless, so for futures always pass it.
`coverage(..., contract="au2510")` checks one contract; without it the contract-dependent ranges are listed under
`contract_required`.

## 4e. Dates after the tracked date: `tracking`

Every `resolve()` answer carries `tracking: {tracked_through, beyond}`: the last date for which the official sources of
the market were checked for rule changes, and whether `trade_date` is after it (both `null`: the market is not tracked).
When `tracking.beyond` is true, or `warnings` holds `CARRY_FORWARD_BEYOND_TRACKED` / `CARRY_FORWARD_UNTRACKED`, the value
comes from an open-ended record carried forward past what was checked — the exchange may have changed the rule since.
Do one of two things, never neither:

- tell the user, with the answer: "carried forward beyond `<tracked_through>` (not tracked: say so); not checked against
  later notices"; or
- opt in to refusal — `resolve(..., require_tracked=True)` answers `BEYOND_TRACKING` (a stop, like any non-DETERMINED
  status), `rule_at` / `record_at(..., require_tracked=True)` raise `BeyondTracking` (a `KeyError`),
  `coverage(..., require_tracked=True)` turns the `beyond_tracking` ranges into `partial`.

A closed record (`effective_to` set) is not flagged: its end is sourced. Tracking dates per market are in capabilities
(`tracking`) and `mr.tracking_registry()`.

## 5. Cite the bytes you ran against

```python
result["rules_citation"] = mr.citation(short=False)
# 'rules: marina-rules@<data version> sha256:<64 hex> code: marina-rules-core@<code version>'
```

A result without this line cannot be reproduced. The hash is over the data files only. The rules
(`marina-rules`, date versions, `mr.VERSION`) and the code that read them (`marina-rules-core`,
semantic versions, `mr.__version__`) are separate packages; the line names both. A result meant to be
reproduced pins both versions it ran under.

## 6. Stopping correctly

When the path cannot continue, the right output is a precise statement of what is missing — not a
number. Templates:

- "Coverage for `st_main` / `price_limit_pct` is `partial`: gap 2005-01-01→2008-09-19. Narrow the window or add the record."
- "Scope `chinext` requires `st_status`; the input has no point-in-time ST column. Excluded 197 securities flagged ST today; results for them are not computed."
- "Scope `reits` is `unsupported` in marina-rules@<data version> — known gap **G-0009** (pending). REIT bands are not encoded; nothing was substituted."
- "Scope `unicorn` is `unsupported` and matches no known gap — Marina has no opinion on it at all. Stop."
- "`price_limit_pct` is not a rule of `cffex_if`; the scope's daily limit is `price_limit_pct_of_prev_settlement` (0.10 of the previous settlement price on 2024-06-03). Answered under that name." — or, if that is not the quantity asked for: "not covered; nothing substituted."
- "`session_schedule` / `shfe_cu` on 2026-11-20 is `BEYOND_TRACKING`: SHFE sources were checked only through 2026-11-02. Not answered."

`cov["known_gap_ids"]` is the difference between *we know we don't cover this* (cite the `G-xxxx`, its
`severity` says how wrong a substitute would be) and *nobody has looked* (no id). Both stop the run;
only the first can be reported precisely. The registry is `data/cn/known_gaps.yaml`.

## When Marina is upgraded

```bash
python -m marina_rules.diff <old> <new>   # git tags of this repository, or directories holding the data
```

The rules are the `marina-rules` package (`pip install -U marina-rules`, usually weekly); the code is
`marina-rules-core`, upgraded with them only when they need it. `mr.DATA_DIR` is the installed data
directory. Keep the old one (or fetch it with `pip download "marina-rules==<old version>" --no-deps`
and unpack `marina_rules/data` from the wheel) to diff against.

Read the `kind` of each change: `correction` means results you computed under the old version on
that interval used a wrong rule — re-run them and say so; `regime_change` means the rule changed on
that date — re-run anything touching the interval; `rename`/`bookkeeping`/`metadata` change nothing
you computed. Keep both citations (old and new) in the re-run report.

## Verify a finished fill log

```bash
python -m marina_rules.check fills.csv --strict      # [--no-tick] [--band-tolerance-pct X] [--rows] | --list-scopes
```

Emits `rules-verified@<data version>:<hash>` when every fill respects the price band, the tick in force
(`PRICE_OFF_TICK`) and the statutory fee floor that day; non-finite prices and dates not written `YYYY-MM-DD` are `ROW_INVALID`. The stamp
commits to every input column (date, code, side, price, prev_close, scope, market, decimals, fee,
turnover; canonical form in `marina_rules.check`). The stamp says nothing about look-ahead, survivorship, or statistics.
China A-share fills only: a Hong Kong or US row is reported as `MARKET_UNSUPPORTED` and not checked.

- `prev_close` must be on the same basis as `price`: unadjusted; on an ex-rights day the exchange's ex-rights
  reference price. Never an adjusted close. `hints` in the output names codes whose rows look off by a constant factor.
  Optional `day_high` / `day_low` (same basis as `price`) add `PRICE_OUTSIDE_DAY_RANGE` — a data-consistency check,
  not an exchange rule — which catches a mismatch that stays inside a wide band.
- Scope: `--list-scopes` lists every accepted scope. Or leave `scope` empty and give `board`, `st`,
  `listing_day_index` (+ `issue_regime` / `delisting_day_index` where relevant); the scope is chosen from the
  registry's asserts (`marina_rules.equity.pick_scope`), and a row that fits none or several is `SCOPE_UNDETERMINED`.
  `board_for_code` fills a missing board from the code prefix (A-share stocks only; a convenience, not a record).
  No listing index: `list_date` (past every listing window when > 60 calendar days earlier; inside 60 days it stays
  undetermined), or `--assume-seasoned` (a relaxation; `assumed_seasoned` counts the rows that relied on it).
  No ST cell: the scope stays undetermined unless you pass `--assume-not-st` (a relaxation; `assumed_not_st`) —
  never fill in `st=false` yourself for rows you have no ST history for.
- An engine's own export (RQAlpha, vn.py, backtrader, 掘金, or any table): do not rewrite it by hand. Pass
  `--format NAME` and, for the previous close / ST / listing dates the engine did not export, `--bars FILE
  --bars-format NAME`, `--st FILE`, `--listing FILE` (`marina-rules adapt --list-formats` lists the layouts and what
  each reading rests on; `marina-rules adapt` writes the adapted rows). Read `adapter` in the output: it counts the
  cells that could not be read and the fills that found no bar. A fill without a previous close is `ROW_INVALID`,
  not a pass. Bars must be unadjusted; never compute a previous close from other columns.
- Model prices (quote ± slippage): `--no-tick`, `--band-tolerance-pct X`. A relaxed run never gets a stamp; say
  which options you used. The tolerance also hides small price-basis errors: read `hints` and `summary.by_code` too.
  `counts` counts findings (`LIMIT_*` ⊂ `PRICE_OUTSIDE_BAND`); `rows_with_findings`, `summary` (by scope / year /
  side / code) and `--rows` (`row_status`, one per input row) count rows.
- Exit 0 = no findings under the options used, 1 = findings, 2 = usage error. Read `relaxed`, `within_tolerance` and
  `assumed_seasoned` / `assumed_not_st` from the JSON; exit 0 from a relaxed run is not a verification.

## What this skill never does

Generate signals, choose parameters, judge strategies, or touch market data. Those belong to the
engine and the researcher. Marina only answers "what rule, since when, says who" — and declines
when it cannot.
