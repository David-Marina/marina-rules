# Marina

**Point-in-time trading rules for financial markets, as data.**

Price limits, fees, trading sessions, settlement — every record says *when* it took effect and *where* it was published. Any backtest or trading agent can cite the exact rules it ran under, and anyone can re-run it against byte-identical rules.

> **中文** · 市场交易规则的「tzdata」：涨跌幅、费用、交易时段、tick 等制度**从哪天起、依据什么**，每条记录都带官方原文出处、引文和内容哈希。它给回测引擎和 AI Agent 用——查不到就报错，不猜；`coverage()` 预检整段窗口，`resolve()` 返回统一判定，`diff_rules` 告诉你升级后哪些回测要重跑。目前覆盖 A 股、中金所股指期货与国债期货、上期所 / 上期能源 / 郑商所 / 广期所商品期货（自 2024 年起）、港股和美股；大商所尚未覆盖，各市场的具体范围见 [Coverage](#coverage)。CC0 数据 + MIT 代码。

```
rules: marina-rules@2026.11.13 sha256:a66ca0e3fe8e3659
```

Marina is to trading rules what the [tz database](https://www.iana.org/time-zones) is to time zones and what [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars) is to trading days: small, boring, free, and meant to be the one copy everyone imports instead of the thousand copies everyone gets slightly wrong.

> **Status: 2026.11.13.** 2873 records — 1421 `verified`, 1451 `single-source`, 1 `unverified` — each traced to primary sources with quotes and content hashes. China A-shares: price limits, fees, sessions, ticks and holding periods, measured from 2006-07-01; CFFEX stock-index futures from 2010; CFFEX treasury bond futures from 2013; SHFE (20 products, incl. night sessions), INE (5 products), CZCE (27 products, mostly `single-source`) and GFEX (5 products, no sessions yet): margin, price limits, fees and same-day round trips from 2024-01-01; Hong Kong shares and ETFs from 2010; US stocks and ETFs from 2010. DCE, crypto and other markets are not covered. Details per market: [Coverage](#coverage). Treat the exchange's own notice as authoritative, always.

What changed in each release, and which backtests a release asks you to re-run: [CHANGELOG.md](CHANGELOG.md).

## Why

Every backtest engine, every trading agent, and every research notebook re-implements the same handful of rules — "ChiNext limit is 20%" — and a large share of them get the *date* wrong (it was 10% before 2020-08-24), the *scope* wrong (ST stocks differ), or the *rounding* wrong (exchanges round half-up; `round()` doesn't). These errors used to live in one firm's code. Now that AI agents write backtests by the thousand, the same error gets copied by the thousand.

A shared, cited, versioned table fixes this the way tzdata fixed time zones: not by being authoritative, but by being **the same for everyone** and **traceable to the source**.

## Use

```bash
pip install marina-rules      # self-contained: the dataset ships inside the wheel, byte-pinned
# or take the JSON / SQLite dump attached to each GitHub Release — same bytes, same digest
```

```python
import marina_rules as mr

mr.rule_at("stamp_duty_sell", "2023-08-28")           # 0.0005
mr.rule_at("price_limit_pct", "2020-08-23", "chinext", "XSHE")   # 0.10
mr.limit_price(10.00, "chinext", "2021-03-01", "XSHE") # (12.0, 8.0)  — exchange rounding
mr.limit_price(10.00, "ipo_first5_main", "2024-01-30", "XSHG+XSHE")  # None — unlimited band
mr.rule_at("stamp_duty_sell", "2005-01-01")            # KeyError — no defaults, ever
mr.citation()                                          # 'rules: marina-rules@<version> sha256:<16 hex>'

# Pre-flight a whole backtest window before running it:
mr.coverage("XSHE", "chinext", ["price_limit_pct"], "2019-01-01", "2026-10-19")
# {'status': 'complete', 'gaps': [], 'conflicts': [], 'verification': 'verified',
#  'required_context': ['board', 'st_status', 'listing_day_index'], 'excludes': [...], ...}
```

```bash
python -m marina_rules.diff <old> <new>     # what changed, and what must be re-run; git tags or data directories
```

`coverage()` answers "can Marina serve every (rule, day) in this window for this scope?" — `complete`,
`partial` (with the exact gaps), or `unsupported`. It also tells you what you must already know about
each security to select the scope legitimately (`required_context`): Marina holds rules, never a
security's ST or listing history, and it will not guess them for you. Gaps carry `known_gap_ids`
when they match [`data/cn/known_gaps.yaml`](data/cn/known_gaps.yaml) (Hong Kong: [`data/hk/known_gaps.yaml`](data/hk/known_gaps.yaml); US: [`data/us/known_gaps.yaml`](data/us/known_gaps.yaml)) — the list of things Marina
knows it does not cover (pre-2006 sessions and convertibles, the 2013 T+0 switch for bond/money/gold ETFs…), each with
a reason and a status, so "unsupported" can be cited rather than worked around. Agents: read [SKILL.md](SKILL.md).

The data is plain YAML under [`data/`](data/). You do not need the Python package; read the files from any language.

### Cite it

Put `mr.citation()` in every result you publish. A result without it cannot be reproduced; a result with it can be re-run by anyone against the same bytes.

### Check a fill log

```bash
python -m marina_rules.check fills.csv [--strict]
```

Verifies each fill against the rules in force that day — no buys above limit-up, no sells below limit-down, prices on the tick in force, fees not below the statutory floor — and emits a `rules-verified@<version>:<hash>` stamp when clean. The stamp is recomputable by anyone holding the same log and the same rules version, and commits to every column a check used (date, code, side, price, prev_close, scope, market, decimals, fee, turnover — canonical row format in the `marina_rules.check` docstring).

Findings: `ROW_INVALID` (missing field, or price / prev_close not a finite number — also for unlimited scopes), `PRICE_OFF_TICK` (price not a multiple of the instrument family's `tick_size` that day, exact decimal comparison), `LIMIT_BUY_ABOVE_UP`, `LIMIT_SELL_BELOW_DOWN`, `PRICE_OUTSIDE_BAND`, `FEE_BELOW_STATUTORY`, `RULE_MISSING`, `MARKET_REQUIRED`, `MARKET_UNSUPPORTED` (the checks are China A-share only: a Hong Kong or US row — market `XHKG`, `XNYS`, `XNAS` or scope `hk_stock` / `hk_etf` / `us_stock` / `us_etf` — is reported, not checked).

**What the stamp does not mean:** it says nothing about look-ahead bias, survivorship, capacity, or statistical validity. It says only that the fills respected the rules in this dataset. Name it accordingly.

### Audit the rules against your own data

```bash
python scripts/audit_bars.py /path/to/daily_bars --complete-from-listing
```

A price-limit rule is falsifiable: after it takes effect, no close may move beyond the band. This script counts violations per rule. A violation means the rule is wrong or your data is — either way you want to know. Marina was first audited this way against 9.1 million A-share bars; see [`docs/audit-2026-10-24.md`](docs/audit-2026-10-24.md). The primary-source audit that followed, and the four corrections it produced, is in [`docs/sources-audit-2026-10-24.md`](docs/sources-audit-2026-10-24.md).

## Coverage

| Market | Records (`verified` / `single-source` / `unverified`) | Price limits | Fees | Sessions / auctions | Tick & lot | Settlement | Margin |
|---|---|---|---|---|---|---|---|
| China A-share (XSHG, XSHE, BJSE) | 146 (114 / 31 / 1) | ✅ incl. B-share, ETF, convertible, delisting, REIT; one-tick floor per exchange (explicit `false` where none) | ✅ 31 records (stamp duty both sides from 2005-01-24, transfer fee incl. SSE par-value basis before 2015-08-01, commission cap/minimum for stocks, funds, REITs, SSE convertibles 2006-07-01..2021-12-31 and SZSE convertible cap 2006-12-30..2014-08-25; BJSE and later convertible commission unresolved) | ✅ `session_schedule` per exchange since 2006 (stocks, funds, convertibles, REITs, BJSE) | ✅ tick (stocks, B shares, funds, convertibles, BJSE) | ✅ `min_holding_days` (stocks, B shares, BJSE, convertibles, REITs, fund types) | n/a |
| CFFEX stock-index futures (CCFX: IF, IH, IC, IM) | 67 (62 / 5 / 0) | ✅ `price_limit_pct_of_prev_settlement` from each listing day (IF 2010-04-16), incl. the ±7% week of 2016-01 | ✅ `trans_fee_rate`, `close_today_fee_rate`, `delivery_fee_rate` (from 2015) | ✅ from listing | — | ✅ same-day round trip (`min_holding_days` 0) | ✅ non-hedge `margin_ratio` from 2015-09-07 |
| CFFEX treasury bond futures (CCFX: TF, T, TS, TL) | 61 (53 / 8 / 0) | ✅ from each listing day (TF 2013-09-06) | ✅ `trans_fee_per_lot`, `delivery_fee_per_lot` | ✅ from listing | — | ✅ same-day round trip | ✅ non-hedge (TF 2015-03-16 → 2015-09-12 a known gap) |
| SHFE (XSGE: CU, AL, ZN, PB, NI, SN, AO, AD, AU, AG, RB, WR, HC, SS, FU, BU, RU, SP, BR, OP) | 1044 (846 / 198 / 0) | ✅ from 2024-01-01 (AD, OP from listing) | ✅ trading and close-today fees (rate or per lot; where contracts are priced apart, by `contract`, some intervals known gaps) | ✅ incl. night session (`night`, `day_call`) | — | ✅ same-day round trip | ✅ speculative, from 2024-01-01 |
| INE (XINE: SC, LU, NR, BC, EC) | 281 (233 / 48 / 0) | ✅ from 2024-01-01 | ✅ trading and close-today fees (SC by `contract`) | ✅ incl. night session (EC: day only, from listing 2023-08-18) | — | ✅ same-day round trip | ✅ speculative, from 2024-01-01 |
| CZCE (XZCE: AP, CF, CJ, CY, PK, SR, OI, RM, TA, MA, SA, FG, UR, PF, PX, SH, SF, SM, PR, PL, WH, RS, PM, RI, JR, LR, ZC) | 872 (27 / 845 / 0) | ✅ from 2024-01-01 (PR from 2024-08-30, PL from 2025-07-22; thinly traded products partly known gaps) | ✅ trading and close-today fees (tiers by `contract`) | PF and PR only | — | ✅ same-day round trip | ✅ speculative, from 2024-01-01 |
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

**Coverage statement (2026.11.13).** China A-shares from 2006-07-01: **137 targets, 97.25% of target-days**
(687,464 / 706,888 target-days to 2026-11-13; 130 targets complete; `python scripts/coverage_report.py`). Every gap that
remains is listed as `unresolved` in [`coverage/cn_targets.yaml`](coverage/cn_targets.yaml) and counts as **not covered**:
convertible-bond commission cap — SZSE 2006-07-01 → 2006-12-30 and 2014-08-25 → open, SSE 2021-12-31 → open — and minimum —
SZSE 2006-07-01 → open, SSE 2021-12-31 → open (no official text states a level, or says there is none, for those periods); BJSE
stock commission cap / minimum 2021-11-15 → open (no official text sets one); the context-free ChiNext delisting scope
2020-08-24 → 2020-12-31 (answered by the split scopes `delisting_chinext_pre0824` / `delisting_chinext_post0824`, G-0016). CI
fails on any gap not so listed. Coverage targets exist for China A-shares only; for the other markets the table above and
each market's `known_gaps.yaml` are the statement.

## Scope — what Marina will and will not contain

**In:** rules that change *whether an order fills, at what price, or at what cost* — price limits, trading hours and auction windows, tick size and lot size, price cages, T+N settlement, statutory fees, exchange margin requirements, trading calendars (delegated to `exchange_calendars`).

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
and what is out of scope: [docs/SCHEMA.md](docs/SCHEMA.md#as_of--as-officially-published-on-2026102607).

## One answer shape for every language: the decision contract

```bash
python -m marina_rules.contract price_limit_pct 2024-06-14 st_main XSHE --context board=main_board,st_status=true
python -m marina_rules.contract --schema          # JSON Schema of the answer
python -m marina_rules.contract --capabilities    # what can be asked, generated from the data (add `hk` for Hong Kong, `us` for US equities)
```

`resolve()` returns one dict with `status ∈ {DETERMINED, MISSING_CONTEXT, OUT_OF_COVERAGE, CONFLICT,
UNVERIFIED, NOT_YET_PUBLISHED, UNKNOWN_PUBLICATION}` (the last two only with `as_of`), a `result` only when determined, the record and evidence refs, `known_gap_ids`, the
ruleset version and hash, and a `reason` in plain words. It is the boundary other languages, agents
and logs should see; the Python exceptions remain for in-process use.

## Upgrading: `diff_rules`

`python -m marina_rules.diff <from> <to>` lists every change between two tags (or directories) and
classifies each as **correction** (Marina was wrong about the past — results computed under the old
version on that interval were computed with a wrong rule), **regime_change** (the rule itself changed
on that date), **coverage_added**, **rename**, **bookkeeping** or **metadata**. It ends with the
`(market, scope, rule, interval)` list you must re-run. Both versions are pinned by dataset digest.
Marina does not estimate P&L impact; that is what the interval is for.

## Conformance vectors — check *your* implementation, in any language

[`conformance/vectors/`](conformance/) holds 559 input→expected pairs whose expected values come from
the exchange texts and hand arithmetic quoted in each vector's `oracle`, not from running Marina.
Regime switches one day before and on the day, ST vs non-ST, IPO windows, both exchanges' one-tick
floors, funds, convertibles, fees, missing and contradictory context, known gaps. Marina itself is
tested against them in CI; the first run caught a real defect. `python conformance/run.py`.

## Errata

When data contradicts a rule, so far the data has been wrong every time. [`errata/`](errata/) records each case with a sample and a one-command detector you can run on your own bars (stale pct-change columns; sub-¥1 adjusted-price rounding; issuer-specific ex-rights formulas in reorganisation conversions). Contributions welcome under the same bar: sample + detector + the fact that settles it.

## Verification levels

Every record carries one of three levels, in the data, in the open:

| level | meaning |
|---|---|
| `verified` | ≥1 official primary source (exchange / ministry / depository) states this value and date, **or** ≥2 independent authoritative sources agree. Every source carries a verbatim `quote` and a content hash of the fetched document (text for HTML, bytes for PDF) — mandatory, enforced at load time |
| `single-source` | one source, or an official source where date or value had to be inferred |
| `unverified` | secondary sources only, or sources disagree (the disagreement is recorded in `notes`) |

`strict=True` in the API refuses `unverified` records. Release tags include all levels; the level is part of the record, not hidden in a changelog.

## Contributing

Yes, please — this only works as a commons. One record per pull request, with the primary source linked. CI checks the schema, the sources, interval overlap, and runs the audit on the sample bars. See [CONTRIBUTING.md](CONTRIBUTING.md) and [GOVERNANCE.md](GOVERNANCE.md).

## Acknowledgements

The China A-share timeline was cross-checked against the rule histories compiled in the MIT-licensed PyPI package [`data-backtest-live-common`](https://pypi.org/project/data-backtest-live-common/) (2026-09), whose anonymous author did careful work on the fee and limit chronology, and against [`exchange_calendars`](https://github.com/gerrymanoim/exchange_calendars) for calendar conventions. If you are the dbl_common maintainer: please open an issue; this table should have your name on it.

## License

Data (`data/`, `docs/`): [CC0 1.0](LICENSE-DATA) — no rights reserved.
Code (`src/`, `scripts/`, `tests/`): [MIT](LICENSE).

## About the name

Marina is named after my wife, Marina. This repository was published on **13 November 2026**, our wedding anniversary.

A rules table is an unglamorous thing: a few hundred lines of dates, percentages, and citations. But every one of those lines is a mistake that someone, somewhere, no longer has to make. If this table spares even a few people a wrong number, a bad trade, or a wasted week, then it has done what I hoped it would do on the day it was named — bring a little more good into the world, in her name.

It is free for everyone, forever. No rights reserved.

— David Li, 13 November 2026

---

**关于名字**

Marina 以我爱人 Marina 的名字命名。这个仓库发布于 **2026 年 11 月 13 日**，我们的结婚纪念日。

一张规则表是件很不起眼的东西：几百行日期、百分比和出处。但其中每一行，都是某个人在某个地方不必再犯的一个错误。如果这张表能让哪怕几个人少写错一个数字、少做错一笔交易、少白费一周时间，它就做到了命名那天我希望它做到的事——以她的名字，给这个世界多带来一点好。

它对所有人免费，永远如此。不保留任何权利。
