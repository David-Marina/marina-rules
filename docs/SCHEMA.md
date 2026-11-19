# Data schema (schema: 1)

Each file under `data/<market>/` is a YAML document:

```yaml
schema: 1                    # required; bump only for breaking changes
market: XSHG+XSHE            # default market for records in this file (ISO 10383 MIC, '+' joins several)
asset_class: equity          # informational
records:
  - id: cn.limit.chinext.2020-08-24          # stable, unique across the whole dataset
    market: XSHE                              # optional; overrides the file default
    scope: chinext                            # which securities (vocabulary per market, see below)
    rule: price_limit_pct                     # rule name (vocabulary below)
    value: 0.20                               # number | "unlimited" | {up: x, down: y} | token
    effective_from: 2020-08-24                # inclusive
    effective_to: 2021-01-01                  # optional, exclusive
    verification: verified                    # verified | single-source | unverified
    sources:                                  # required unless unverified
      - {url: ..., publisher: ..., title: ..., date: YYYY-MM-DD, kind: official|secondary, quote: "...",
         content_sha256: <64 hex>, hash_kind: text|bytes}   # required unless the record is unverified
    notes: ""                                 # free text; record disagreements here
```

## Semantics

- Intervals are half-open `[effective_from, effective_to)`. A record with no `effective_to` is in force indefinitely.
- Lookup key is `(market, scope, rule)`. Within one key, intervals must not overlap; the record with the latest `effective_from ≤ date` wins.
- A lookup that finds no record **raises**. Consumers must not substitute defaults; the absence of a rule is information.
- `market` with `+` means the record applies identically to each listed MIC.

## Dataset version and format (`data/VERSION`, `data/SCHEMA`)

Two one-line text files describe the dataset as a whole. Neither is YAML, so neither enters `dataset_digest()`.

- `data/VERSION` — the dataset version, `YYYY.MM.DD` (`YYYY.MM.DD.N` for a further release on the same day). It is
  the version of the `marina-rules` package (`marina_rules.VERSION`) and the version a citation names
  (`rules: marina-rules@<VERSION> sha256:… code: marina-rules-core@…`).
- `data/SCHEMA` — the data format: the highest `schema:` of any data file (today `1.2`). The code (`marina-rules-core`)
  declares the schemas it reads (`marina_rules.DATA_SCHEMAS`) and the oldest dataset it reads
  (`marina_rules.MIN_DATA_VERSION`); at import it refuses a dataset whose `SCHEMA` it does not read (upgrade the code)
  or whose `VERSION` is older than that minimum (upgrade the data), and the YAML loader refuses any single file with an
  unknown `schema:` the same way. A new schema value therefore ships together with a code release that reads it.

## Source policy: archived copies of official pages

An official page that no longer exists on the live site may be cited through a **web.archive.org capture of that exact official URL** (the `…/web/<timestamp>id_/<original-url>` form, which serves the original bytes). Conditions:

- The capture's original URL must be on the issuer's own domain (e.g. sse.com.cn, szse.cn); captures of reprints do not count as official.
- `content_sha256` is computed on the archived copy, and `publisher` says it is an archive copy (e.g. 「上交所（收费页面，web.archive.org 存档）」).
- A record whose value or date rests on an archived copy is at most **`single-source`**, never `verified`: the archive is a third party holding the copy, and the page's own date stamp is not a filing's effective date.
- Prefer the live official text whenever it exists; an archived copy never overrides it.

## Rule vocabulary (v1)

| rule | value | meaning |
|---|---|---|
| `price_limit_pct` | fraction, `unlimited`, or `{up, down}` | daily band vs previous close |
| `limit_price_rounding` | `half_up_2dp` … | how the exchange computes the limit price |
| `stamp_duty_sell` | fraction | tax on sell turnover |
| `transfer_fee_each_side` | fraction | depository fee per side |
| `commission_cap` | fraction | statutory maximum brokerage rate |
| `commission_min_per_order_cny` | number | statutory minimum per order |

New rules are added by PR with a one-line definition appended to this table.

## Scope vocabulary · China A-share

See `data/cn/scopes.yaml` — the registry is authoritative and declares, per scope, what context the caller must supply (`requires`) and which scopes are mutually exclusive (`excludes`). Current (A-share): `stock` `bse_stock` `main_board` `chinext` `star` `bse` `st_main` `st_chinext` `st_star` `ipo_day1_main` `ipo_day1_bse` `ipo_first5_main` `ipo_first5_chinext` `ipo_first5_star` `b_share` `st_b_share` `etf` `etf_20pct` `convertible` `convertible_day1` `delisting` `delisting_day1` `delisting_chinext` `delisting_chinext_pre0824` `delisting_chinext_post0824` `delisting_star` `delisting_day1_star` `reits` `reits_day1` `st_bse` `delisting_bse` `delisting_day1_bse` `etf_bond` `etf_money` `etf_gold` `etf_commodity` `etf_crossborder` `star_growth_new` `star_growth_legacy`. CFFEX index futures: `cffex_if` `cffex_ih` `cffex_ic` `cffex_im` `cffex_index_futures`. CFFEX treasury bond futures: `cffex_tf` `cffex_t` `cffex_ts` `cffex_tl`. SHFE futures: `shfe_cu` `shfe_al` `shfe_zn` `shfe_pb` `shfe_ni` `shfe_sn` `shfe_ao` `shfe_au` `shfe_ag` `shfe_rb` `shfe_wr` `shfe_hc` `shfe_ss` `shfe_fu` `shfe_bu` `shfe_ru` `shfe_sp` `shfe_br` `shfe_ad` `shfe_op`. INE futures: `ine_sc` `ine_lu` `ine_nr` `ine_bc` `ine_ec`. CZCE futures: `czce_ap` `czce_cf` `czce_cj` `czce_cy` `czce_pk` `czce_sr` `czce_oi` `czce_rm` `czce_ta` `czce_ma` `czce_sa` `czce_fg` `czce_ur` `czce_pf` `czce_px` `czce_sh` `czce_sf` `czce_sm` `czce_pr` `czce_pl` `czce_wh` `czce_rs` `czce_pm` `czce_ri` `czce_jr` `czce_lr` `czce_zc`. GFEX futures: `gfex_si` `gfex_lc` `gfex_ps` `gfex_pt` `gfex_pd`. Hong Kong (separate registry `data/hk/scopes.yaml`, market XHKG): `hk_stock` `hk_etf`. US equities (separate registry `data/us/scopes.yaml`, markets XNYS, XNAS): `us_stock` `us_etf`.

## Id convention

`<market-prefix>.<family>.<scope>[.<qualifier>].<effective_from>` — e.g. `cn.limit.ipo_first5_main.main.2023-02-17`. Ids never change once released; a correction creates a new record and closes the old one with `effective_to`, or fixes the value in place only when the id's `effective_from` was itself the error (recorded in the changelog).

## Schema 1.1 (2026-10-25)

Additions, all backward compatible (loader accepts `schema: 1` and `1.1`):

| field | on | meaning |
|---|---|---|
| `published_at` | record | date the official notice was issued; `null` when only later restatements were found. Never later than `effective_from`. |
| `recorded_at` | record | date the record entered Marina. Not a proxy for "known at". |
| `data/<market>/scopes.yaml` | registry | per scope: `requires` (context the caller must hold to select it: `board`, `st_status`, `listing_day_index`, `issue_regime`), `excludes` (scopes that must not be co-selected), `asserts` (what the scope asserts about the supplied context — checked by `resolve()`; grammar in the file header) and `rule_asserts` (extra per-rule requirements). |

Semantics tightened in the same release:

- **Non-overlap is enforced at load.** Two records of one `(market, scope, rule)` in force on the same day make the dataset refuse to load. A superseded record must be closed with `effective_to`.
- **Market matching is subset-based.** A query for `XSHG+XSHE` is satisfied only by records covering both; an `XSHE`-only record never answers a both-boards question.
- **`record_at` raises `RuleConflict`** instead of silently preferring the newest record when more than one is in force.
- **Listing-window scopes are per board**: `ipo_day1_main`, `ipo_day1_bse`, `ipo_first5_main`, `ipo_first5_chinext`, `ipo_first5_star` (were `ipo_day1` / `ipo_first5`). Record ids changed accordingly; see the 2026.10.25 release notes.
- `coverage(market, scope, rules, start, end)` added; see README and SKILL.md.

## Schema 1.2 — contract selectors (2026.11.05)

Futures exchanges often price contracts of one product apart: named contracts (指定合约), month categories, tiers that
roll as expiry approaches. A record — or a known gap — may carry a **`contracts` selector**; it then covers only those
contracts of its scope's product. Without the field a record covers every contract, exactly as before.

```yaml
schema: 1.2            # required in any file that uses `contracts`; older readers refuse the file instead of misreading it
records:
- id: cn.futures.trans_fee_per_lot.shfe_au.near3_jun_dec.2025-05-16
  scope: shfe_au
  rule: trans_fee_per_lot
  contracts:
    any:                                  # covers a contract if ANY clause matches; `none: [...]` = if NO clause matches
    - months_to_delivery: {max: 2}        # keys inside one clause must all hold (AND)
    - delivery_month: {in: [6, 12]}
  value: 20
  unit: CNY
```

| clause key | operators | computed from |
|---|---|---|
| `code` | `in`, `not_in` | the contract code. In data always lower-case product + `YYMM` (`au2506`; a CZCE `SR605` is written `sr2605`). |
| `delivery_month` | `in`, `not_in` (1–12) | the code's delivery month |
| `months_to_delivery` | `min`, `max` (inclusive), `in` | (delivery year × 12 + delivery month) − (trade year × 12 + trade month): 0 in the delivery month |

Every feature is arithmetic on the code and the trade date, so Marina needs no contract calendar and the caller supplies
only the code. The scope must name one product (`<exchange>_<product>`, e.g. `shfe_au`) and every code in a selector
must be of that product.

- **Non-overlap still holds, per contract.** Two records of one `(market, scope, rule)` may share days only if both
  carry selectors and no contract is covered by both; loading checks this exactly (selector features change only at
  month boundaries, so one probe per month over every code with `months_to_delivery` 0–60, plus every named code). A
  record without a selector covers every contract and so cannot share a day with any other record of its key. A gap
  with a selector covers only those contracts (typically "every contract except the named ones" while a notice priced
  the named ones).
- **Lookup.** `record_at` / `rule_at` take `contract=` (keyword-only), `coverage` takes `contract=`, and `resolve` reads
  `context["contract"]`. The code may be given in either form and any case (`AU2606`, `SR605`); a three-digit CZCE code
  is read as the first year ending in that digit whose delivery month is not before the trade month. Its product must
  be the scope's (`ValueError` otherwise).
  - In force records carry selectors, no contract given → `ContractRequired` (a `KeyError`); `resolve` answers
    `MISSING_CONTEXT` with `missing_context: ["contract"]`. Marina never picks a tier.
  - Contract given → the one record covering it; none → `KeyError` / `OUT_OF_COVERAGE`, with any gap whose selector
    covers that contract in `known_gap_ids`.
  - A contract given where nothing differs by contract is ignored, so a caller may always pass it for futures.
  - `coverage` without a contract lists the contract-dependent ranges under `contract_required` and adds `contract` to
    `required_context` (status `partial`); with a contract it checks that contract, month by month. Neither key
    appears when no selector is involved.
  - A `DETERMINED` answer from a selector record carries `result.contracts` and lists `contract` in `required_context`.
- **Ids** add the tier as the qualifier: `cn.futures.<rule>.<scope>.<tier>.<effective_from>` (`near3_jun_dec`,
  `other_months`, `au2506`).
- **Release files**: the JSON dump carries `contracts` on every record (null when absent); the SQLite tables `records`
  and `known_gaps` have a `contracts_json` column; capabilities list `contract_keyed_scopes` per rule.

## Rule names (2026.10.25b)

| rule | value | basis |
|---|---|---|
| `price_limit_pct` | fraction, `{up, down}`, or `unlimited` | previous close |
| `price_limit_pct_of_issue_price` | `{up, down}` or `unlimited` | **issue price** (convertible-bond listing day). Distinct name on purpose: `limit_price(prev_close, …)` must not be used with it. |
| `min_holding_days` | integer | trading days a bought security must be held before it can be sold (A shares 1 = T+1 since 1995; B shares 1 since ≤2006-07-01; ordinary funds `etf`/`etf_20pct` 1 since 2006-07-01; same-day-rotation fund types 0 — see 2026.10.26.5). |
| `tick_size` | number + `unit` (CNY/USD/HKD) | minimum price increment per instrument family (`stock` / `bse_stock` / `etf` / `b_share` / `convertible`; `marina_rules.tick_family(scope, market)`). The fallback to family `stock` applies to mainland securities scopes only (scopes whose records are on XSHG / XSHE / BJSE): a futures, Hong Kong or US scope is its own family and has no `tick_size`, so the question is refused. `limit_price()` rounds at this tick; with none usable it raises `KeyError`, except for family `stock` on a date with no stock tick record at all (before 2006-07-01), which it rounds at 0.01 — known gap G-0005, the one value Marina substitutes |
| `limit_price_min_tick` | `true` \| `false` | exchange floors the band at ±1 tick when it would round to zero. **Per exchange**: XSHE `true` from 2011-02-28 (rules 3.3.16), XSHG `true` from 2023-04-10 (rules 3.3.17); `false` (rounding only — sourced from the complete rule text) XSHE 2006-07-01..2011-02-28, XSHG 2006-07-01..2023-04-10, BJSE from 2021-11-15 (2026.10.26.7). `false` and absent behave identically in `limit_price()`. |
| `limit_price_min_tick` (scope-specific) | `{prev_close_lt \| prev_close_lte: x, band: b}` + `unit` | board-specific absolute band: when the previous close is below / at-or-below `x`, the limits are prev_close ± `b` regardless of rounding. Only the SSE delisting board uses it (scopes `delisting`, `delisting_day1`; 2013-01-01 `<0.05`, 2020-12-31 `≤0.05`, both ±¥0.01; repealed 2023-04-10). `limit_price()` looks up the requested scope first and falls back to scope `stock`. (2026.10.26.4) |
| `stamp_duty_sell` / `transfer_fee_each_side` / `commission_cap` / `commission_min_per_order_cny` | fraction / CNY | turnover / per order |

`limit_price()` composes the three: band → round to tick → apply the floor if (and only if) a `limit_price_min_tick` record is in force for that market and date (requested scope first, then `stock`). When the floor would matter and no market was given it raises `ValueError` rather than guess.

## 2026.10.26.5 — sessions, same-day fund types, pre-2022 convertibles

### Rule `session_schedule`

| rule | value | meaning |
|---|---|---|
| `session_schedule` | `{open_call: [start, end], continuous: [[start, end], …], close_call: [start, end] \| null}` | competitive-auction (竞价交易) windows of a trading day, local exchange time `HH:MM`, each window half-open `[start, end)`. `close_call: null` = no closing call auction (the last continuous window runs to the close and the close is computed otherwise). |

Recorded per exchange (`XSHG`, `XSHE` — never `XSHG+XSHE`, the two diverged 2006–2018) and per instrument family:
scope `stock` (all A/B shares) and scope `etf` (listed funds). Example (SZSE since 2006-07-01; SSE stocks since
2018-08-20; SSE funds since 2026-07-06):

```json
{"open_call": ["09:15","09:25"], "continuous": [["09:30","11:30"],["13:00","14:57"]], "close_call": ["14:57","15:00"]}
```

Not modelled: the 9:25–9:30 interval (orders accepted, not matched), cancel-ban windows, halt-resumption auctions,
block trades, after-hours fixed-price trading, BSE. Before 2006-07-01: G-0007 / G-0024.

Optional keys (2026.11.02, for products with a night session):

| key | value | meaning |
|---|---|---|
| `night` | `[start, end]` \| `null` | continuous-trading window of the **night session**, held on the evening of the previous working day and counted as part of this trading day. `end < start` means the window crosses midnight (`["21:00","01:00"]`). `null` = no night session. When it is not null, `open_call` is the call auction **before the night session**, and `continuous` lists the day-session windows. |
| `day_call` | `[start, end]` \| `null` | call auction before the **day session** of a product that has a night session. `null` = none. |

A missing key means the same as `null`, so the A-share and CFFEX records (which have neither key) are unchanged.
Example (SHFE copper and the other SHFE non-ferrous metals, from 2024-01-01):

```json
{"open_call": ["20:55","21:00"], "night": ["21:00","01:00"], "day_call": ["08:55","09:00"],
 "continuous": [["09:00","10:15"],["10:30","11:30"],["13:30","15:00"]], "close_call": null}
```

A product without a night session (SHFE wire rod) has `night: null` and `day_call: null`; its `open_call` is the call
auction before the day session:

```json
{"open_call": ["08:55","09:00"], "night": null, "day_call": null,
 "continuous": [["09:00","10:15"],["10:30","11:30"],["13:30","15:00"]], "close_call": null}
```

Optional keys (2026.11.02, US equities, where the opening and closing auctions are instantaneous crosses rather than
call windows):

| key | value | meaning |
|---|---|---|
| `open_cross` | `HH:MM` \| `null` | time of the opening single-price cross (auction) that starts the core session. With it, `open_call` is `null`: there is no separate call-auction session. |
| `close_cross` | `HH:MM` \| `null` | time of the closing single-price cross (auction) at the end of the core session; `close_call` is `null`. |

A missing key means the same as `null`; no earlier record has either key. Example (Nasdaq-listed stocks and ETFs on
XNAS, NYSE-listed stocks on XNYS, from the coverage floor 2010-01-01):

```json
{"open_call": null, "continuous": [["09:30","16:00"]], "close_call": null, "open_cross": "09:30", "close_cross": "16:00"}
```

### Same-day (T+0) fund scopes

Trading rules 3.1.5 enumerate fund types that may be sold the day they are bought. Each is its own scope,
`min_holding_days: 0` from the earliest date an official text lists it:

| scope | type | from |
|---|---|---|
| `etf_bond` | 债券交易型开放式（指数）基金 | 2015-01-19 (G-0019 before: 2013 switch not sourced) |
| `etf_money` | 交易型 / 上市交易的货币市场基金 | 2015-01-19 (G-0020) |
| `etf_gold` | 黄金交易型开放式基金 | 2015-01-19 (G-0021) |
| `etf_commodity` | 商品期货交易型开放式基金 | XSHE 2019-01-11 (single-source date), XSHG 2020-01-20; `1` from 2006-07-01 before that |
| `etf_crossborder` | 跨境 ETF / 跨境 LOF **whose constituents trade same-day** | 2015-01-19; `1` 2006-07-01..2015-01-19 |

Ordinary funds (`etf`, `etf_20pct`) are `min_holding_days: 1` from 2006-07-01 (G-0013 before). Price band, tick and
session for the new scopes are those of the fund family: `tick_size()` / `resolve("tick_size", …)` map them to `etf`;
query `price_limit_pct` and `session_schedule` under `etf`.

### Context keys

| key | values | required by |
|---|---|---|
| `fund_type` | `bond_etf` \| `money_market` \| `gold_etf` \| `commodity_futures_etf` \| `cross_border` \| `other` | the five T+0 fund scopes; also `min_holding_days` under `etf` / `etf_20pct` (a same-day type there is a context conflict, so a bond ETF cannot silently get T+1) |
| `underlying_t0` | `true` \| `false` | `etf_crossborder` (must be `true`): whether the tracked constituents / investment targets themselves trade same-day — the per-instrument condition in 3.1.5 |
| `spread_table` | `part_a` \| `part_b` \| `part_d` | Hong Kong (`data/hk/scopes.yaml`): which Part of the Second Schedule to the Rules of the Exchange the ETF traded under on that date. `tick_size_table` under `hk_etf` (`part_a` before 2020-06-01, `part_d` from it); `hk_etf_part_b` (must be `part_b`) |

### Rule-specific context in `resolve()`

Some rules depend on only part of a scope's context. `resolve()` asks for:

- `tick_size`, `session_schedule`: no context (instrument family only).
- `min_holding_days`: only `fund_type` / `underlying_t0` where the scope declares them (plus `fund_type` for `etf`/`etf_20pct`) — never `st_status`, `listing_day_index` or `fund_constituents`.
- Hong Kong `tick_size_table` under `hk_etf`: `spread_table` (the scope's `rule_asserts`), for this rule only; every other `hk_etf` rule asks for nothing. `hk_etf_part_b` asks for `spread_table` for every rule (it has only `tick_size_table` records).
- every other rule: the scope's full `requires`.

Whatever is asked for, every **supplied** key is checked against the scope's `asserts`; a contradiction (or a
required key passed as `null`) is `MISSING_CONTEXT`. Constraints may be date-dependent (`from`/`to`) — e.g.
`main_board` requires `listing_day_index ≥ 2`, and `≥ 6` from 2023-04-10 unless `issue_regime: approval`.

### `unlimited` for `price_limit_pct_of_issue_price`

`convertible_day1` may now carry `unlimited` (before 2022-08-01: no listing-day band). `convertible` is `unlimited`
2006-07-01..2022-08-01. Intraday halts (临时停牌) are never encoded as a band.

## China A-share investor suitability (2026.11.02)

Data file: `data/cn/equity_suitability.yaml`, market `XSHG`, id family `cn.suitability`.

| rule | value | meaning |
|---|---|---|
| `retail_risk_disclosure_required` | `true` \| `false` | whether an ordinary (non-professional) investor must have signed the exchange-prescribed, product-specific risk disclosure statement before the broker may accept the investor's subscription or trading orders in the scope's securities; `true` = such orders must be refused until it is signed. The loader refuses any value that is not a YAML boolean. |

Scopes (SSE STAR Market growth tier 科创成长层, from 2025-07-13; mutually exclusive):

| scope | securities | value from 2025-07-13 |
|---|---|---|
| `star_growth_new` | STAR shares / depositary receipts newly registered into the tier (in it from listing day; terminal label 成) | `true` (上证函〔2025〕2218号 item 1) |
| `star_growth_legacy` | STAR shares / depositary receipts listed before the notice and not yet profitable since listing, moved into the tier on 2025-07-13 (label 成1) | `false` — the notice's exemption, a sourced fact |

Both scopes require `board` (must be `star`) and the new context key below. Membership is the caller's per-security
fact: Marina stores no constituents and does not track exits from the tier. These are suitability-only scopes: band,
tick and session of a growth-tier stock are answered under `star` / `st_star` / `ipo_first5_star`, and the rule has no
record under those scopes (`OUT_OF_COVERAGE`, never a default). No record before 2025-07-13: the tier did not exist.
The STAR account threshold and the general STAR risk disclosure are not encoded.

| key | values | required by |
|---|---|---|
| `star_growth_tier` | `new` \| `legacy` | `star_growth_new` (asserts `new`), `star_growth_legacy` (asserts `legacy`): whether the security was in the growth tier on that date as a newly registered member or as an existing member moved in on 2025-07-13. A STAR stock outside the tier selects neither scope. |

## Rule names · CFFEX stock-index futures (2026.10.26.6)

Market `CCFX` (ISO 10383 MIC of the China Financial Futures Exchange). Scopes `cffex_if` `cffex_ih` `cffex_ic` `cffex_im`
(per product, from the contract code) and `cffex_index_futures` (fees that do not distinguish products) — see `data/cn/scopes.yaml`.
Data file: `data/cn/index_futures_margin_fee.yaml`.

| rule | value | basis |
|---|---|---|
| `margin_ratio` | fraction | exchange trading margin as a fraction of contract value, **non-hedge (speculative) positions**; hedge-position margin is not recorded. Exchange minimum — brokers add their own markup. |
| `trans_fee_rate` | fraction | exchange trading fee on turnover for opening and for closing positions opened on an earlier day. Per-order declaration fees are not included. |
| `close_today_fee_rate` | fraction | exchange trading fee on turnover for closing a position opened the same trading day (平今仓). Replaces `trans_fee_rate` for those fills. |
| `delivery_fee_rate` | fraction | exchange fee on delivery (final cash settlement) amount. CFFEX settlement-parameter XML field `JG_TRANSFEE_RATE` — **not** the close-today fee. |

Sources for these rules are CFFEX notices (`/cn/jystz/`, HTML, `hash_kind: text`) and the daily settlement-parameter XML
(`/sj/jscs/YYYYMM/DD/index.xml`, `hash_kind: bytes`; `quote` = the contract code and XML elements carrying the value, joined by ` … `).
Conditional effective dates in holiday notices ("first trading day after … without a one-sided market") are fixed from the XML of that day and say so in `notes`.

## Rule names · CFFEX stock-index futures trading (2026.11.02)

Data file: `data/cn/index_futures_trading.yaml`. Market `CCFX`; product scopes
`cffex_if`, `cffex_ih`, `cffex_ic`, `cffex_im`.

| rule | value | meaning |
|---|---|---|
| `price_limit_pct_of_prev_settlement` | fraction, e.g. `0.1` | ordinary-day symmetric maximum price band relative to the **previous trading day's settlement price**. Like `price_limit_pct_of_issue_price`, its basis differs from previous close, so `limit_price(prev_close, …)` must not be used with it. |
| `session_schedule` | `{open_call, continuous, close_call}` | regular planned auction and continuous-trading windows in Beijing time, using the existing schedule shape; `close_call: null` means no closing call auction. Actual circuit-breaker halts and reopening auctions are not encoded. |
| `min_holding_days` | integer | in futures scopes, `0` means a position opened today may be closed today, not zero fees or unlimited opening. All four records are `single-source` inferences; their listing-day starts are not directly verified and `published_at` is null. |

Special-day price bands and early closes are described in notes, not encoded in separate scopes;
ordinary-day values must not be applied to listing-day or last-trading-day exceptions.
The 2016-01-01..2016-01-08 (exclusive) `0.07` is the daily maximum; it does not model the 5% stage
restriction or circuit breakers. The rules took effect on 2016-01-01; the first trading day was 2016-01-04.

## Rule names · CFFEX treasury bond futures (2026.11.02)

Data file: `data/cn/bond_futures.yaml`. Market `CCFX`; scopes `cffex_tf` (5-year, listed
2013-09-06), `cffex_t` (10-year, listed 2015-03-20), `cffex_ts` (2-year, listed 2018-08-17),
and `cffex_tl` (30-year, listed 2023-04-21).

| rule | value | meaning |
|---|---|---|
| `trans_fee_per_lot` | number, `unit: CNY` | Exchange trading fee in CNY per lot for opening or closing a position opened on an earlier trading day; excludes declaration fees and broker commissions. |
| `delivery_fee_per_lot` | number, `unit: CNY` | Exchange physical-delivery fee in CNY per lot, including dated concessions subject to eligibility exceptions in notes. |

Close-today fee exemptions are described only in notes. The 2025 and 2026 delivery-fee
halving does **not** apply to exchange-designated high-frequency traders, who still pay
5 CNY per lot; record values represent ordinary participants.
Existing `price_limit_pct_of_prev_settlement`, `session_schedule`, `min_holding_days` and
`margin_ratio` definitions apply. Margins are exchange-applied base non-hedge margins;
delivery-month increases and special-day exceptions are described in notes. Same-day
round trips remain `single-source` inferences, so a `verified` threshold returns `UNVERIFIED`.

TF has no product-level price-band or margin record during **[2015-03-16, 2015-09-12)**:
TF1512 and later use 1.2%, while TF1506/TF1509 retain the old 1.5% ordinary band and
base-margin regime until expiry. The 2015-03-10 notice and 20150316 settlement CSV support
the margin split; the 2015 contract rules arts. 21 and 26 support the price-band split.
Art. 9 sets the last trading day to the expiry month's second Friday: TF1509 expires
2015-09-11. New product-level records begin 2015-09-12; `known_gaps.yaml` declares both
omissions, and queries within the interval raise `KeyError` (`OUT_OF_COVERAGE` in `resolve()`).

## Rule names · SHFE commodity futures (2026.11.02)

Data file: `data/cn/shfe_futures.yaml`. Market `XSGE` (ISO 10383 MIC of the Shanghai Futures Exchange), asset class
`commodity_futures`; one scope per product (20), read from the contract code. Non-ferrous metals: `shfe_cu` (copper),
`shfe_al` (aluminium), `shfe_zn` (zinc), `shfe_pb` (lead), `shfe_ni` (nickel), `shfe_sn` (tin), `shfe_ao` (alumina),
`shfe_ad` (cast aluminium alloy). Precious metals: `shfe_au` (gold), `shfe_ag` (silver). Ferrous metals: `shfe_rb` (rebar),
`shfe_wr` (wire rod), `shfe_hc` (hot-rolled coil), `shfe_ss` (stainless steel). Energy and chemicals: `shfe_fu` (fuel oil),
`shfe_bu` (bitumen), `shfe_ru` (natural rubber), `shfe_sp` (pulp), `shfe_br` (butadiene rubber), `shfe_op` (offset printing
paper). **Coverage starts 2024-01-01**: earlier queries find no record (`KeyError`, `OUT_OF_COVERAGE`). Products listed
later are covered from their listing day — cast aluminium alloy **2025-06-10**, offset printing paper **2025-09-10** — and
queries before it also find no record. The margin and band records in force on 2024-01-01 start at the real change dates
(margin 2023-10-09 / band 2023-10-10, also natural rubber and pulp; alumina, fuel oil, bitumen and butadiene rubber
2023-12-28 / 2023-12-29; wire rod 2023-07-19 / 2023-07-20), not at the floor. `session_schedule` and `min_holding_days`
records start at the floor itself (2024-01-01; AD and OP at the listing day), not at the date the value took effect.

Existing definitions apply: `margin_ratio` (here the **speculative**, 一般持仓 position margin), `price_limit_pct_of_prev_settlement`,
`session_schedule` (with the optional `night` and `day_call` keys above) and `min_holding_days`.

- **General months.** SHFE sets margin and band per contract. The product-level value is the one for general contract
  months: the **minimum** over the product's contracts, leaving out for `margin_ratio` the two nearest expiries and
  contracts that hit a limit that day, for the band one-sided-market contracts and listing-day contracts. Not encoded
  (described in `notes`): the temporary raise on a one-sided-market day, the raises as delivery approaches, and the
  listing-day band. The listing-day double band (交易管理办法 art. 37) is never recorded: a new product's first record is
  its ordinary band from the listing day (cast aluminium alloy 7% on 2025-06-10, offset printing paper 6% on 2025-09-10,
  although that day's file shows 14% / 12%). Contracts can keep the double band for a long time while they have not traded
  (wire rod, bitumen, offset printing paper and others); each is left out from its first appearance until its first
  ordinary band, and the double band is cross-checked against that contract's speculative margin minus two percentage
  points.
- **Night sessions.** Gold and silver 21:00–02:30; rebar, hot-rolled coil, fuel oil, bitumen, natural rubber, pulp,
  butadiene rubber and offset printing paper 21:00–23:00; stainless steel, cast aluminium alloy and the other non-ferrous
  metals 21:00–01:00; each with `open_call` 20:55–21:00 and `day_call` 08:55–09:00. Wire rod has no night session
  (`night: null`, `day_call: null`, `open_call` 08:55–09:00). Cast aluminium alloy and offset printing paper had only a day
  session on their listing day (call 08:55–09:00); the records give the regular schedule and the notes say so.
- **Effective dates.** A margin takes effect on the first trading day whose settlement-parameter file shows the new value
  (notices say "自 X 收盘结算时起"); a band on the first trading day it applies to, which is one trading day later. The
  night session belongs to the next trading day. Conditional dates in holiday notices ("第一个未出现单边市的交易日") are
  fixed from the files, and the notes say so.
- **Sources.** SHFE notices (`/publicnotice/notice/YYYYMM/tYYYYMMDD_N.html`, `hash_kind: text`), the daily settlement-parameter
  file (`/data/tradedata/future/dailydata/jsYYYYMMDD.dat`, margin) and the daily trade-argument file
  (`/data/busiparamdata/future/ContractDailyTradeArgumentYYYYMMDD.dat`, band), both `hash_kind: bytes` (hash of the `.dat`
  bytes). For a `.dat` file, `quote` is the `"FIELD":value` fragments of one contract's row, joined by ` … `.
- **Gaps.** Wherever general months carry two values at once, no single product-level value exists and no record is
  made. `known_gaps.yaml` declares all 95 (G-0031..G-0125); queries inside them raise `KeyError` (`OUT_OF_COVERAGE` in
  `resolve()`). The band gap usually runs one trading day after the margin gap; because the two nearest expiries are left
  out of the margin sample, the two ends can differ by more.
  - Non-ferrous (G-0031..G-0072): in 2026 SHFE set levels for contracts already listed (已上市合约) apart from new listings
    (CU/AL/ZN/PB/AO 2703 on, NI/SN 2704 on). Margin has no record for [2026-03-17, 2026-04-29), [2026-05-06, 2026-09-29)
    and [2026-10-08, open) (NI/SN from 2026-04-16), the band one trading day later in each case; the holiday windows in
    between were uniform and are recorded.
  - Rebar 2024 (G-0083, G-0086, G-0087): the 2024-07-29 notice gave RB2410 a special margin (8%) from 2024-07-31 and set
    separate bands for RB2408/RB2409/RB2410 from 2024-08-01; margin [2024-07-31, 2024-08-16), band [2024-08-01,
    2024-09-30) and, after the uniform National Day window, again [2024-10-09, 2024-10-16).
  - Silver 2025-12 (G-0077, G-0080): AG2602 raised on its own from 2025-12-12; margin [2025-12-12, 2025-12-16), band
    [2025-12-15, 2025-12-31). These ends come from the contract leaving the sample, not from a new notice.
  - Gold and silver after New Year 2026 (G-0073, G-0075, G-0078, G-0081): the named near months kept the holiday levels
    while the other contracts were restored (margin from 2026-01-05, band from 2026-01-06, to the end of January / early
    February).
  - 2026 old vs new contracts in the precious and ferrous metals (G-0074, G-0076, G-0079, G-0082, G-0084, G-0085,
    G-0088..G-0101): gold and silver from 2026-05-18 / 05-19 (gold uniform again from 2026-07-02 / 07-03, silver open);
    rebar, wire rod, hot-rolled coil and stainless steel from 2026-03-17 / 03-18, uniform for the Labour Day window, then
    split again until rebar and hot-rolled coil 2026-05-19 / 05-20, stainless steel 2026-07-02 / 07-03, wire rod
    2026-09-29 / 09-30.
  - Fuel oil and bitumen (G-0102..G-0108): March 2026 notices set different levels for FU2604–2608 and FU2609–2703 (margin
    [2026-03-04, 2026-03-10), band [2026-03-05, 2026-03-11)); the 2026-06-23 notice lowered FU2608 on but not FU2607, band
    [2026-06-26, 2026-07-01); named FU contracts raised again, band from 2026-09-15 (open), margin [2026-10-12, 2026-11-02);
    named BU contracts raised from
    2026-10-12 (margin) / 2026-10-13 (band), open. Where a gap ends because the special contract left the sample, the next
    record is `single-source`.
  - 2026 old vs new contracts in natural rubber, pulp, cast aluminium alloy and offset printing paper (G-0109..G-0125):
    RU, SP and OP margin [2026-04-16, 2026-04-29) and [2026-05-06, 2026-07-10), RU and SP bands one trading day later (OP
    band only [2026-06-04, 2026-07-13), because its new contracts kept the listing-day double band until then); AD margin
    [2026-03-17, 2026-04-29), [2026-05-06, 2026-09-29) and [2026-10-08, open), band [2026-03-19, 2026-04-30), [2026-05-07,
    2026-09-30) and [2026-10-09, open).
- **Fees** are recorded so far for the non-ferrous and precious metals only (next subsection); the other SHFE products
  have no fee record and no fee gap yet.
- `session_schedule` and `min_holding_days` are `single-source` (undated trading-hours page; same-day round trip inferred
  from close-today fee notices and, for the products added after the non-ferrous metals, the risk-control rules' matching
  exception for closing same-day new positions), so a `verified` threshold returns `UNVERIFIED`. A few margin / band records with no
  located notice (value and date from the daily files only) are also `single-source`. The fuel-oil margin from 2026-11-03
  (0.16) is daily-file only as well: that day's notice raised only the two nearest expiries, which the sample leaves out.
  The bitumen margin from 2026-11-17 (0.12) is the same case: the split of gap G-0107 ended when the two raised contracts
  (BU2612, BU2701) became the two nearest expiries; no notice states the general-month value.

### SHFE exchange fees (2026.11.02, first batch)

Scopes `shfe_cu` `shfe_al` `shfe_zn` `shfe_pb` `shfe_ni` `shfe_sn` `shfe_ao` `shfe_ad` `shfe_au` `shfe_ag`, from
2024-01-01 (cast aluminium alloy from its listing day 2025-06-10). Only the exchange fee for **speculative / general
positions** is recorded: hedge-position fees, declaration fees (申报费) and broker commissions are not included. An open
end (`effective_to: null`) means no later change was found up to 2026-11-18, not a forecast.

| rule | value | meaning |
|---|---|---|
| `trans_fee_rate` | fraction | As for CFFEX: exchange trading fee on turnover for opening, and for closing a position opened on an earlier trading day. |
| `trans_fee_per_lot` | number, `unit: CNY` | As for CFFEX treasury bond futures: the same fee in CNY per lot. |
| `close_today_fee_rate` | fraction | As for CFFEX: exchange trading fee on turnover for closing a position opened the same trading day; replaces `trans_fee_rate` for those fills. |
| `close_today_fee_per_lot` | number, `unit: CNY` | Exchange trading fee in CNY per lot for closing a position opened on the same trading day; replaces trans_fee_per_lot for those fills and excludes declaration fees and broker commissions. |

Each product charges each fee in one form (rate or per lot) throughout the window; the other form has no record and no
gap. Loading refuses a `trans_fee_rate` or `close_today_fee_rate` outside [0, 0.01), and a `trans_fee_per_lot` or
`close_today_fee_per_lot` without `unit: CNY` or below 0 (CFFEX records included).

- **Units.** In the daily settlement-parameter file (`jsYYYYMMDD.dat`) `TRADEFEERATIO` is in **per mille** (‰):
  fraction = value / 1000 (copper 0.05 → 0.00005). `TRADEFEEUNIT` is CNY per lot. Basis: the 2024-10-28 alumina notice
  ("交易手续费调整为成交金额的万分之三，套期保值交易手续费调整为成交金额的万分之一点五") against 0.3 / 0.15 in the 2024-10-30 file.
- **`TTRADEFEERATIO` / `TTRADEFEEUNIT` (present from 2024-07-22) are the hedge-position fee, not the close-today fee.**
  The same alumina notice set AO2501's close-today fee at 6/10000 while the file shows `TTRADEFEERATIO` 0.15; the
  2024-07-29 tin notice set a close-today fee of CNY 18 (hedge close-today CNY 9) while the file shows `TTRADEFEEUNIT`
  1.5. They serve as cross-checks only; no hedge-fee records.
- **Close-today fees come from notices only**: the daily file has no close-today field. An absolute value is taken as
  stated, "免收" is recorded as 0 (a sourced 0, not a default), and a multiple of the opening fee would be converted to an
  absolute value. These records are therefore `single-source`. A trading-fee record is `verified` when a notice and the
  daily file agree, and `single-source` from the daily file alone — including the values already in force before 2024
  whose real start was not found (clipped at 2024-01-01; the notes say so). Alumina starts at its real change, 2023-09-08.
- **Contract-level differences: contract selectors, never the mode.** SHFE often prices contracts apart (named
  contracts, month categories, tiers that roll as expiry approaches). A record without a selector exists only on days
  when **all listed contracts carry the same value**; where they differ, each tier is a record with a `contracts`
  selector (Schema 1.2 above) and a query must give the contract — the mode or the minimum is never substituted. A
  selector interval ends on the first trading day on which all listed contracts agree again (usually when the special
  contract expires). Trading days in the window on which every listed contract had the same opening /
  closing-earlier-position fee:

  | product | uniform days | structure |
  |---|---|---|
  | cu, al, zn, pb, sn | 684 / 684 (100%) | uniform |
  | ad | 340 / 340 (100%) | uniform from listing |
  | ni | 649 / 684 (94.9%) | named contract NI2409 CNY 6, the others 3 (2024-05-13 → 2024-07-02) |
  | ao | 559 / 684 (81.7%) | named contracts AO2402 / AO2403 raised (2024-01-05 → 2024-03-18), AO2509 raised (2025-05-26 → 2025-09-16) |
  | au | 0 / 684 | month-category tiers rolling towards expiry; in 2025 also named-contract and general raises |
  | ag | 0 / 684 | month-category tiers rolling towards expiry (0.01‰ / 0.05‰) |

  Selectors in use (trading fee):

  | product | interval | higher tier | lower tier |
  |---|---|---|---|
  | au | 2024-01-01 → 2024-05-31 | `months_to_delivery` ≤ 2 and even delivery month, or June / December: CNY 10 | the rest: CNY 2 |
  | au | 2024-05-31 → 2025-04-25 | `months_to_delivery` ≤ 2, or June / December: CNY 10 | CNY 2 |
  | au | 2025-04-25 → 2025-05-16 | AU2506 alone CNY 20; the near-three / June / December tier otherwise CNY 10 | CNY 2 |
  | au | 2025-05-16 → 2025-06-03 | `months_to_delivery` ≤ 3, or June / December: CNY 20 | CNY 10 |
  | au | 2025-06-03 → open | `months_to_delivery` ≤ 2, or June / December: CNY 20 | CNY 10 |
  | ag | 2024-01-01 → open | `months_to_delivery` ≤ 2, or June / December: 0.00005 | 0.00001 |
  | ni | 2024-05-13 → 2024-07-02 | NI2409: CNY 6 | other contracts: CNY 3 |
  | ao | 2024-01-05 → 2024-03-18 | AO2402, AO2403: 0.0004 | 0.0001 |
  | ao | 2025-05-26 → 2025-09-16 | AO2509: 0.0003 | 0.0001 |

  The gold and silver tier rules are read from the daily files (every listed contract on every trading day is explained
  by them); no tier-setting notice was located, so those records are `single-source`. Close-today notices that price
  named contracts are records with a `code` selector; the other contracts in those windows are gaps carrying a `none`
  selector, unless a notice prices every other contract too (tin under the 2025-03-31 fee table: CNY 3 for every other
  contract and later listings).
- **Gaps** (30: G-0352..G-0355 and G-0364..G-0389). Close-today fee: CU, AL, ZN, PB from 2024-01-01 (open) — no dated product-wide history
  was located; NI, AU, AG, SN and AO over the windows not priced by a notice, split around the named-contract records
  (14 of them carry a `none` selector: "every contract except the named ones"). No trading-fee gap remains for these ten
  products: every contract-day 2024-01-02 → 2026-11-18 has a record.

### SHFE exchange fees, second batch (2026.11.05): ferrous metals, energy and chemicals

Scopes `shfe_rb` `shfe_wr` `shfe_hc` `shfe_ss` `shfe_fu` `shfe_bu` `shfe_ru` `shfe_sp` `shfe_br` `shfe_op` (OP from its
listing day 2025-09-10), same rules, units and method as the first batch, with contract selectors from the start
(112 records, 18 `verified`, 88 with a selector). Form: per lot for SS (CNY 2) and RU (CNY 3), turnover rate for the
others; no product changed form.

| product | days with one value across contracts | trading-fee structure |
|---|---|---|
| wr, ss, bu, ru, sp, br, op | 100% | uniform (BU 0.0001 → 0.00005 from 2024-04-26; SP, BR and OP cut in steps) |
| hc | 97 / 684 | uniform until 2024-05-31; then the near three calendar months and January / May / October contracts 0.0001, the other months 0.00002 (2024-05-29 notice) |
| rb | 0 / 684 | RB2410 / RB2501 at 0.0003 apart until 2024-08-28; from 2024-05-31 the same near-three / Jan-May-Oct tier as HC |
| fu | 15 / 684 | near months and January / May / September contracts 0.00005, the rest 0.00001; the near threshold alternated between one and two months in early 2024; 2026-03-11 one rate for all listed contracts, then the named FU2604–FU2703 (March 2026 notice) and FU2607 (June 2026) priced apart until 2026-07-01 |

The month tiers are read from the daily files and explain every listed contract on every trading day; the non-main-month
cut of 2024-05-29 (RB, HC, FU) is the only tier rule found as a notice. Initial records clipped at 2024-01-01 carry the
earliest 2023 file from which their own value holds without a break as `published_at`; the FU lower tier has none
(on 2023-12-29 FU2402 still paid the higher rate), so its `published_at` is null.

Close-today (notices only): BR and OP fully priced (BR 0.0001 → 0.00002 from 2024-04-26 with named-contract steps; OP
waived from 2025-11-10); BU waived from 2024-04-26; SP 0 for every contract from 2026-07-10; FU non-main months waived
from 2024-05-31 and the March / June 2026 notices; RB, WR, HC and RU for named contracts or month classes only. 35 gaps
(G-0390..G-0424, 25 with a `none` selector) cover the rest; SS has no located close-today notice in the window.

**Not yet encoded** (researched, no records):

- **Delivery fees** (`COMMODITYDELIVFEE*` in the daily file).
- **Hedge-position fees** (the `TTRADEFEE*` fields and the notices' 套期保值 rates).
- **Declaration fees** (申报费), charged per order message, not per fill.

## Rule names · INE commodity futures (2026.11.02)

Data file: `data/cn/ine_futures.yaml`. Market `XINE` (ISO 10383 MIC of the Shanghai International Energy Exchange, a
subsidiary of SHFE), asset class `commodity_futures`; one scope per product (5), read from the contract code: `ine_sc`
(crude oil), `ine_lu` (low sulphur fuel oil), `ine_nr` (TSR 20 rubber), `ine_bc` (bonded copper), `ine_ec` (container
freight index, Europe line). **Coverage starts 2024-01-01**: earlier queries find no record (`KeyError`,
`OUT_OF_COVERAGE`). The margin and band records in force on 2024-01-01 start at the real change dates (crude oil and low
sulphur fuel oil 2023-12-28 / 2023-12-29; TSR 20 rubber and bonded copper 2023-10-09 / 2023-10-10), not at the floor;
for EC general months carried different levels from 2023-12-27 / 2023-12-28, so its first margin / band records start
2024-01-04 / 2024-01-05 (known gaps below). `session_schedule` and `min_holding_days` records start at the floor itself
(2024-01-01), except EC, whose records start at its listing day **2023-08-18** (INE listing notice of 2023-08-11).

Existing definitions apply: `margin_ratio` (here the **speculative**, 一般持仓 position margin), `price_limit_pct_of_prev_settlement`,
`session_schedule` (with the optional `night` and `day_call` keys above) and `min_holding_days`.

- **General months — INE's own delivery ladder, not "the two nearest expiries".** INE sets margin and band per contract.
  The product-level value is the **minimum** over the product's general contract months. For `margin_ratio` a contract is
  left out once INE's risk-control rules (风险控制管理细则) put it on the delivery-ladder margin, judged for the **next**
  trading day because a new standard is collected at the preceding settlement (art. 5): crude oil (art. 64) and low
  sulphur fuel oil (art. 68) from the first trading day of the month before the delivery month; TSR 20 rubber (art. 72)
  and bonded copper (art. 78) from the month before the delivery month (with a further step in the delivery month); the
  container freight index (art. 85) from the seventh trading day before the last trading day (20%, then 30% from the
  second), so its margin sample drops a contract from the settlement eight trading days before expiry. Exclusion is by
  calendar month, not by a fixed count of contracts, and contracts that hit a limit that day are also left out. For the
  band, one-sided-market contracts of the previous day and listing-day contracts are left out (交易细则 art. 27: the
  listing-day double band persists until the contract first trades; each is tracked to its first ordinary band and
  cross-checked as 2 × (its speculative margin − 2 percentage points)), and for EC also the ±20% band of the
  last trading day (风险控制管理细则 art. 86). If every eligible contract is left out (EC around some expiries), the
  previous observable value is carried; this does not claim the excluded contracts were charged that value. Not encoded
  (described in `notes`): the temporary raise on a one-sided-market day, the delivery-ladder raises and the listing-day band.
- **Night sessions.** Crude oil 21:00–02:30; bonded copper 21:00–01:00; low sulphur fuel oil and TSR 20 rubber
  21:00–23:00; each with `open_call` 20:55–21:00 and `day_call` 08:55–09:00 (交易细则 art. 19). The container freight
  index has **no night session** (`night: null`, `day_call: null`, `open_call` 08:55–09:00). Day session for all five
  09:00–10:15 / 10:30–11:30 / 13:30–15:00, no closing call. Holiday eves without a night session are in `notes` only.
- **Effective dates.** As for SHFE: a margin takes effect on the first trading day whose settlement-parameter file shows
  the new value; a band on the first trading day it applies to (the file's `TRADINGDAY`), one trading day later. The night
  session belongs to the next trading day. Conditional dates in holiday notices ("第一个未出现单边市的交易日") are fixed
  from the files, and the notes say so.
- **Sources.** INE notices (many republished on shfe.com.cn under the INE name, `hash_kind: text`), the daily
  settlement-parameter file (`https://www.ine.cn/data/tradedata/future/dailydata/jsYYYYMMDD.dat`, margin) and the daily
  trade-argument file (`https://www.ine.cn/data/busiparamdata/future/ContractDailyTradeArgumentYYYYMMDD.dat`, band), both
  `hash_kind: bytes`, and the INE trading rules and risk-control rules (2023-08-11 revision, official `.doc`, `hash_kind:
  bytes`; quotes are text extracted from the official `.doc`). The rules supply the sample method, not an independent
  check of the numeric rate.
- **Gaps.** Wherever general months carry two values at once, no record is made. `known_gaps.yaml` declares 32
  (G-0126..G-0157); queries inside them raise `KeyError` (`OUT_OF_COVERAGE` in `resolve()`).
  - Crude oil and low sulphur fuel oil (G-0126..G-0137): March 2026 named-contract levels (margin from 2026-03-04, band
    from 2026-03-05, a few days); the old near months keeping a higher band to expiry at the end of June 2026 (band
    [2026-06-26 / 06-29, 2026-07-01)); named contracts raised again from 2026-09-14 (margin [2026-09-14, 2026-09-30), band
    from 2026-09-15, open) and margin from 2026-10-12 (open).
  - TSR 20 rubber (G-0138..G-0141): already-listed vs new contracts, margin [2026-04-16, 2026-04-29) and [2026-05-06,
    2026-07-10), band [2026-04-22, 2026-04-30) and [2026-05-07, 2026-07-13); the Labour Day window was uniform.
  - Bonded copper (G-0142..G-0147): margin [2026-03-17, 2026-04-29), [2026-05-06, 2026-09-29) and [2026-10-08, open); band
    [2026-04-28, 2026-04-30), [2026-05-07, 2026-09-30) and [2026-10-09, open) — later than the margin because the new
    contracts kept the listing-day double band; the Labour Day and National Day windows were uniform.
  - Container freight index (G-0148..G-0157): margin [2023-12-27, 2024-01-04), [2024-02-27, 2024-04-29), [2024-05-06,
    2024-06-24), [2026-03-04, 2026-03-09) and [2026-05-26, open); band one trading day later in each case.
- **Exchange fees (2026.11.05)**, from 2024-01-01, same rules, units and method as the SHFE fee subsections (40 records,
  8 `verified`, 31 with a contract selector). The INE daily file uses the SHFE fields: `TRADEFEERATIO` per mille and
  `TRADEFEEUNIT` CNY per lot (the 2026-03-09 notice and its attachment, "一般交易手续费率（‰）" / "一般交易手续费额（元/手）",
  against 40 and 0.1 in the 2026-03-11 file; CNY from the SC listing notice); `TTRADEFEE*` is the hedge fee (the same
  attachment lists general / hedge / close-today separately). SC is charged per lot (CNY 20), LU, NR, BC and EC on
  turnover (0.00001, 0.00002, 0.00001, 0.0006), uniform until 2026-03-11. From 2026-03-11 every already-listed SC / LU
  contract paid CNY 40 / 0.0001 while contracts listed later kept the old fee; the named higher-fee contracts were
  restored on 2026-05-19 and 2026-06-25, and the last one left the listing on 2026-07-01 (code selectors listing the
  named contracts). Close-today (notices only, `single-source`): SC and LU for the named contracts of the March, May and
  June 2026 notices; EC2504 and EC2506 at 0.0012 (2024 notices). 21 gaps (G-0425..G-0445, 15 with a `none` selector)
  cover the rest, including NR and BC close-today over the whole window.
- `session_schedule` and `min_holding_days` are `single-source` (undated trading-hours page, and for EC the listing
  notice; same-day round trip inferred from 风险控制管理细则 art. 15 "平当日新开仓位" and, for EC, the listing notice's
  close-today fee treatment), so a `verified` threshold returns `UNVERIFIED`. Six margin / band records whose value and
  date come from the daily files only (no matching notice located) are also `single-source`: EC margin 2024-01-04 and
  2024-06-24, EC band 2024-01-05 and 2024-06-25, SC and LU band 2026-07-01 (a specially set July contract left the
  sample).

## Rule names · CZCE commodity futures (2026.11.02)

Data file: `data/cn/czce_futures.yaml`. Market `XZCE` (ISO 10383 MIC of the Zhengzhou Commodity Exchange), asset class
`commodity_futures`; one scope per product (27), read from the contract code (CZCE codes carry a three-digit year-month,
`AP505` → AP). Agricultural: `czce_ap` (apple), `czce_cf` (cotton), `czce_cj` (dried jujube), `czce_cy` (cotton yarn),
`czce_pk` (peanut kernel), `czce_sr` (white sugar), `czce_oi` (rapeseed oil), `czce_rm` (rapeseed meal). Chemicals and
building materials: `czce_ta` (PTA), `czce_ma` (methanol), `czce_sa` (soda ash), `czce_fg` (flat glass), `czce_ur` (urea),
`czce_pf` (polyester staple fiber), `czce_px` (paraxylene), `czce_sh` (caustic soda). Ferroalloys: `czce_sf`
(ferrosilicon), `czce_sm` (silicomanganese). Added later in the same release: `czce_pr` (PET bottle chip, listed
2024-08-30), `czce_pl` (propylene, first in the daily file 2025-07-22), and the thinly traded `czce_wh` (strong wheat),
`czce_rs` (rapeseed), `czce_pm` (common wheat), `czce_ri` (early indica rice), `czce_jr` (japonica rice), `czce_lr` (late
indica rice) and `czce_zc` (thermal coal). **Coverage starts 2024-01-01** (PET bottle chip from its listing day 2024-08-30,
propylene from 2025-07-22; late indica rice ends 2026-01-19, the first daily file with no LR contract listed, which is
not claimed as a delisting date): earlier queries find no record (`KeyError`, `OUT_OF_COVERAGE`). The margin and band records in force on 2024-01-01 start at the real change dates where one was
observed in the daily files from 2023-01-03 (for example cotton yarn, peanut kernel, rapeseed oil, rapeseed meal, PTA and
polyester staple fiber margin 2023-10-09 / band 2023-10-10; flat glass 2023-09-05 / 2023-09-06), not at the floor; where
none was observed (ferrosilicon, silicomanganese, and strong wheat, rapeseed, common wheat, early indica rice, japonica
rice, late indica rice and thermal coal) the record starts at 2024-01-01 and the notes say so. Several products
start 2024 inside a gap (below). `session_schedule` and `min_holding_days` records start at the floor itself (2024-01-01; PET bottle chip and propylene at
their first coverage day).

Existing definitions apply: `margin_ratio` (here the **speculative**, 一般持仓 position margin), `price_limit_pct_of_prev_settlement`,
`session_schedule` (with the optional `night` and `day_call` keys above) and `min_holding_days`.

- **The daily settlement-parameter file.** `http://www.czce.com.cn/cn/DFSStaticFiles/Future/YYYY/YYYYMMDD/FutureDataClearParams.txt`
  (`hash_kind: bytes`) lists, per contract, `交易保证金率(%)` and `涨跌停板(%)` (`9` → 0.09, `±8` → 0.08), the one-sided-market
  flag and the fees. `quote` is the header line and one contract's row, joined by ` … `. The **margin** column applies
  from that day's settlement, so a margin's `effective_from` is the file date. The **price-limit** column is the band for
  the **next** trading day: the settlement price is the basis of the next trading day's limit (期货交易管理办法, 2023
  revision, art. 32), so a band's `effective_from` is the trading day after the file date (and its night session belongs to
  that trading day). Example: the 2024 National Day notice attachment ("9月27日结算时起") raised PTA and methanol to 10% /
  ±9; the 2024-09-27 file shows both, margin from 2024-09-27, band from 2024-09-30.
- **General months — CZCE's delivery ladder, not "the two nearest expiries".** The product-level value is the one shared
  by the product's general contract months. For `margin_ratio` a contract is left out once the delivery-ladder margin
  applies, judged for the **next** trading day because the new standard is collected from the preceding settlement
  (风险控制管理办法, 2018 revision, arts. 5, 7): for most products from the **16th calendar day of the month before
  delivery** (art. 5); for dried jujube (CJ) from the **1st** of that month. For dried jujube and peanut kernel no cited
  source quotes the boundary. Sparse delivery calendars are judged by the actual
  delivery month (an apple or peanut October contract is still a general month in June to August). For the band, contracts
  entering the delivery month on the next trading day, contracts flagged one-sided in the file (`U` or `D`) and listing-day
  contracts are left out (art. 15: the listing-day double band persists until the contract first trades; each is tracked
  from its first appearance to its first ordinary band). A record is made **only where all remaining contracts agree**;
  where they carry two values at once, no record is made and a known gap is declared (the minimum is not taken). If every
  eligible contract is one-sided, the previous observable value is carried; this does not claim the excluded contracts were
  charged that value. Not encoded (described in `notes`): the temporary raise on a one-sided-market day, the ladder raises
  and the listing-day band.
- **Thinly traded products: no band where every contract keeps the listing band** (maintainer decision 2026-11-03). Where
  every listed contract carries the doubled listing band throughout the window because it never trades (common wheat,
  early indica rice, japonica rice and late indica rice at ±14, thermal coal at ±20), the daily file shows no ordinary band
  at all. **No band record is made and a known gap covers the window**; an ordinary level stated in a notice before the
  window (for example the 2022 notice setting 7%) is not carried forward. Margin records are still made where the general
  months agree. Strong wheat is different: its ordinary 7% band is observed in the daily file (January to March 2023 and
  WH509 from 2025-08-15), so it has a band record, carried over the days on which every eligible contract keeps the listing
  band, as for one-sided days above.
- **Sessions.** Under the 2023 trading rules (arts. 26, 28, 30) the day session is 09:00–10:15 / 10:30–11:30 / 13:30–15:00;
  a product with a night session has its opening call in the five minutes before the night session, a product without one
  at 08:55–09:00. **CZCE has no separate day-session call auction for night-session products**: 08:55–08:59 only allows
  cancelling unfilled night-session orders, so `day_call` is `null`. No closing call. **Most CZCE `session_schedule`
  records are not yet present**: only polyester staple fiber and PET bottle chip have one (night 21:00–23:00 from their
  listing notices, `open_call` 20:55–21:00, `single-source`; PET bottle chip's listing day had a day session only, the night
  session belonging to the next trading day); for the other 25 products no dated source giving the night-session product list and
  closing time for the coverage window was located, and each is a known gap rather than hours carried over from another
  exchange or product.
- **Sources.** The daily files (2023-01-03 onward), the official attachment to the 2024 National Day notice (`.docx`,
  `hash_kind: bytes`, no publication stamp, so `published_at` is null), the 2018 risk-control rules and 2023 trading rules
  (web.archive.org copies of czce.com.cn, `hash_kind: text`), and product materials from czce.com.cn. CZCE's notice pages
  block automated retrieval, so **most values are `single-source`** (value and date from the daily file only); the method
  articles support the sample selection, not an independent check of the numeric rate. The 27 `verified` records are the
  2024 National Day raises, where the attachment and the daily file agree.
- **Gaps.** `known_gaps.yaml` declares 127 (G-0158..G-0284); queries inside them raise `KeyError` (`OUT_OF_COVERAGE` in
  `resolve()`). The band gap usually starts one trading day after the margin gap.
  - Agricultural (G-0158..G-0171, G-0178..G-0203): apple, cotton, dried jujube and cotton yarn carried contract-specific
    levels for months at a time (apple margin [2023-11-08, 2024-04-15), [2024-12-25, 2025-04-15) and [2026-02-24,
    2026-04-15); cotton and dried jujube from before the floor until 2024-04-15 / 2024-07-31, bands 2024-04-30 / 2024-09-02;
    cotton yarn [2024-09-02, 2025-01-15)); rapeseed oil and rapeseed meal in repeated windows between 2024-07 and 2026-04
    (13 gaps each). Peanut kernel and white sugar have no margin or band gap.
  - Chemicals and building materials (G-0204..G-0230, G-0237..G-0256): PTA, methanol and paraxylene mostly from 2026-02
    (PTA margin open from 2026-10-26, methanol from 2026-10-27, the three bands open from 2026-10-12), PTA and paraxylene
    also in 2025 and paraxylene's band in 2024-04 → 05; methanol's band [2023-10-10, 2024-01-02); urea in three windows
    2023-10 → 2024-09 and in 2026-03 → 04; soda ash 2026-03 → 04; flat glass 2025-04 and 2026-03 → 05; caustic soda bands
    2024-04 → 05 and 2026-03 → 07; polyester staple fiber [2026-02-24, 2026-08-14) (band [2026-02-25, 2026-09-01)).
    **Paraxylene and caustic soda have no margin records at all** ([2024-01-01, open)): no
    quotable source for their delivery-ladder boundary was obtained.
  - Ferroalloys (G-0257..G-0260): silicomanganese [2024-06-04, 2024-09-27) and [2024-10-08, 2024-12-13), band gaps starting one
    trading day later. Ferrosilicon has no margin or band gap.
  - Sessions (G-0172..G-0177, G-0231..G-0236, G-0261..G-0265; 17 gaps, [2024-01-01, open)): every product except polyester
    staple fiber.
  - PET bottle chip and propylene (G-0266..G-0271): **no margin records at all** (PET bottle chip [2024-08-30, open),
    propylene [2025-07-22, open)): no quotable source for their delivery-ladder boundary was obtained. Bands: PET bottle chip
    [2026-02-25, 2026-09-01), propylene [2026-03-11, 2026-09-01) and its first day [2025-07-22, 2025-07-23) (no listing notice
    giving the first-day ordinary band was obtained). Propylene session [2025-07-22, open).
  - Thinly traded products (G-0272..G-0284): bands for common wheat, early indica rice, japonica rice and thermal coal
    [2024-01-01, open) and late indica rice [2024-01-01, 2026-01-19) (rule above); late indica rice margin [2025-12-15,
    2026-01-19), when only the contract entering delivery remained; sessions for strong wheat, rapeseed, common wheat, early
    indica rice, japonica rice and thermal coal [2024-01-01, open) and late indica rice [2024-01-01, 2026-01-19). After
    2026-01-19 late indica rice has neither records nor gaps.
- **Exchange fees (2026.11.05)**, 182 records (all `single-source`, 90 with a contract selector), from 2024-01-01 (PR
  from 2024-08-30, PL from 2025-07-22, LR until 2026-01-19). The daily file carries both fees per contract —
  `交易手续费` (opening and closing earlier positions) and `日内平今仓交易手续费` (close-today) — with `手续费收取方式`:
  `绝对值` = CNY per lot (`trans_fee_per_lot` / `close_today_fee_per_lot`), `比例值` = **1/10000 of turnover**
  (`trans_fee_rate` / `close_today_fee_rate` = value / 10000; basis: the 2024-08-16 PET bottle chip listing notice,
  "成交金额的万分之一", against 1.00 / 比例值 on 2024-08-30, cross-checked with the 2024-10-21 soda ash and 2025-03-12 bottle
  chip notices). Close-today values are therefore daily observations here, not notice-only as at SHFE and INE; no gap.
  Rate products: MA, SA, UR, PX, SH, PR, and PL until 2026-06-08 (then CNY 3 / 0 per lot). Contract tiers (selectors)
  for CF, CJ, CY, OI, RM, SA, FG, UR, SF, SM and SH; the rest are uniform. Records stay `single-source`: the CZCE site
  answered the first request of the batch with HTTP 412, so its notices were read only as archived copies (Source
  policy above), which cannot raise a record to `verified`. Data uses four-digit codes (`sa2501`); callers may pass the
  exchange's three-digit code (`SA501`).
- `min_holding_days` 0 is `single-source`: inferred from the daily file publishing a close-today trading fee
  (`日内平今仓交易手续费`) for each product, so a `verified` threshold returns `UNVERIFIED`; it is not a claim of zero
  fees or unlimited opening.

## Rule names · GFEX commodity futures (2026.11.02)

Data file: `data/cn/gfex_futures.yaml`. Market `GFEX` (ISO 10383 MIC of the Guangzhou Futures Exchange; MIC and
operating MIC are both `GFEX`), asset class `commodity_futures`; one scope per product (5), read from the contract code
(`SI2501` → SI): `gfex_si` (industrial silicon), `gfex_lc` (lithium carbonate), `gfex_ps` (polysilicon, listed
2024-12-26), `gfex_pt` (platinum) and `gfex_pd` (palladium), both listed 2025-11-27. **Coverage starts 2024-01-01**
(polysilicon from its listing day 2024-12-26, platinum and palladium from 2025-11-27, each the date of the exchange's
listing notice and the first day the product appears in the settlement parameters): earlier queries find no record
(`KeyError`, `OUT_OF_COVERAGE`). Industrial silicon and lithium carbonate start 2024 inside a gap (margin until
2024-02-07, band until 2024-02-08): the settlement parameters show both raised from 2023-12-28, but no New Year notice
and restoration notice was located, so the observed level is not turned into a record. `min_holding_days` records start
at the floor itself (2024-01-01, or the listing day).

Existing definitions apply: `margin_ratio` (here the **speculative**, 投机 position margin of general months),
`price_limit_pct_of_prev_settlement` and `min_holding_days`. No `session_schedule` record is made (below).

- **Values come from notices.** Every margin and band record takes its value and date from a dated GFEX notice (holiday
  adjustments, product listings and ad-hoc adjustments). A margin applies from the settlement the notice names
  ("自…结算时起"), so its `effective_from` is that settlement day. The settlement price is the basis of the **next**
  trading day's limit, so a band set at the same settlement starts one trading day later. Conditional restorations
  ("恢复交易后，在…持仓量最大的合约未出现涨跌停板单边无连续报价的第一个交易日结算时起") are dated by the day the general-month
  margins return in the settlement parameters, and the notes say so. Example: the 2026 National Day notice raised the
  margin from the 2026-09-29 settlement and restored it after trading resumed on 2026-10-08; the band runs from 2026-09-30
  and from 2026-10-09.
- **The settlement-parameter page is a check, not a source.** The exchange's daily settlement parameters
  (`http://www.gfex.com.cn/gfex/rjscs/ywcs.shtml`) list each contract's speculative margin, but the data come
  from a POST-only endpoint whose response carries a server timestamp, so they cannot be cited with a stable content
  hash. They are used only to check every margin record day by day; gap evidence summarises what they showed. They do
  not publish the price band or a one-sided-market flag.
- **General months — GFEX's delivery ladder.** The product-level margin is the one shared by the product's general
  contract months. A contract is left out once the delivery-ladder margin applies, judged for the **next** trading day
  because a new standard is collected from the preceding settlement (风险管理办法 art. 9): for industrial silicon and for
  lithium carbonate contracts before LC2512 from the **15th trading day** of the month before delivery (10%; 20% in the
  delivery month; product rules art. 13); for LC2512 and later, polysilicon, platinum and palladium from the **10th
  trading day** (lithium carbonate art. 13 as revised 2024-12-06, applying to LC2512 and later contracts only; polysilicon,
  platinum and palladium art. 12). If the month before delivery has fewer trading days, no boundary is invented.
  Contracts on their listing day are left out, except on a product's first day where the listing notice sets the same
  ordinary margin. A `verified` margin record is made **only where every remaining contract equals the notice
  standard**; because no independent one-sided-market flag is available, days where they differ or sit above it are
  known gaps, not silently discarded contracts, and no temporary raise is recorded.
- **Bands.** The record holds the ordinary general-month band; delivery-month exceptions, one-sided-market widening and
  the doubled listing-day band are not encoded (polysilicon's 14% listing-day band is not a record; its ordinary 7%
  starts on the listing day). Bands are `single-source`: the value and date come from the notice only, because the
  settlement parameters do not publish the band; restoration dates are cross-checked against the return of the margins.
  For platinum and palladium no notice giving the band in force from listing was located, so their first weeks are
  gaps rather than the lowest contract-level value.
- **Sessions are gaps.** The 2024 trading management rules give the three day-session segments and the call-auction
  rules for products with and without a night session, but leave the night-session product list to separate notices.
  No dated chain giving each product's night-session status and hours over the window was located, so all five products
  have a session gap and neither a night session nor its absence is asserted.
- **Sources.** 28 web.archive.org `id_` copies of gfex.com.cn pages: notices (`hash_kind: text`), the product rules
  (current and earlier versions), the risk-management rules and the settlement rules, and three PDF / DOCX rule
  attachments (`hash_kind: bytes`; quotes are from the text layer). Rule texts carry no publication stamp in the source
  (`date: null`); `published_at` is the notice date.
- **Gaps.** `known_gaps.yaml` declares 60 (G-0285..G-0344); queries inside them raise `KeyError` (`OUT_OF_COVERAGE` in
  `resolve()`). The band gap usually starts one trading day after the margin gap. Three kinds: 36 windows with no
  complete dated notice chain (the settlement parameters changed, but are not a source), 19 windows where the remaining
  general months did not all equal the notice standard, and 5 session gaps.
  - Lithium carbonate (G-0285..G-0300): margin [2024-01-01, 2024-02-07), [2024-04-29, 2024-09-27), [2025-09-29,
    2025-12-30) and [2026-02-12, 2026-09-29), bands one trading day later; seven short non-uniform margin windows (one or two
    trading days) in 2025-07 → 08 and 2026-01 → 02; session [2024-01-01, open).
  - Palladium and platinum (G-0301..G-0310, G-0325..G-0334): margin [2025-11-27, 2025-12-30), [2026-01-13, 2026-02-05),
    [2026-02-12, 2026-03-24) and [2026-04-29, 2026-07-03), bands one trading day later, plus one non-uniform margin
    window around the 2026 New Year (palladium 2025-12-30, platinum [2025-12-30, 2026-01-05)); session [2025-11-27, open).
  - Polysilicon (G-0311..G-0324): margin [2025-09-29, 2025-12-30) and [2026-04-29, 2026-09-29), bands one trading day
    later; nine short non-uniform margin windows in 2025-07 → 09 and 2026-04 (PS2605 kept 15% until 2026-04-14 while the
    other general months were at 13%); session [2024-12-26, open).
  - Industrial silicon (G-0335..G-0344): margin [2024-01-01, 2024-02-07), [2024-04-29, 2024-06-06), [2025-09-29,
    2025-12-30) and [2026-02-12, 2026-09-29), bands one trading day later; one non-uniform margin day 2025-07-22; session
    [2024-01-01, open).
- **Exchange fees (2026.11.07)**, 99 records (all `single-source`, 80 with a contract selector) and 67 gaps (G-0446..G-0512,
  49 with a contract selector), from 2024-01-01 (polysilicon from 2024-12-26, platinum and palladium from 2025-11-27).
  Same rules as the SHFE fee subsections, speculative only: `trans_fee_rate` (opening and closing earlier positions) and
  `close_today_fee_rate` (日内平今仓); every GFEX fee in the window is a share of turnover. **Values and dates come from
  notices**, as for margins: the listing notices (industrial silicon and polysilicon "成交金额的万分之一", lithium carbonate
  "成交金额的万分之零点八，平今仓交易暂免收交易手续费"), the 2023-03-30 notice waiving the industrial silicon close-today fee,
  and eight adjustment notices 2024-02-05 → 2026-07-07 that name contracts (selectors by `code`, the rest of the product
  as the complement). A change "自…交易时起" first shows in the settlement parameters on that same trading day. The
  settlement parameters (opening = closing = short-term opening fee on every contract-day, short-term closing = the
  close-today fee) check every listed contract on every trading day; where they changed and no notice was located, the
  contracts concerned are a gap, not a record: lithium carbonate's December 2023 raises (LC2401–LC2411 into 2024), LC2601
  from 2025-11-20, the 2026-01-15 and 2026-09-22 lithium carbonate changes, polysilicon at 5/10000 from 2025-12-29 to
  2026-04-03, the platinum and palladium fee from listing (only PT2606 and PD2606 at 1/10000 from 2026-04-27 to
  2026-06-15 have a notice), and contracts listed after a notice whose own fee chain was not located. All sources are
  web.archive.org copies, so records stay `single-source`.
- `min_holding_days` 0 is `single-source`: inferred from the settlement rules (结算管理办法 art. 46), which compute the
  profit and loss of closing a position opened the same day (平当日仓盈亏), so a `verified` threshold returns
  `UNVERIFIED`; it is not a claim of zero fees or unlimited opening.

## Rule names · Hong Kong equities (XHKG) (2026.11.02)

Data file: `data/hk/equity.yaml`; scope registry `data/hk/scopes.yaml`; known gaps `data/hk/known_gaps.yaml`. Market
`XHKG` (ISO 10383 MIC of the Stock Exchange of Hong Kong), asset class `equity`; ids `hk.<rule>.<scope>.<effective_from>`.
The first market outside mainland China, so it has its own registry directory (`market_prefix` `hk`):
`coverage()`, `gaps_for()` and `contract.resolve()` choose it from the market (`marina_rules.market_prefix_for`:
`XHKG` → `hk`, everything else → `cn`), and `scopes("hk")`, `known_gaps("hk")`, `capabilities("hk")` read it directly.
Gap ids use their own namespace `G-HK-NNNN`. **Coverage starts 2010-01-01**; earlier dates are out of scope.

Three scopes. `hk_stock` and `hk_etf` are selected by instrument type alone and exclude each other; only the ETF spread
table needs context (`spread_table`, Context keys above):

- `hk_stock` — ordinary shares on the Main Board and GEM, including H shares and red chips.
- `hk_etf` — exchange-traded funds, excluding leveraged and inverse products. For `tick_size_table` it requires
  `spread_table`: `part_a` before 2020-06-01, `part_d` from 2020-06-01 (`rule_asserts`); `part_b` is a contradiction.
- `hk_etf_part_b` — the same ETFs when traded on Part B of the Second Schedule (before 2020-06-01 fixed-income and
  currency ETFs; from 2020-06-01 fixed-income ETFs whose manager kept Part B). Requires `spread_table: part_b`; excludes
  `hk_stock` but not `hk_etf`, because it is selected for the spread table only: the same ETF's fees, sessions and VCM
  are asked under `hk_etf` (as A-share `stock` and the board scopes coexist).

Not covered (no scope, no record): REITs, derivative warrants, callable bull / bear contracts, inline warrants, equity
warrants and rights, debt securities, leveraged and inverse products. Board lot is not recorded; the spread table
(`tick_size_table`, below) is recorded for shares and ETFs.

New rules (amounts are fractions of the consideration unless a `unit` is given):

| rule | value | meaning |
|---|---|---|
| `transaction_levy_each_side` | fraction | SFC transaction levy on the consideration, charged separately to buyer and seller (rounded to the nearest cent). |
| `afrc_levy_each_side` | fraction | AFRC transaction levy on the consideration, charged separately to buyer and seller (rounded to the nearest cent). |
| `trading_fee_each_side` | fraction | Exchange trading fee on the consideration, charged to each side (rounded to the nearest cent). |
| `settlement_fee_each_side` | `{rate, min, max}` + `unit: HKD` | CCASS stock settlement fee per side of an ordinary, non-crossed Exchange Trade: `rate` × gross value, floored at `min` and capped at `max` (HKD; `null` = no floor / cap). Charged to clearing participants. |
| `trading_tariff_per_trade` | number + `unit: HKD` | Exchange trading-system tariff on each purchase or sale transaction. `0` = removed (a sourced fact, not a default). |
| `settlement_cycle_days` | integer | settlement days from trade date to scheduled CCASS settlement between Exchange Participants and the clearing house (T+2 = `2`; non-settlement days do not count). Client terms may differ. |
| `tick_size_table` | list of `{gt \| ge, le, tick}` + `unit: HKD` | Ordered minimum price-increment bands: a price p falls in the band with `gt` < p ≤ `le` (the first band has `ge` instead, `ge` ≤ p ≤ `le`, so it includes the lowest permissible price), and `tick` is the increment in the stated currency. Bands meet end to end (each `gt` equals the previous `le`; checked at load). Not `tick_size`: it has no tick family and `tick_size()` does not read it. |
| `closing_auction_limit_pct` | fraction | Symmetric outer CAS order-price limit as a fraction of the CAS reference price, conditional on CAS eligibility (the value describes CAS securities only). An intraday band, not a daily price limit: `limit_price()` does not use it. |
| `vcm_trigger_pct` | `{tier: fraction}` | Tier-specific fractional deviation from the last automatch traded price five minutes earlier that triggers a cooling-off period. A security in no listed tier is not subject to the VCM; tier membership on the trade date is the caller's (Marina stores no index constituents or VCM lists). |
| `investor_compensation_levy_each_side` | fraction | Investor Compensation Fund levy as a fraction of consideration charged separately to buyer and seller; zero denotes a sourced suspension. In [0, 1); checked at load. |
| `opening_auction_limit_pct` | fraction | Symmetric outer POS at-auction limit-order price band as a fraction of the POS reference price; narrower executable-order limits remain in notes. In (0, 1); checked at load (as is `closing_auction_limit_pct`). An intraday band, not a daily price limit: `limit_price()` does not use it. |
| `short_sale_price_test` | `{restriction, duration}` | Standing short-sale price test in continuous trading; auction-specific floors and exemptions are stated in notes. Exactly these two keys, each one of the values below (no `none`); checked at load for market `XHKG`. The same rule name has a different shape for US equities (US section); the loader checks each market's shape. Describes designated securities for short selling only; the designation and exemption lists are the caller's (Marina stores none). |
| `order_spread_limit` | `{max_spreads, wider_pct, reference}` | Passive-side CTS limit-order quotation boundary: `max_spreads` spread steps from `reference`, or, where `wider_pct` is set, the wider of that and the `wider_pct` alternative; empty-book and first-quotation fallbacks are specified in notes. Continuous trading only: auction orders are excluded (see `opening_auction_limit_pct` / `closing_auction_limit_pct`). Exactly these keys, each as below; checked at load, for market `XHKG` only. Not a daily price limit: `limit_price()` does not use it. |
| `order_price_multiple_limit` | `{max_multiple, reference}` | Exclusive upper and reciprocal lower multiplicative order-price thresholds; reject P >= N*R or P <= R/N when the prescribed reference is available (N = `max_multiple` > 1, R = the `reference` price; equality at either threshold is rejected). Exactly these two keys; checked at load, for market `XHKG` only. Not a daily price limit: `limit_price()` does not use it. |

Values of `short_sale_price_test` (Hong Kong):

| field | value | meaning |
|---|---|---|
| `restriction` | `not_below_best_ask` | Ordinary short-sale order price must be at or above the current best ask in continuous trading. |
| `restriction` | `exempt` | Eligible ETF short sales are exempt from the price tick test for all participants; designation, coverage and order-type requirements remain. |
| `duration` | `always` | The restriction or exemption is standing and requires no price-decline trigger; it does not mean trading is permitted in every session. |

Fields of `order_spread_limit` and `order_price_multiple_limit`:

| field | value | meaning |
|---|---|---|
| `max_spreads` | positive integer | Number of spread steps in the spread component (24); it is not an unconditional maximum distance once `wider_pct` is set. A spread is the minimum price change of the security's applicable spread table (`tick_size_table`) on the date. |
| `wider_pct` | `null` \| fraction in (0, 1) | Percentage alternative to `max_spreads`, as a fraction of the reference price: the boundary is whichever of the two is wider (the lower price below the reference, the higher above it), the percentage result rounded to a valid spread (rounded up below the reference, rounded down above it). `null` = spread component only. |
| `reference` (`order_spread_limit`) | `same_side_best_or_rule_fallback` | Current best bid for buys or best ask for sells when that side exists; otherwise the side-specific extreme of opposite quote, previous close and day low/high, with last-opposite-quote fallback when both queues are empty; first CTS quotations use previous close. |
| `max_multiple` | number > 1 | N in the multiplicative check. |
| `reference` (`order_price_multiple_limit`) | `nominal_or_previous_close_for_opening` | Rule 505A nominal price, except the first quotation governed by Rule 503 uses previous closing price; this is a legal-case selector, not a caller-selected reference. |

VCM tier keys (`vcm_trigger_pct`):

| key | securities |
|---|---|
| `hsi_hscei_constituents` | Constituents of the Hang Seng Index or Hang Seng China Enterprises Index (the original 2016 stock universe). |
| `hsci_largecap_constituents` | Constituents of the Hang Seng Composite LargeCap Index. |
| `hsci_midcap_constituents` | Constituents of the Hang Seng Composite MidCap Index. |
| `hsci_smallcap_constituents` | Constituents of the Hang Seng Composite SmallCap Index. |
| `vcm_eligible_etfs` | ETFs on the effective HKEX VCM list under the quarterly turnover / listing-age entry and retention criteria in ETP/001/22; excludes leveraged and inverse products. |

Existing rules with their usual meaning: `stamp_duty_buy` / `stamp_duty_sell` (ad valorem duty on the bought / sold
contract note), `price_limit_pct`, `session_schedule`, `min_holding_days`.

**Verification.** `verified` only where two independent publishers support value and date (Inland Revenue Department /
GovHK / the Government's press release on one side, HKEX on the other). HKEX and HKSCC are one group and count as one
publisher; a fee resting on HKEX / HKSCC texts alone is `single-source`; SFC texts available only as archived copies do
not count as a second publisher. 6 records are `verified` (stamp duty), 69 `single-source` (the spread table,
closing-auction, VCM, pre-opening, short-selling, quotation-spread and multiple-check records rest on HKEX texts alone;
an HKEX circular stating that the SFC approved a rule change is not a second publisher's text; the Investor Compensation levy
records add a Government announcement, but the SFC's original 2005 exemption notice was not obtained). Many records have `published_at: null` (fee pages and FAQs carry no publication stamp), so `as_of`
queries on them are `UNKNOWN_PUBLICATION`.

Timelines (`hk_stock` and `hk_etf` share every fee record's value and sources unless stated):

- **Stamp duty**, both sides: 0.1% (record from 2001-09-01) → **0.13% from 2021-08-01** → **0.1% from 2023-11-17**
  (`hk_stock`; the 2021 and 2023 changes `verified`). The computed duty is rounded **up** to HKD 1 (notes); the
  consideration is not rounded up to HKD 1,000 in this window. `hk_etf`: **0 from 2015-02-13**, the statutory waiver for
  all ETFs (`verified`); before it the duty depended on the fund (G-HK-0002 / G-HK-0003).
- **SFC transaction levy**: 0.004% (record from 2006-12-01) → 0.003% from 2010-10-01 → 0.0027% from 2014-11-01.
- **AFRC transaction levy**: 0.00015% from 2022-01-01. The levy did not exist before; there is no record and no gap
  before commencement (as for a product before its listing day), so a query for 2021 is `OUT_OF_COVERAGE` without a gap id.
- **Trading fee** 0.005% → **0.00565% from 2023-01-01**; **trading tariff** HKD 0.50 per trade → **0 from 2023-01-01**.
  The pre-2023 values are stated by the 2022 circular as the existing structure; their original start was not located,
  so those records start at the coverage floor.
- **Settlement fee** `{rate: 0.00002, min: 2, max: 100}` → **`{rate: 0.000042, min: null, max: null}` from 2025-06-30**.
  Crossed trades (half the rate, floor and cap; 0.0021% from 2025-06-30) and eligible ETF market-maker trades (0.002% /
  0.001% crossed from 2025-06-30) differ and are in `notes`, not encoded; so are SI transactions.
- **Settlement cycle** T+2 and **same-day resale** (`min_holding_days` 0), both from the coverage floor, `single-source`:
  T+2 from the HKEX operations FAQ (ETPs also from the ETP trading-arrangements leaflet); day trading from the Stock
  Connect investor book (Southbound investors may day-trade Hong Kong stocks), applied to ETFs by analogy with HKEX's
  "ETFs trade like stocks". Neither permits naked short selling.
- **No daily price limit**: `price_limit_pct` is `unlimited` from 2010-01-01 for both scopes (`single-source`): HKEX states
  that securities listed on the Exchange are not subject to trading bands, and its 2016 announcement says the Volatility
  Control Mechanism must not be confused with the daily price limits of some markets. `limit_price()` returns `None`, as for
  A-share `unlimited` scopes. The **VCM** (from 2016-08-22, a cooling-off period on individual stocks) and the **closing
  auction's ±5% band** around the reference price are intraday mechanisms, recorded separately as `vcm_trigger_pct` and
  `closing_auction_limit_pct` (below), as is the pre-opening session's ±15% band (`opening_auction_limit_pct`, from
  2020-10-19); none changes `price_limit_pct` or `limit_price()`. The start is truncated at the
  coverage floor (no earlier text was cited).
- **Spread table** (`tick_size_table`, `hk_stock`, Part A of the Second Schedule, HKD; the same numbers apply to other
  quotation currencies, not recorded): from the coverage floor the 11-band table restated by HKEX's 2024 consultation
  (previous reform 2006-07-24; continuity to 2010 is an inference) → **phase 1 from 2025-08-04** (over 10 to 20: 0.02 →
  0.01; over 20 to 50: 0.05 → 0.02, a new band) → **phase 2 from 2026-08-03** (over 0.50 to 10: 0.01 → 0.005, merged with
  over 0.25 to 0.50). Every share table runs from 0.01 to 9,995. ETFs were excluded from both phases (ETF tables below).

  | price band (HKD) | to 2025-08-04 | 2025-08-04 | 2026-08-03 |
  |---|---|---|---|
  | 0.01 – 0.25 | 0.001 | 0.001 | 0.001 |
  | over 0.25 – 0.50 | 0.005 | 0.005 | 0.005 |
  | over 0.50 – 10 | 0.01 | 0.01 | 0.005 |
  | over 10 – 20 | 0.02 | 0.01 | 0.01 |
  | over 20 – 50 | 0.05 | 0.02 | 0.02 |
  | over 50 – 100 | 0.05 | 0.05 | 0.05 |
  | over 100 – 200 / 500 / 1,000 / 2,000 / 5,000 / 9,995 | 0.1 / 0.2 / 0.5 / 1 / 2 / 5 | same | same |

- **ETF spread tables** (`tick_size_table`, HKD, context `spread_table`): `hk_etf` **Part A** (the shares' 11-band table
  above) from the coverage floor to 2020-06-01 → **Part D from 2020-06-01** (ETP/004/20 of 2020-05-18; the current
  Second Schedule restates it; unchanged by the 2025 / 2026 share reductions, which exclude ETPs). `hk_etf_part_b`
  **Part B** from the coverage floor, open-ended: one band, HKD 0.05 from 0.50 to 9,999.95 (`{ge: 0.5, le: 9999.95,
  tick: 0.05}`; prices below 0.50 are outside it). Before 2020-06-01 the undated ETP trading-arrangements leaflet puts
  ordinary ETPs on Part A and fixed-income and currency ETPs on Part B; from 2020-06-01 Part B remains an option only for
  fixed-income ETFs at the manager's preference. Starts at the coverage floor are truncations; continuity is a
  single-publisher inference. Which Part an ETF used on a date is the caller's; Marina does not infer it.

  | price band (HKD) | Part D (from 2020-06-01) |
  |---|---|
  | 0.01 – 1 | 0.001 |
  | over 1 – 5 | 0.002 |
  | over 5 – 10 | 0.005 |
  | over 10 – 20 | 0.01 |
  | over 20 – 100 | 0.02 |
  | over 100 – 200 / 500 / 1,000 / 2,000 / 9,999 | 0.05 / 0.1 / 0.2 / 0.5 / 1 |

- **Closing auction price limit** (`closing_auction_limit_pct`, both scopes): **±5% of the CAS reference price from
  2016-07-25**, unchanged since (the 2016 rule and briefing already state ±5%; the 2017 phase-2 amendment keeps it). The
  reference price is the median of five nominal-price snapshots taken at 15-second intervals from 15:59:00 to 16:00:00;
  the band applies to order input 16:01–16:06, after which a possibly tighter band between the lowest ask and highest bid
  at 16:06 applies (in `notes`). No reference price → no CAS price limit that day. All ETFs were CAS securities from phase
  1; shares were phased in until 2019-10-08 (the value describes CAS securities only). No record and no gap before
  2016-07-25 (the mechanism did not exist).
- **VCM trigger** (`vcm_trigger_pct`): `hk_stock` **`{hsi_hscei_constituents: 0.1}` from 2016-08-22** (at most one
  trigger per stock per session) → **`{hsci_largecap_constituents: 0.1, hsci_midcap_constituents: 0.15,
  hsci_smallcap_constituents: 0.2}` from 2020-05-11** → same fractions from **2021-03-29**, when multiple triggers per
  session were allowed (a separate record so the notes match the mechanism). `hk_etf` **`{vcm_eligible_etfs: 0.05}` from
  2022-05-03**; ETFs were outside the VCM before, so there is no record and no gap. The reference is the last automatch
  traded price five minutes earlier; a five-minute cooling-off period restricts trading to the same band; no monitoring in
  POS or CAS, the first 15 minutes of the morning and afternoon sessions, or the last 20 minutes of the final session (in
  `notes`). The VCM has not been extended to the closing auction.
- **Investor Compensation Fund levy** (`investor_compensation_levy_each_side`, both scopes, secondary-market ETF units
  included): **0 from 2005-12-19**, when the SFC suspended the levy (unsuspended rate 0.002% per side, `0.00002`, rounded
  to the nearest cent; in `notes`); `published_at` 2005-11-11, the SFC exemption notice's date as reported by HKEX's
  CT/134/19 (the notice itself was not obtained). A same-value record from **2020-01-01**, when the suspension /
  reinstatement trigger levels of the fund's net assets rose from HKD 1.4 billion / 1 billion to HKD 3 billion / 2
  billion without affecting the suspension in force. The suspension lasts until the SFC publishes a termination notice,
  and reinstatement cannot take effect earlier than two months after it; no reinstatement was found before 2026-11-04.
- **Pre-opening price limit** (`opening_auction_limit_pct`, both scopes): **±15% from 2020-10-19** (POS enhancement,
  covering all equities and ETFs), the first-stage outer band for at-auction limit orders 09:00–09:15 around the POS
  reference price: the previous close, adjusted on ex-dates. ETFs on their listing day use the pre-listing NAV per unit as
  reference; ordinary IPO shares and securities resuming from suspension have no first-stage check (in `notes`). From
  09:15 to the random match (at the latest 09:22) new executable orders must lie between the lowest ask and highest bid
  recorded at 09:15 (the inner band, in `notes`; not encoded). A same-value record from **2026-11-02**, when the
  additional quotation check tightened from nine to five times the nominal price; the 15% band did not change. Before
  2020-10-19 the old POS had no fixed price range (only the nine-times rule): known gaps G-HK-0005 / G-HK-0006, not a
  value.
- **Short-selling tick rule** (`short_sale_price_test`): `hk_stock` `{restriction: not_below_best_ask, duration:
  always}` — a short sale of a designated security may not be made below the best current ask in continuous trading
  (Rule 563D, Eleventh Schedule (15)) — from the coverage floor (a truncation: the start of the regime was not
  established; HKEX stated the rule in 2001), with same-value records from **2017-07-24** (short-sale input in the closing
  auction at or above the CAS reference price), **2020-10-19** (input in the pre-opening session at or above the POS
  reference price) and **2023-06-19** (Dual Counter Market Maker short selling exempt from all three floors); the
  auction floors and the market-maker, index-arbitrage and hedging exemptions are in `notes`. `hk_etf` `{restriction:
  exempt, duration: always}` from **2002-03-25** (all ETFs exempt from the tick rule for all participants, HKEX's
  2002-03-28 status report; `published_at` null, the report is later than the start), with same-value records from
  **2017-07-24**, **2020-10-19** (CAS / POS input, still exempt) and **2024-11-01** (securities market makers may enter
  ETF market-making orders in POS and CAS). `exempt` lifts the price test only: designation, covering and order-type
  requirements remain, and naked short selling is prohibited (SFO s. 170(1)). Which securities are designated for short
  selling on a date is the caller's.
- **Quotation spread limit** (`order_spread_limit`, both scopes, `reference` `same_side_best_or_rule_fallback`): **24
  spreads from 2005-07-04** (eight → twenty-four spreads; HKEX's 2005-06-29 announcement and the rule-amendment register:
  a sourced start before the coverage floor, continuity to later restatements a single-publisher inference), `wider_pct`
  null → `hk_etf` **from 2023-03-20** the wider of 24 spreads or 3.5% (`wider_pct` 0.035; the dual-structure price limit
  for exchange traded products, ETP/001/23) → `hk_stock` **from 2025-08-04** the wider of 24 spreads or 5% (`wider_pct`
  0.05; introduced with the first minimum-spread reduction, LSD/030/2025, for all price bands). Under Rules 506A / 507A a
  limit buy may go down to the lower of 24 spreads or the percentage below the current bid (the percentage result rounded
  up to a valid spread), and a limit sell up to the higher of 24 spreads or the percentage above the current ask (rounded
  down). With both queues present a buy is bounded below by the best bid and above by the best ask, a sell above
  by the best ask and below by the best bid; the missing-queue and first-quotation fallbacks, the waiver of Rule 504 and
  the different enhanced / special limit order boundaries are in `notes`. Spreads are counted on the security's own spread
  table (an ETF on its Part A, B or D). Auction orders are excluded (Rule 505). The 2026-11-02 pre-trade reform did not
  change `max_spreads` or `wider_pct`.
- **Order-price multiple check** (`order_price_multiple_limit`, both scopes, `reference`
  `nominal_or_previous_close_for_opening`): reject a price P ≥ N × R or P ≤ R / N (both equalities rejected; not ±N%),
  where R is the nominal price (Rule 505A; POS: IEP, else previous close; CTS: last trade or previous close, replaced by a
  higher bid or a lower ask; CAS: IEP, else CAS reference price) or, for the opening quotation (Rule 503), the previous
  close. Applies in CTS and to priced at-auction limit orders in POS and CAS; unmatched POS at-auction limit orders are
  carried into CTS only if they pass it (Rule 501I). **N = 9 from the coverage floor** (a truncation: HKEX's 2008
  consultation describes the nine-times rule as an existing control; its original start was not found) → **N = 5 from
  2026-11-02** (pre-trade controls enhancements phase 1, Rules 501I, 503 and 505A; LSD/072/2026 of 2026-10-26 gives the
  effective date, CT/159/26 announced the launch, the rule-amendment register confirms it). Structured products keep nine
  times (outside both scopes). Phase 1 changed no other market-wide price or quantity parameter.

`session_schedule` (`hk_stock` only; Hong Kong time, ordinary full trading day):

| from | `open_call` | `continuous` | `close_call` |
|---|---|---|---|
| 2010-01-01 | 09:30–09:50 | 10:00–12:30, 14:30–16:00 | `null` |
| 2011-03-07 | 09:00–09:20 | 09:30–12:00, 13:30–16:00 | `null` |
| 2012-03-05 | 09:00–09:20 | 09:30–12:00, 13:00–16:00 | `null` (to 2016-07-25) |
| 2019-10-08 | 09:00–09:20 | 09:30–12:00, 13:00–16:00 | 16:01–16:10 |
| 2020-10-19 | 09:00–09:22 | 09:30–12:00, 13:00–16:00 | 16:01–16:10 |

- `open_call` is the pre-opening session's window in which auction orders may be entered, **up to the start of
  matching** (order input and pre-order matching / no-cancellation periods); order matching and the blocking period up
  to the open are excluded. Since 2020-10-19 matching starts randomly between 09:20 and 09:22; 09:22 is the latest end.
- `close_call` is the closing auction's **input window 16:01–16:10**: the reference-price fixing period 16:00–16:01 accepts
  no orders, and the auction closes randomly between 16:08 and 16:10 (in `notes`).
- Not modelled: half-day trading (Christmas, New Year and Lunar New Year eves), severe-weather trading (from 2024-09-23)
  and halts.
- The closing auction was phased in 2016-07-25 / 2017-07-24 for eligible securities only, so one schedule cannot describe
  all of `hk_stock` until it covered all equities on 2019-10-08: that window is gap G-HK-0001. `hk_etf` has no session
  record (G-HK-0004; rechecked in the second batch, still open).

**Gaps.** `data/hk/known_gaps.yaml` declares 6; queries inside them raise `KeyError` (`OUT_OF_COVERAGE` with the gap id in
`resolve()`):

- G-HK-0001 `hk_stock` / `session_schedule` [2016-07-25, 2019-10-08): closing-auction phase-in, CAS and non-CAS stocks in
  one scope. Phase 1 (2016-07-25): HSCI LargeCap and MidCap constituents, H shares with Mainland-listed A shares, all
  ETFs; phase 2 (2017-07-24): plus HSCI SmallCap constituents; all equities from 2019-10-08.
- G-HK-0002 / G-HK-0003 `hk_etf` / `stamp_duty_buy` / `stamp_duty_sell` [2010-01-01, 2015-02-13): before the all-ETF
  waiver some ETFs were taxed and others remitted (26 of 124 still taxed in 2015); no single rate covers the scope.
- G-HK-0004 `hk_etf` / `session_schedule` [2010-01-01, open): no complete, unambiguous ETF schedule history (the 2011 and
  2012 reforms limited extended morning trading to two designated ETFs, and the Rules still allow designation; no dated
  end of the distinction was found). POS and the all-ETF closing auction from 2016-07-25 are dated, but a partial schedule
  cannot fill the rule.
- G-HK-0005 / G-HK-0006 `hk_stock` / `hk_etf` / `opening_auction_limit_pct` [2010-01-01, 2020-10-19): the old
  pre-opening session (all securities, ETFs included) had "No fixed price range (except 9-times rule)" (HKEX's 2019
  consultation, Appendix 1). The nine-times quotation restriction is not a symmetric percentage band around a reference
  price, so the rule cannot encode it; 0, `unlimited` or 0.15 would each be wrong. (The nine-times check itself is
  recorded separately as `order_price_multiple_limit`.)

**Not yet encoded** (researched, no records):

- **Designated securities and per-security exemptions** (encoded: `short_sale_price_test`): the list of securities
  designated for short selling, the Commission-approved Market Making Securities, and which participants and accounts
  qualify for the market-maker, index-arbitrage, stock-futures, options and structured-product hedging exemptions are
  per-security, per-participant facts; Marina stores no list (the caller's, as for VCM tiers).
- **Statutory exceptions to the naked short-selling ban** (SFO s. 170 and its subsidiary legislation): described in
  `notes` only; not encoded.
- **Spread counting across price bands** (encoded: `order_spread_limit`): Rule 101 defines a spread by the Second
  Schedule, but no text located states how 24 spreads are counted when the range crosses a band boundary of the spread
  table; multiplying 24 by the starting tick is not established. The caller counts on `tick_size_table`.
- **Structured products' nine-times check**: from 2026-11-02 structured products keep N = 9 (Rules 503, 505A); they are
  outside this library's scope, so no record.
- **Maximum order size**: 3,000 board lots per order (raised from 600 with effect from 2007-03-26); not encoded (no rule
  name; board lots are not recorded).
- **Pre-trade controls phase 2** (securities market): no parameters or effective date published as of 2026-11-04; no
  record.
- **T+1 settlement**: HKEX's 2026-10-16 roadmap targets the second half of 2028, subject to market readiness and
  regulatory approval; not implemented, so `settlement_cycle_days` stays 2 (open-ended) and no future record is added.

**Fill checks.** `marina-check` composes A-share rules (tick family, band, stamp duty and transfer fee under scope `stock`)
and does not support Hong Kong: a row with market `XHKG` or scope `hk_stock` / `hk_etf` / `hk_etf_part_b` is reported as
`MARKET_UNSUPPORTED` and no other check runs on it.

## Rule names · US equities (XNYS, XNAS) (2026.11.02)

Data file: `data/us/equity.yaml`; scope registry `data/us/scopes.yaml`; known gaps `data/us/known_gaps.yaml`. Asset
class `equity`; markets are ISO 10383 MICs of the New York Stock Exchange (`XNYS`) and Nasdaq (`XNAS`). Its own
registry directory (`market_prefix` `us`): `market_prefix_for` maps `XNYS`, `XNAS` and `XNYS+XNAS` to `us`, so
`coverage()`, `gaps_for()` and `contract.resolve()` pick it from the market, and `scopes("us")`, `known_gaps("us")`,
`capabilities("us")` read it directly. Gap ids use their own namespace `G-US-NNNN`. **Coverage starts 2010-01-01**;
earlier dates are out of scope.

**Market = the security's primary listing exchange** (as `XSHG` / `XSHE` are for A shares). Two kinds of record:

- Federal and national-plan rules (Section 31, FINRA TAF, settlement, Rule 612, same-day resale, LULD, market-wide
  circuit breakers, the single-stock trading-pause pilot, CAT LLC fees, the Regulation SHO short-sale price test, FINRA's
  pattern-day-trader requirement) are identical on NYSE and Nasdaq and carry market `XNYS+XNAS`, so a query with `XNYS` or `XNAS`
  alone is answered by the same record. Ids `us.<rule>.<scope>.<effective_from>`.
- Exchange rules (`session_schedule`, `extended_hours`) are recorded per exchange, market `XNYS` or `XNAS`, ids
  `us.<rule>.<scope>.xnys|xnas.<effective_from>`. Such a record describes the securities **whose primary listing is
  that exchange**, as traded on that exchange: their trading sessions and opening / closing auctions. Trading of the same
  security on another exchange under unlisted trading privileges (UTP; NYSE's Tape B / C trading of non-NYSE-listed
  securities) is not modelled. A query with `XNYS+XNAS` finds no exchange-rule record (subset matching): the caller
  must name the listing exchange.

Two scopes, selected by instrument type alone (no context keys; they exclude each other):

- `us_stock` — exchange-listed NMS common stocks; ordinary secondary-market transactions.
- `us_etf` — exchange-listed ETFs that are NMS stocks; ordinary secondary-market share transactions, excluding creation
  and redemption baskets.

Not covered (no scope, no record): preferred shares, warrants, rights, closed-end funds, ETNs and other non-ETF
exchange-traded products, OTC equities, options; securities primary-listed on other exchanges (NYSE Arca `ARCX`, NYSE
American, Cboe, …), which is where most ETFs are listed.

New rules:

| rule | value | meaning |
|---|---|---|
| `sec_fee_rate_sell` | fraction | Exchange Act Section 31 transaction fee as a fraction of covered **sell** turnover. Statutorily payable by the exchanges and FINRA to the SEC; brokers commonly pass it on to the seller. Not a registration fee. |
| `finra_taf_sell` | `{per_share, max_per_trade}` + `unit: USD` | FINRA Trading Activity Fee on each sale of a covered equity security: `per_share` × shares sold, capped at `max_per_trade` per trade (USD). A member-level fee; a broker pass-through is not a separately mandated customer charge. |
| `min_quote_increment` | `{threshold, at_or_above, below}` + `unit: USD` | Regulation NMS Rule 612 minimum pricing increment for quotations and orders: `at_or_above` for prices ≥ `threshold`, `below` under it (USD). A quotation floor, not a trade-price increment; not `tick_size`. |
| `session_schedule` (US) | `{open_call: null, continuous: [[start, end]], close_call: null, open_cross, close_cross}` | Core continuous-trading hours and instantaneous opening / closing single-price crosses (auctions) at `open_cross` / `close_cross` (`HH:MM`, Eastern time); null call windows mean no separate call-auction session. Per exchange (market = primary listing exchange). |
| `extended_hours` | `{pre_market: [start, end], post_market: [start, end]}` | Pre-market and post-market continuous-trading intervals on the named exchange, Eastern time, each half-open `[start, end)`. |
| `luld_band` | `{hours: [start, end], tier_1: [bracket, …], tier_2: [bracket, …]}` + `unit: USD` | Tier-specific intraday Limit Up-Limit Down price-band parameters: per price bracket (`gt` \| `ge` lower bound, `lt` \| `le` upper bound, USD; a missing bound = from 0 / unbounded) the percentage parameter `pct`, optional absolute cap `abs_cap` (the band is the lesser of `abs_cap` and `pct` × reference price) and `doubled`, the windows in which the parameters are doubled; `hours` = the Plan's operating hours. The brackets of a tier cover every positive price exactly once (checked at load). The tier (and a leveraged ETP's ratio) is the caller's. Not a daily price limit. |
| `mwcb_decline_levels` | `{reference, levels: [l1, l2, l3]}` | Market-wide circuit-breaker decline fractions (Levels 1–3) and the index reference used to calculate their thresholds (`reference` values below). Halt durations and cut-off times are in `notes`. |
| `single_stock_pause_pct` | `{<group>: [bracket, …], …, hours: [start, end], lookback_minutes}` + `unit: USD` | Group-specific percentage moves over a rolling lookback that trigger an individual-security trading pause, subject to qualifying-trade filters. Per security group (group keys below) a list of price brackets (`gt` \| `ge` lower bound, `lt` \| `le` upper bound, USD, as for `luld_band`; a group without price brackets is one `{gt: 0.0, pct}`) with the trigger fraction `pct`; `hours` = the monitoring window (Eastern time), `lookback_minutes` = the comparison window. Each group's brackets cover every positive price exactly once (checked at load). Group membership is the caller's; Marina stores no constituents. The pause length and venue-specific trade filters are in `notes`. Not a daily price limit or a LULD band. |
| `cat_fee_per_share` | USD number + `unit: USD` | CAT LLC prospective funding charge in USD per executed equivalent share, per Industry Member buyer or seller executing-broker role: charged once to the CAT Executing Broker for the Buyer and once to the one for the Seller (both roles to the executing broker where an off-exchange report names no Industry Member contra side). An Industry Member fee, not a legally mandated customer charge (brokers may pass it through). Dates are charged transaction months, not invoice dates. |
| `cat_historical_assessment_per_share` | USD number + `unit: USD` | CAT LLC historical-cost assessment in USD per executed equivalent share, per Industry Member buyer or seller executing-broker role; same liable brokers, units and dating as `cat_fee_per_share`, and charged alongside it (a separate rule, not part of it). Not FINRA's own Historical CAT Cost Recovery Assessment. |
| `short_sale_price_test` | `none` \| `{trigger_decline_pct, reference, restriction, duration}` | Federal short-sale price-test regime applicable to covered NMS securities, including trigger, reference price, execution/display restriction and duration. `trigger_decline_pct` is the decline fraction from `reference` (in (0, 1); reaching it triggers the test); `reference`, `restriction` and `duration` take the values below. Exactly these four keys; checked at load (for markets `XNYS`, `XNAS`, `XNYS+XNAS`). Exemptions (short exempt orders) are in `notes`. The Hong Kong rule of the same name has its own shape: see the Hong Kong section. |
| `pattern_day_trader_min_equity` | `{min_equity, day_trades, window_business_days}` + `unit: USD` | Special account-level minimum equity and trade-count criteria for pattern day traders in customer margin accounts: a customer who executes `day_trades` or more day trades within `window_business_days` business days is a pattern day trader and must hold at least `min_equity` (USD) in the account to day trade. `min_equity` > 0, the two counts positive integers, exactly these keys; checked at load. An account rule that applies to margin accounts only (cash accounts are not designated; they remain subject to payment with settled funds), not a per-security holding restriction; the 6% exception, designation on reasonable knowledge and day-trading buying power are in `notes`. |

`reference` values (`mwcb_decline_levels`):

| value | meaning |
|---|---|
| `djia_quarterly_points` | DJIA point thresholds fixed quarterly from the preceding month's average close and rounded to 50 points. |
| `sp500_prev_close` | Daily percentage declines relative to the previous trading day's S&P 500 closing value. |

Values of `short_sale_price_test`:

| field | value | meaning |
|---|---|---|
| (whole value) | `none` | No short-sale price test applies to any security (the former regime, after Rule 10a-1 was removed); locate, delivery, marking and other short-sale requirements remain. |
| `reference` | `prior_close` | The covered security's closing price determined by its primary listing market at the end of regular trading hours on the prior trading day. |
| `restriction` | `above_national_best_bid` | Trading-center policies and procedures must prevent execution or display of a triggered covered short-sale order at or below the current national best bid, except as permitted by Rule 201. |
| `duration` | `rest_of_day_and_next_day` | The restriction applies for the remainder of the trigger day and the following trading day while the national best bid is calculated and disseminated on a current and continuing basis. |

`pattern_day_trader_min_equity` has no `none` value: FINRA removed the special pattern-day-trader requirement with
effect from 2026-06-04, but members may move to the new intraday margin standards one by one until 2027-10-20, so the
interval is a known gap (below), not a `none` record.

Group keys (`single_stock_pause_pct`; membership is the caller's to determine):

| key | meaning |
|---|---|
| `sp500_constituents` | Securities that are constituents of the S&P 500 Index. |
| `russell1000_constituents` | Securities that are constituents of the Russell 1000 Index. |
| `specified_etps` | Exchange-traded products specifically designated for the pilot; only ETFs in the requested scope are included. |
| `other_nms_stocks` | NMS stocks outside both named indices and the designated ETP list. |

The two indices may overlap (both 10%); `other_nms_stocks` excludes all three named groups. An ETF that tracks an index
is not thereby a constituent of it.

Existing rules with their usual meaning: `settlement_cycle_days` (as for Hong Kong: business days from trade date to
regular-way settlement; T+1 = `1`), `min_holding_days`, `price_limit_pct`. `session_schedule` keys `open_cross` /
`close_cross` are optional (see Rule `session_schedule`); US records have no `night` / `day_call`.

**Verification.** `verified` only where two independent publishers support value and date. The SEC's orders and final
rules reproduced by the Federal Register / GPO (govinfo) are one publisher; FINRA, NYSE and Nasdaq are others. An
exchange's own rule filing (even as printed in the Federal Register) and its own notice count as one publisher; CAT
LLC is another publisher, but its fee alerts are cited from archived copies, which keeps a record `single-source`; the
SEC's approval of a FINRA filing and FINRA's own notice count as one publisher. 14 records are `verified` (the T+2 and
T+1 switches, the Section 31 rates from 2010-01-15 and from 2026-04-04, the market-wide circuit-breaker levels from
2013-04-08, the trading-pause thresholds from 2011-08-08 and the Rule 201 short-sale price test from 2011-02-28), 93
`single-source`.

Timelines (`us_stock` and `us_etf` share every record's value and sources unless stated):

- **Section 31 fee** (USD per million of covered sales; the value is that ÷ 1,000,000): 25.70 (record from the
  coverage floor; the 2009 start was conditional on appropriations and is not established) → **12.70 from 2010-01-15**
  (`verified`: FINRA's information notice states rate and date, and the SEC's 2010 mid-year order applies 12.70 to sales
  from 1/15/10 to 3/31/10) → 16.90 from 2010-04-01 → 19.20 from 2011-01-21 → 18.00 from 2012-02-21 → 22.40 from
  2012-04-01 → 17.40 from 2013-05-25 → 22.10 from 2014-03-18 → 18.40 from 2015-02-14 → 21.80 from 2016-02-16 → 23.10 from
  2017-07-04 → 13.00 from 2018-05-22 → 20.70 from 2019-04-16 → 22.10 from 2020-02-18 → 5.10 from 2021-02-25 → 22.90 from
  2022-05-14 → 8.00 from 2023-02-27 → 27.80 from 2024-05-22 → **0.00 from 2025-05-14** → **20.60 from 2026-04-04**
  (`verified`: SEC order and FINRA information notice). Each date is the one stated by the SEC order, including
  non-trading days. The conditional fiscal-2012 rate of 15.10 never took effect and has no record; the May 2026
  correction to the 2026 order changes only a sign in its computation appendix, not the rate.
- **FINRA TAF** (`per_share` / `max_per_trade`, USD): 0.000075 / 3.75 (record from the coverage floor; the original
  start was not located) → 0.000090 / 4.50 from 2011-07-01 → 0.000095 / 4.75 from 2012-03-01 → 0.000119 / 5.95 from
  2012-07-01 → 0.000130 / 6.49 from 2022-01-01 → 0.000145 / 7.27 from 2023-01-01 → 0.000166 / 8.30 from 2024-01-01 →
  0.000195 / 9.79 from 2026-01-01 → **0 / 0 from 2026-10-01 to 2027-01-01**: the temporary fee holiday for transactions
  from 2026-10-01 through 2026-12-31 ([SR-FINRA-2026-021](https://www.govinfo.gov/content/pkg/FR-2026-09-23/html/2026-19392.htm)).
  The resumption of the normal rates for January 2027 stated in the filing is not encoded: there is no record and no
  gap from 2027-01-01 (after the coverage window), so a query for 2027 raises `KeyError`. Values come from FINRA's
  official Schedule A revisions; exemptions in Schedule A Section 1(b)(2) and the execution-price-below-fee exemption
  are not modelled.
- **Settlement cycle**: T+3 (record from 1995-06-07, as recalled by the SEC's 2017 final rule) → **T+2 from
  2017-09-05** → **T+1 from 2024-05-28**, both changes `verified` (SEC final rules and FINRA notices 17-19 / 24-04).
  These are the compliance dates, not the rules' legal effective dates (2017-05-30, 2023-05-05). Rule 15c6-1 exceptions
  and expressly agreed alternative settlement are excluded.
- **Same-day resale** (`min_holding_days` 0) from the coverage floor, `single-source`: an inference from FINRA's
  recognition of same-day purchases and sales. Pattern-day-trader margin requirements (`pattern_day_trader_min_equity`,
  below) and cash-account settled-funds constraints are account rules, not a security-level holding period.
- **Rule 612** `{threshold: 1.0, at_or_above: 0.01, below: 0.0001}` from its compliance date **2006-01-31**. The 2024
  amendments (a half-cent increment for stocks with a time-weighted average quoted spread of at most USD 0.015) were
  legally effective 2024-12-09, but SEC exemptive orders deferred compliance to the first business day of November 2027
  ([2026 order](https://www.govinfo.gov/content/pkg/FR-2026-06-15/html/2026-11997.htm)), outside the window: not
  encoded. Exemptive retail programs and the 2016–2018 stock-by-stock Tick Size Pilot are outside this baseline.
- **Limit Up-Limit Down** (`luld_band`, `single-source`; the Plan text is in the SEC's
  [2012 approval](https://www.govinfo.gov/content/pkg/FR-2012-06-06/html/2012-13653.htm)). Brackets by reference
  price, both tiers: above USD 3 — Tier 1 5%, Tier 2 10%; USD 0.75 to 3.00 inclusive — 20%; below USD 0.75 — the lesser
  of USD 0.15 and 75%. Tier 1 = S&P 500 and Russell 1000 stocks and designated ETPs, Tier 2 = other NMS stocks; a Tier 2
  leveraged ETP's parameters are multiplied by its leverage ratio (both the caller's to apply). Phase-in from
  **2013-04-08** by batches of securities: known gaps G-US-0005 / G-US-0006 → all NMS securities from **2013-12-08**
  (the calendar date stated by the SEC, a Sunday), hours 09:30–15:45, doubled 09:30–09:45 and 15:35–15:45 → hours to
  **16:00 from 2014-02-24**, doubled 09:30–09:45 and 15:35–16:00 → **2020-02-24** (Amendment 18 in operation; the 2019
  approval that made the Plan permanent does not date the cutover): no opening doubling, and no closing doubling for
  Tier 2 above USD 3; the other brackets stay doubled 15:35–16:00. Before 2013-04-08 there is no record and no gap (the
  Plan did not exist). The 15-second limit state, the five-minute pause, reference-price computation and reopening
  are in `notes`; overnight bands planned from 2026-12-06 are outside the window.
- **Market-wide circuit breakers** (`mwcb_decline_levels`): `{reference: djia_quarterly_points, levels: [0.1, 0.2,
  0.3]}` from the coverage floor (the old regime's start was not located; `single-source`; Level 1 halts one hour before
  14:00, 30 minutes 14:00–14:30, none after; Level 2 two hours before 13:00, one hour 13:00–14:00, the rest of the day
  after; Level 3 the rest of the day) → **`{reference: sp500_prev_close, levels: [0.07, 0.13, 0.2]}` from 2013-04-08**
  (`verified`: Nasdaq and NYSE notices and guidance): Levels 1 and 2 halt for 15 minutes only before 15:25, each once a
  day; Level 3 ends the day at any time.
- **Trading sessions** (`session_schedule`, `single-source`, from the coverage floor, open-ended; Eastern time,
  ordinary full trading day): `{open_call: null, continuous: [["09:30","16:00"]], close_call: null, open_cross: "09:30",
  close_cross: "16:00"}` for `us_stock` on `XNYS` (NYSE-listed, Tape A stocks: core session and the opening and closing
  auctions; auctions are exclusive to NYSE-listed securities), and for `us_stock` and `us_etf` on `XNAS` (Nasdaq-listed:
  regular session and the Opening and Closing Crosses). The core session and the auctions predate 2010; the start is
  truncated at the coverage floor, and continuity through the window is an inference from current exchange pages,
  2006–2013 rule texts and notices (no single dated text covers the window). Order-entry cut-offs are in `notes` only:
  NYSE MOC / LOC entry until 15:40, 15:45 from 2010-03-01, 15:50 from 2019-04-01; Nasdaq's current MOO 09:28 / LOO
  09:29:30 / MOC 15:55 / LOC 15:58 with earlier values whose deployment dates were not verified. Half days, holidays,
  IPO and halt auctions are not encoded. `us_etf` on `XNYS`: known gap G-US-0007.
- **Extended hours** (`extended_hours`, `XNAS`, both scopes, `single-source`): pre-market 07:00 and post-market to
  20:00 before 2013-03-18 are documented, but not the old regime's start (known gaps G-US-0003 / G-US-0004) →
  **`{pre_market: ["04:00","09:30"], post_market: ["16:00","20:00"]}` from 2013-03-18** (Nasdaq's production notice;
  the filing's 2013-03-05 operative date is not the go-live). `XNYS`: known gaps G-US-0008 / G-US-0009 (NYSE-listed
  securities have pre-opening order entry only, the 2018 early session is for Tape B / C non-primary securities, and no
  text on a post-market session for NYSE-listed securities was found).
- **Single-stock trading pause** (`single_stock_pause_pct`; the pilot that preceded LULD): a five-minute pause after a
  move of at least the threshold within five minutes, monitored 09:45–15:35 (no pause outside these times; on early
  closes monitoring ends 25 minutes before the close). The pilot began 2010-06-11 with S&P 500 stocks (NYSE: five on
  June 11, a total of 54 on June 14; Nasdaq all its S&P 500 issues on June 14) and added Russell 1000 stocks and
  designated ETPs from 2010-09-14; activated security by security, so `us_stock` [2010-06-11, 2011-08-08) and `us_etf`
  [2010-09-14, 2011-08-08) are known gaps **G-US-0010** / **G-US-0012** → Phase III, all NMS stocks, from **2011-08-08**
  (`verified`: FINRA's filing and the NYSE Arca bulletin / NYSE notice):
  `{sp500_constituents: [{gt: 0.0, pct: 0.1}], russell1000_constituents: [{gt: 0.0, pct: 0.1}], specified_etps: [{gt:
  0.0, pct: 0.1}], other_nms_stocks: [{ge: 1.0, pct: 0.3}, {lt: 1.0, pct: 0.5}], hours: ["09:45", "15:35"],
  lookback_minutes: 5}` (the price bracket is set by the previous trading day's closing price, or the previous day's last
  consolidated sale if there is none). The record ends at **2013-04-08**: LULD replaced the pilot security by security
  until all NMS stocks were under LULD on 2013-12-08, known gaps **G-US-0011** / **G-US-0013**; from 2013-12-08 there is
  no record and no gap (the mechanism ended), and before each scope's start none either. NYSE's three-breach filter
  (from 2011-01-28) and Nasdaq's three-print / NBBO procedure are trade filters, not further groups (in `notes`); the
  2011-11-25 removal of rights and warrants does not change either scope.
- **CAT LLC fees** (`cat_fee_per_share`, `cat_historical_assessment_per_share`, USD per executed equivalent share per
  CAT Executing Broker role, `single-source`: FINRA's fee filings in the Federal Register and CAT LLC fee alerts in
  archived copies). Dated by the charged transaction month (the first invoice follows a month later). CAT Fee: 0.000035
  from **2024-09-01** (CAT Fee 2024-1) → 0.000022 from **2025-01-01** (2025-1) → 0.000009 from **2025-07-01** (2025-2) →
  **0 from 2025-12-01** (last invoices on November 2025 transactions after the 2025-07-25 court decision vacating the
  2023 funding model; December 2025 – April 2026 funded from the surplus reserve) → 0.000001 from **2026-05-01** (2026-1,
  under the revised model approved 2026-03-16), open. Historical CAT Assessment: 0.000013 from **2024-10-01**
  (Assessment 1) → **0 from 2025-12-01** → 0.000002 from **2026-05-01** (Assessment 1A, recovering what Assessment 1 left
  uncollected, not added to it), open. No record and no gap before the first billed month (earlier invoices were tests
  and not payable). The liable broker is the one named in the exchange's CAT order-trade data or FINRA's TRF / ORF / ADF
  executing / contra-side data, not automatically the clearing broker; brokers may, but need not, pass the fees to
  customers. Participant cost-recovery fees, exchange pass-throughs and FINRA's own Historical CAT Cost Recovery
  Assessment are not included.
- **Short-sale price test** (`short_sale_price_test`): `none` from the compliance date **2007-07-06** of the SEC's 2007
  final rule (former Rule 201(a): no short sale price test, including any SRO's, applies; Rule 10a-1 removed; the rule's
  legal effective date was 2007-07-03), `single-source` (the SEC rule and NYSE Arca's own system notice, which does not by
  itself establish both exchanges) → the Rule 201 circuit breaker from **2011-02-28** (`verified`: the SEC's 2010 final
  rule and compliance-date extension, FINRA Notice 10-48 and NYSE's implementation notice), open:
  `{trigger_decline_pct: 0.1, reference: prior_close, restriction: above_national_best_bid, duration:
  rest_of_day_and_next_day}` — a decline of 10% or more (equality included) from the prior close triggers it, and a
  further qualifying decline can retrigger it. The 2010 rule was legally effective 2010-05-10 with an original
  compliance date of 2010-11-10, which the SEC extended to 2011-02-28; the extension's DATES line says March 10 for
  effectiveness (the original publication date), not used. Later amendments (2018, 2021, 2024) renumber definitions and
  restate the primary listing exchange without changing the encoded terms.
- **Pattern day trader** (`pattern_day_trader_min_equity`, `single-source`: NASD / FINRA notices and SEC approvals of
  their filings count as one publisher): `{min_equity: 25000.0, day_trades: 4, window_business_days: 5}`, USD, from the
  NASD rule's implementation date **2001-09-28** (Notice to Members 01-26; the SEC approved it on 2001-02-27); the 2010-12-02
  consolidation of NASD Rule 2520 and NYSE Rule 431 into FINRA Rule 4210 did not change the values. The record ends at
  **2026-06-04**, when FINRA's intraday margin standards replaced the pattern-day-trader designation and the $25,000
  minimum (SEC approval 2026-04-14, Regulatory Notice 26-10); because members may phase the new standards in until
  2027-10-20, the broker decides which regime applies: known gaps **G-US-0014** / **G-US-0015** from 2026-06-04, no
  record. The ordinary margin minimum equity (generally USD 2,000), Regulation T and broker house requirements are not
  encoded.

`us_etf` and `us_stock` are equal for every encoded rule (the Nasdaq ETF session record also cites the Cross FAQ's ETP
passages); the trading-pause pilot started later for ETFs (2010-09-14), so their phase-in gaps differ. Not modelled for ETFs: creation and redemption (not a secondary-market sale; TAF exemptions there need their
own analysis), ETP-specific cross price thresholds and the closing-price fallback of an ETP without a closing cross (in
`notes`).

**Gaps.** `data/us/known_gaps.yaml` declares 15; queries inside them raise `KeyError` (`OUT_OF_COVERAGE` with the gap id in
`resolve()`):

- G-US-0001 / G-US-0002 `us_stock` / `us_etf` / `price_limit_pct` [2010-01-01, open): no official text was found that
  states the absence of a daily percentage price limit. LULD bands and market-wide circuit breakers are intraday
  mechanisms and do not establish an `unlimited` daily band, so no record is written.
- G-US-0003 / G-US-0004 `XNAS` `us_stock` / `us_etf` / `extended_hours` [2010-01-01, 2013-03-18): the 07:00 pre-market
  and 16:00–20:00 post-market are documented as the prior regime, but no complete applicability chain covers the
  interval: pre-2010 texts document 07:00 openings and 20:00 endings, some with a 16:15 regular-session end, routing
  availability does not establish trading sessions, and the 2013 notice does not settle the earlier chronology.
- G-US-0005 / G-US-0006 `us_stock` / `us_etf` / `luld_band` [2013-04-08, 2013-12-08): the Plan was introduced in
  per-security batches (Phase I from 2013-04-08, completed 2013-05-03; Phase II from 2013-08-05), so covered and
  uncovered securities coexist in one scope.
- G-US-0007 `XNYS` `us_etf` / `session_schedule` [2010-01-01, open): ETFs are almost all primary-listed on NYSE Arca
  (`ARCX`, not a market here); no separate text for ETFs primary-listed on NYSE was found.
- G-US-0008 / G-US-0009 `XNYS` `us_stock` / `us_etf` / `extended_hours` [2010-01-01, open): no dated applicability
  chain establishes the absence of both continuous extended sessions for NYSE-listed securities over the window. The
  2019 Pillar filing says Exchange-listed securities trade only in the Core Trading Session and the 2018 filing that
  there is no Late Trading Session, but neither dates the earlier history; Crossing Session II (aggregate-price coupled
  orders, decommissioned 2024-01-31) was not continuous trading; the 2007 Gold Shares early opening cautions against
  one historical ETF schedule. Neither windows nor null are recorded.
- G-US-0010 / G-US-0012 `us_stock` / `us_etf` / `single_stock_pause_pct` [2010-06-11, 2011-08-08) / [2010-09-14,
  2011-08-08): group membership is the caller's and not itself a gap (as for `luld_band` and Hong Kong
  `vcm_trigger_pct`); the gap is that the pilot was activated security by security (NYSE five S&P 500 stocks on
  2010-06-11, 54 on 2010-06-14, the completion date for all NYSE S&P 500 stocks not found; designated ETPs in batches on
  2010-09-14 / 2010-09-15), and no text states a day from which every group was fully in force. Re-researched in the
  fourth batch (NYSE's rollout schedule and eligibility lists are plans, not completion notices): unchanged.
- G-US-0011 / G-US-0013 `us_stock` / `us_etf` / `single_stock_pause_pct` [2013-04-08, 2013-12-08): LULD replaced the
  pilot in per-security batches (the window of G-US-0005 / G-US-0006), so the two mechanisms coexist in one scope.
- G-US-0014 / G-US-0015 `us_stock` / `us_etf` / `pattern_day_trader_min_equity` [2026-06-04, open): FINRA's amendments
  effective 2026-06-04 remove the day-trade-count definition and the $25,000 minimum in favour of an account-level
  intraday margin deficit calculation, but members may implement them one by one until 2027-10-20; until then a broker
  may still apply the old requirement. Marina holds no broker information, so no single value exists (the same kind of
  mixed applicability as a rule phased in security by security). After 2027-10-20 the special requirement is gone at
  every member, which is outside the window and not recorded.

**Not yet encoded** (researched, no records):

- **CAT** (encoded: `cat_fee_per_share`, `cat_historical_assessment_per_share`, above). Not encoded: Participant
  (exchange and FINRA) cost-recovery fees and their pass-throughs; FINRA's own Historical CAT Cost Recovery Assessment
  ([FINRA filing](https://www.govinfo.gov/content/pkg/FR-2024-09-23/html/2024-21625.htm)), which is not CAT LLC's
  Historical CAT Assessment and is not added to it; any customer rate (brokers set their own pass-through).
- **Single-stock trading pause pilot** (encoded: `single_stock_pause_pct` from 2011-08-08, above). Not encoded: the
  pilot phases 2010-06-11 → 2011-08-08 (known gaps G-US-0010 / G-US-0012: per-security activation) and the LULD
  migration 2013-04-08 → 2013-12-08 (G-US-0011 / G-US-0013).
- **Pattern day trader from 2026-06-04** (encoded: `pattern_day_trader_min_equity` 2001-09-28 → 2026-06-04): a known
  gap (G-US-0014 / G-US-0015), because members switch to the intraday margin standards broker by broker until
  2027-10-20; the new intraday margin deficit rules themselves are not encoded.
- **Rule 201 exemptions** (encoded: `short_sale_price_test`): the conditions under which a short sale may be marked short
  exempt (the broker-dealer above-NBB provision, delayed delivery, odd lots, domestic and international arbitrage,
  over-allotments and lay-off sales, riskless principal, VWAP) and venue-specific auction handling are in `notes` only;
  there is no blanket market-making exemption.
- **23-hour trading** on Nasdaq and NYSE Arca planned from 2026-12-06 (Nasdaq's
  [2026 filing](https://www.govinfo.gov/content/pkg/FR-2026-10-08/html/2026-20605.htm)): after the window, not
  encoded.

**Fill checks.** `marina-check` does not support US equities either: a row with market `XNYS` / `XNAS` or scope
`us_stock` / `us_etf` is reported as `MARKET_UNSUPPORTED` and no other check runs on it.

## Coverage targets (`coverage/cn_targets.yaml`)

The denominator for "how complete is Marina": China A-shares (XSHG, XSHE, BJSE) from 2006-07-01 (maintainer
decision 2026-10-25; CFFEX is not part of it). Not records — `records()` skips the file.

| field | meaning |
|---|---|
| `existence.<key>` | `date` a board / product / regime first existed + `source` URL, or `existence_source: TODO` |
| `targets[]` | `id` (`market:scope:rule`), `market`, `scope` (the scope the data records the rule under), `rule`, `start` = max(2006-07-01, existence date), optional `end` (exclusive), `applies_to` (registry scopes a family target answers for), `not_applicable: "<reason + url>"` (counts as covered) |
| `unresolved[]` | `target`, `from`, `to` (exclusive, `null` = open), `reason` — gaps accepted as unresolvable; still counted as not covered |
| `new_rules` | rule names targeted before their first record exists (e.g. `stamp_duty_buy`) |

`python scripts/coverage_report.py [--markdown|--json] [--brute] [--until D]` evaluates every target for every day
and exits 1 on any gap not listed in `unresolved`.

## Fee rules (coverage step 2, 2026.10.26.7)

| rule | value | basis |
|---|---|---|
| `stamp_duty_buy` | fraction | stamp duty on **buy** turnover. Bilateral regime: 1‰ from 2005-01-24 (财税〔2005〕11号), 3‰ from 2007-05-30, 1‰ from 2008-04-24; **0** from 2008-09-19 (对受让方不再征税; Stamp Duty Law art.3 from 2022-07-01: 不对受让方征收). `0` is a sourced fact, not a default. |
| `transfer_fee_par_value` | fraction | SSE A-share transfer fee per side as a fraction of **traded par value** (成交面额), CSDC portion — XSHG 2006-07-01..2015-08-01 (0.5‰, 0.375‰ from 2012-06-01, 0.3‰ from 2012-09-01). A broker-retained part existed (CSDC 2012-08-02) but no official text states its size; it is not modelled. **Never multiply it by turnover**: a fill log does not carry par value, so `marina-check` leaves it out of the statutory fee floor (`statutory_fee_floor`). From 2015-08-01 SSE charges on turnover (`transfer_fee_each_side`). |

`transfer_fee_each_side` remains a fraction of **turnover**. Before 2015-08-01 it exists only for XSHE (0.0255‰,
collected by CSDC out of the SZSE handling fee — not a separate investor line item); for XSHG on those dates query
`transfer_fee_par_value`. Exactly one of the two answers each (market, day); `coverage/cn_targets.yaml` documents the
mapping.

Fee records are under scope `stock` (A and B shares; the official texts name A股、B股 together) and carry an explicit
market where the exchanges differ. BJSE (from 2021-11-15) shares the XSHG+XSHE records wherever one official text
covers all three (records with `market: XSHG+XSHE+BJSE`); where its rate differed it has its own record under the
family scope `bse_stock` (Beijing Stock Exchange shares, no context required — like `stock`):
`cn.fee.transfer_fee_each_side.bjse.2021-11-15`, 0.025‰, 2021-11-15..2022-04-29. So on those dates a `stock` lookup
without a market answers the SSE/SZSE 0.02‰ record, `stock` + `BJSE` is `KeyError` (no record), and the BSE value is
`rule_at("transfer_fee_each_side", d, "bse_stock", "BJSE")`. `marina-check` looks up BJSE fills under `bse_stock`
first, then `stock`. From 2022-04-29 the national `stock` record (XSHG+XSHE+BJSE) answers BJSE.

`bse_stock` also holds the other BSE-only stock records (from 2021-11-15): `tick_size` 0.01, `min_holding_days` 1,
`session_schedule` and `limit_price_min_tick` false. The tick family of the BSE board scopes (`bse`, `st_bse`,
`ipo_day1_bse`, `delisting_bse`, `delisting_day1_bse`) is `bse_stock`, and family `stock` asked with market `BJSE` maps
to it too; `limit_price()` / `min_tick_band()` with market BJSE look up the scope, then `bse_stock`, then `stock`.
Rule: with market BJSE look under `bse_stock` first, then `stock` (records such as the 2022-04-29 transfer fee and the
stamp duty legitimately cover XSHG+XSHE+BJSE under `stock`). A `stock` lookup without a market therefore never meets
a BSE-only record; `stock` + `BJSE` for these rules is `KeyError`.

Funds, REITs and convertible bonds: stamp duty and the trading transfer fee do not apply (coverage targets carry
`not_applicable` with hashed sources). Commission cap / minimum apply to funds and REITs (证券投资基金, 证监发〔2002〕21号
art. 1; scopes `etf`, `reits`); for convertibles the notice delegates to the exchanges (art. 2). The exchange-set convertible commission is recorded where an
official exchange text states it (SSE fee tables and notices 2006-07-01..2021-12-31; SZSE fee table 2006-12-30..2014-08-25 — the
older pages are cited as web.archive.org captures of sse.com.cn / szse.cn, hashed on the archived copy); the remaining periods and
the BJSE commission rule are unresolved. No official text found says either is uncapped, so `unlimited` is not used for
`commission_cap` (it would need such a text, like `unlimited` price limits do).

## Coverage step 3 (2026.10.26.7)

### Context key `delisting_entry_before_2020_08_24`

| key | values | required by |
|---|---|---|
| `delisting_entry_before_2020_08_24` | `true` \| `false` | `delisting_chinext_pre0824` (asserts `true`), `delisting_chinext_post0824` (asserts `false`) |

深证上〔2020〕620号: between the ChiNext special rules (2020-08-24) and the December-2020 reform a ChiNext delisting stock's band
was 10% if it had entered the delisting period before 2020-08-24, 20% if it entered on or after (every day, the first included).
Records exist under the two split scopes for [2020-08-24, 2020-12-31) only; outside it use `delisting_chinext` / `delisting_day1`.
The context-free `delisting_chinext` deliberately has no record in that window (G-0016, status open — answerable via the split scopes). `delisting_day1` asserts
`board: main_board` there (`from`/`to` qualifier), because a ChiNext first day belongs to `delisting_chinext_post0824`.

### Coverage of the split window

`coverage/cn_targets.yaml` targets both split scopes for [2020-08-24, 2020-12-31) and keeps the `delisting_chinext` target whole;
its 2020-08-24..2020-12-31 window is listed under `unresolved` (answered by the split scopes, counted as not covered).

### Scope families for the new rules

`session_schedule` / `min_holding_days` / `tick_size` for convertibles are recorded under scope `convertible` (`convertible_day1` is
answered by the same records — `tick_size` maps it automatically, query the others under `convertible`); for REITs under `reits`;
for BJSE stocks under `stock` with `market: BJSE`. Convertible ticks before 2022-08-01 differ by exchange — pass `market`.

## as_of — "as officially published on" (2026.10.26.7)

`record_at`, `rule_at`, `coverage`, `contract.resolve`, and the composites that call them (`limit_price`, `tick_size`,
`min_tick_band`) take an optional keyword `as_of` (ISO `YYYY-MM-DD`; anything else is `ValueError`). It asks:
*answer using only rules that had been officially published on or before `as_of`.*

Exact semantics:

1. The record in force on `date` is found **exactly as without `as_of`** (same market matching, `strict`, conflicts,
   `KeyError` when nothing is in force).
2. It is **visible at `as_of`** iff `published_at` is not null and `published_at <= as_of`. Then the answer is the same
   as without `as_of`.
3. `published_at` is null → **unknown, not absent**: `record_at` / `rule_at` raise `PublicationUnknown` (a `KeyError`
   subclass; `.record` names it); `resolve` returns status `UNKNOWN_PUBLICATION` with `record_id` and a reason;
   `coverage` lists the range under `publication_unknown` and the status is not `complete`.
4. `published_at > as_of` → **not knowable at `as_of`**: `NotYetPublished` (a `KeyError` subclass; message names the
   record and its `published_at`); `resolve` returns `NOT_YET_PUBLISHED` with `result: null`; `coverage` lists the range
   under `not_yet_published`. Marina **does not fall back** to the predecessor record.
5. `as_of` before `date` is allowed (a forward-looking question). `as_of` before the record's `effective_from` is common
   — rules are announced in advance — and is fine as long as `published_at <= as_of`.
6. `as_of=None` (default): behaviour, return values and output keys are byte-for-byte unchanged. `resolve` adds an
   `as_of` key, and `coverage` adds `as_of` / `publication_unknown` / `not_yet_published`, only when `as_of` is given.
7. `limit_price(…, as_of=…)` requires every composed record (band, tick, one-tick floor) to be visible; a publication
   exception is never masked by the pre-2006 0.01 tick fallback or by the scope → `stock` floor fallback.

**Out of scope.** `as_of` does not answer "what would a trader standing at `as_of` have believed applied on `date`?"
— that would substitute the predecessor rule when the in-force one was not yet public (and must also reason about
rules repealed or superseded after `as_of`). It is a different question with a different answer; the caller decides
what to do with `NOT_YET_PUBLISHED`. Also out of scope: consultations / drafts (e.g. a public consultation before the
final notice) are not publication; `published_at` is the final notice's date. `recorded_at` plays no role in `as_of`.

**Data.** 6 of 184 records have `published_at: null` (2026.10.26.7, after the publication-date research) — the original notice was not located; under `as_of` these always yield `UNKNOWN_PUBLICATION`: the 1998 ST 5% (`st_main`, `st_b_share`), the rounding rule (`limit_price_rounding`) and the SZSE / SSE-par-value / BJSE transfer fees. Where a publication date comes from an official register or chronicle rather than the notice text itself (the 1996 band: 1996-12-13; A-share T+1: 1994-12-08), the record's notes say `published_at basis: official-register`.

## Tracking registry (`data/<prefix>/tracking.yaml`)

Not rules, and **not part of the dataset digest**: `_iter_files()` (and `marina_rules.diff`) skip files named
`tracking.yaml`, so moving a tracking date forward with no rule change leaves `dataset_digest()` and every citation
unchanged. Loaded by `tracking_registry()`; one file per market directory (`cn`, `hk`, `us`).

```yaml
schema: 1
tracking:
- market: XSGE                     # MIC as on records; 'XNYS+XNAS' covers each member
  scopes: [cffex_if, cffex_t*]     # optional: scope names or 'family_*' name-prefix patterns; absent = every scope
  tracked_through: '2026-11-02'    # last date for which the official sources were checked for rule changes
  basis: daily settlement parameters and notices, every trading day   # how (short, English)
  updated: '2026-11-14'            # when the entry was last written
```

**Meaning.** For a date on or before `tracked_through`, an open-ended record (`effective_to: null`) states what the
sources said on that date. For a later date it is a **carry-forward** of the last checked rule, not a finding. A closed
record is unaffected: its `effective_to` is itself sourced. A market or scope with no entry is **untracked** — no date is
defaulted, and every open-ended answer on it is a carry-forward.

**Validated at load** (a bad file refuses to load): exactly the keys above; both dates valid ISO dates;
`tracked_through` ≤ `updated`; every market has records under `data/<prefix>/`; every scope (or pattern) names a scope in
that directory's `scopes.yaml`; no two entries cover the same (market, scope).

**Lookup.** `tracked_through(market, scope=None)` → ISO date or `None`. A '+' market takes the earliest of its members
and is `None` if any member is untracked; `scope=None` takes the earliest entry of the market, or `None` if some scope with
records has no entry; `market=None` → `None`. In `resolve()` without a market the answering record's market is used, so
an `XSHG+XSHE+BJSE` record is untracked there (BJSE has no entry for scope `stock`) but tracked for a query with market `XSHG` or `XSHE`.

**Entries (2026-11-19).** `XSHG+XSHE` 2026-11-13 (weekly diff of the SSE, SZSE, CSDC and MOF listing pages; titles matching
rule keywords reviewed by title, not every notice read); `XSGE` 2026-11-18; `XINE` 2026-11-18 (daily files; notices from
2026-11-03 only as republished on shfe.com.cn); `XZCE`, `GFEX` 2026-11-02; `XHKG` 2026-11-18 (the SFC's own news list and
HKEX circulars outside the CT series not read); `XNYS+XNAS` 2026-11-03; `BJSE` 2026-11-18 for its own stock-trading scopes only (`bse`, `st_bse`, `delisting_bse`,
`ipo_day1_bse`, `delisting_day1_bse`, `bse_stock`: the rules in force in BSE's trading-management column read in full).
Untracked: `BJSE` under scope `stock` (stamp duty, transfer fee) and `CCFX`.

**Where it shows** (all additive; default return values and exceptions are unchanged):

| API | without opt-in | `require_tracked=True` |
|---|---|---|
| `contract.resolve()` | `tracking: {tracked_through, beyond}` on every decision (`beyond` = `trade_date` > `tracked_through`; both `null` when untracked; the market is the query's, else the answering record's). `warnings`: `CARRY_FORWARD_BEYOND_TRACKED` / `CARRY_FORWARD_UNTRACKED` on a DETERMINED answer from an open-ended record beyond tracking / on an untracked market | that answer becomes status `BEYOND_TRACKING`: `result` null, `record_id` / evidence kept |
| `record_at()` / `rule_at()` | unchanged | `BeyondTracking` (subclass of `KeyError`; `record`, `date`, `tracked_through`) in the same case |
| `coverage()` | `tracking: {tracked_through, beyond: {from, to} \| null}` and `beyond_tracking` [{rule, from, to, record_ids}]: ranges answered by an open-ended record after `tracked_through` (anywhere when untracked); `status` unchanged | non-empty `beyond_tracking` → `partial` |
| `marina-check` | `tracking`: `rows_beyond_tracked_through`, `rows_untracked` (a row without a market counts as untracked), `tracked_through` per market; not findings, no effect on the stamp or exit code | — |
| capabilities | `tracking`: `entries`, `untracked_markets` | — |

`scripts/check_release_metadata.py` fails on a `tracked_through` or `updated` after today (Asia/Tokyo), and with
`--release data` (the release workflow, on a data tag) after the date of the version's CHANGELOG heading; it prints each entry's age. An old
date is not an error.
