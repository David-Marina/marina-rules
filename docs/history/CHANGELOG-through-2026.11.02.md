# Changelog — releases through 2026.11.02

This is the changelog of Marina's previous repository, kept as history. Marina was relaunched from a new
repository on 2026-11-13 with a clean history; current releases are in [CHANGELOG.md](../../CHANGELOG.md).

- Versions **2026.10.26.1 to 2026.10.26.5** were published on PyPI on 2026-10-25 (JST). The earlier versions
  (2026.10.24 to 2026.10.26, including the letter-suffixed ones) were published only as releases of the previous
  repository, as each entry below says.
- **2026.10.26.6, 2026.10.26.7 and 2026.11.02 were prepared but never published.** Their content ships in
  **2026.11.13**, the first release from the new repository.
- The text below is unchanged except that pull-request and issue numbers and links of the previous repository were
  removed (they would point at unrelated items in the new one). Mentions of GitHub releases, tags, branches, commits
  and pull requests refer to the previous repository; those commit hashes and tags do not exist in the new one, so
  `python -m marina_rules.diff <tag> …` against them only works on a directory holding that version's `data/`.

Every Marina release, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

How to read an entry:

- **Dataset** is the first 16 hex of the dataset digest — the hash in `mr.citation()`. Two results
  that cite the same digest ran against byte-identical rules. The release notes carry the full 64 hex.
- **Corrected (re-run needed)** lists every change `python -m marina_rules.diff <previous> <this>`
  classifies as `correction` (Marina was wrong about the past, or history was re-cut), with its
  interval, plus any behaviour change the diff cannot see. **Added** = `coverage_added` /
  `regime_change`; **Changed** = renames, bookkeeping, metadata, code and docs.
- Facts come from the GitHub release notes, the merged PR descriptions, `git log` and `diff_rules`.
  Where something could not be established from those, the entry says so.
- **Versions are names, not release dates.** `2026.10.25` was published on 2026-10-24 (JST). The date
  after each heading is the tag date in Asia/Tokyo.
- **Version scheme.** Until 2026.10.26 a second same-day release took a letter suffix
  (`2026.10.24b`, `2026.10.25b`, `2026.10.25c`, and the never-released `2026.10.26b`). Under PEP 440
  those are pre-releases (`b0` = beta, `c` = `rc0`), which `pip install` skips by default. From
  **2026.10.26.1** the scheme is `YYYY.MM.DD.N` (GOVERNANCE.md); the release workflow refuses
  any tag that `packaging` reports as a pre/dev release. The letter tags remain on GitHub as history;
  the PyPI line starts at 2026.10.26.1.

## [2026.11.02] - 2026-11-02

Dataset: `sha256:a66ca0e3fe8e3659` · 2873 records (1421 `verified`, 1451 `single-source`, 1 `unverified`): China A-share 146
(114 / 31 / 1), CFFEX 128 (115 / 13), SHFE 1044 (846 / 198), INE 281 (233 / 48), CZCE 872 (27 / 845), GFEX 220 (66 / 154), Hong Kong 75 (6 / 69), US equities 107 (14 / 93). Builds on 2026.10.26.7 (not yet tagged at the time of writing;
the tag date is the heading date). `python -m marina_rules.diff 2026.10.26.7 2026.11.02` reports 3 `correction`, 2683
`coverage_added` (the new A-share suitability, CFFEX trading, treasury-bond-futures, SHFE, INE, CZCE, GFEX, Hong Kong and US records below) and 20 `metadata` changes. No value changed for any date that
2026.10.26.7 answered. Behavioural changes: the CFFEX delivery fee now also answers 2015-04-16 → 2018-12-03 (raised `KeyError`
before), and the SZSE convertible tick for 2011-02-28 → 2012-12-10 is now `unverified`, so `resolve` refuses it at the default
`min_verification`. SHFE, INE, CZCE and GFEX fees that differ by contract (gold, silver, rebar, hot-rolled coil, fuel oil, named contracts) now need the
contract: without it `resolve` answers `MISSING_CONTEXT` (`contract`) where the first fee batch answered `OUT_OF_COVERAGE`. A-share coverage 97.25% of target-days, unchanged (137 targets: the two new suitability targets are complete).

### Added
- **SSE STAR growth-tier risk disclosure requirement** (new file `data/cn/equity_suitability.yaml`, market `XSHG`, 2 records,
  both `single-source`; new rule `retail_risk_disclosure_required`, a boolean the loader checks; new scopes
  `star_growth_new` and `star_growth_legacy`, mutually exclusive, and new context key `star_growth_tier` (`new` |
  `legacy`), which the caller supplies per security and day — Marina stores no tier constituents). From 2025-07-13
  (上证函〔2025〕2218号, in force on publication): an ordinary investor must sign the growth-tier risk disclosure statement
  before the first subscription or trade in a newly registered growth-tier stock, and the broker may not accept the order
  until it is signed (`true`, also for investors who already hold STAR permission); STAR stocks listed before the notice
  and not yet profitable, moved into the tier that day, are exempt (`false`, a sourced fact). The STAR account threshold
  (CNY 500k + 2 years) and the general STAR risk disclosure are unchanged and not encoded. The rule has no record under
  `star` / `st_star` (`OUT_OF_COVERAGE`, no default) and none before 2025-07-13 (the tier did not exist; no gap). Sources:
  the notice and the SSE's same-day press Q&A — one publisher, so `single-source`; the CSRC opinion was not fetched.
  - Researched by an automated agent; the maintainer checked both official pages against the live site, and the 12 quote
    segments and both citation hashes were recomputed from the downloaded pages.
- **CFFEX stock-index futures trading rules** (new file `data/cn/index_futures_trading.yaml`, 21 records, scopes `cffex_if`
  `cffex_ih` `cffex_ic` `cffex_im` from each product's listing day):
  - **Daily price limit** — new rule `price_limit_pct_of_prev_settlement` (basis: previous **settlement** price, so
    `limit_price(prev_close, …)` must not be used with it): ±10%; ±7% from 2016-01-01 to 2016-01-08 under the circuit-breaker
    rules (5% stage restriction not encoded); ±10% again from 2016-01-08 when circuit breakers were suspended. CFFEX trading
    rules / contract trading rules and notices; all `verified`. Listing-day and last-trading-day bands are in `notes`, not encoded.
  - **Sessions** (`session_schedule`): call 09:10–09:15, continuous 09:15–11:30 / 13:00–15:15 until 2016-01-01; then call
    09:25–09:30, continuous 09:30–11:30 / 13:00–15:00 (aligned with stocks). No closing call. All `verified`.
  - **Same-day round trip** (`min_holding_days` 0): `single-source` — inferred from the close-today fee notices and a CFFEX
    FAQ; no text stating it from listing day was found; `published_at` null.
  - Candidates researched by an automated agent and re-fetched / re-hashed by the maintainer (52 citations, 18 documents).
- **CFFEX treasury bond futures** (new file `data/cn/bond_futures.yaml`, 61 records; new scopes `cffex_tf` 2013-09-06,
  `cffex_t` 2015-03-20, `cffex_ts` 2018-08-17, `cffex_tl` 2023-04-21, each from its listing notice):
  - `price_limit_pct_of_prev_settlement`: TF 2% → 1.5% (2014-11-03) → 1.2%; T 2%; TS 0.5%; TL 3.5%. `margin_ratio` (non-hedge)
    per change, including the 2020 National Day raise (TF 1.4%, TS 0.6%, 2020-09-29 → 2020-10-09). Notices + contract trading
    rules + settlement-parameter CSV of the change day; `verified`.
  - **Gap, not a guess**: from 2015-03-16 the new TF contracts (TF1512 on) used 1.2% while TF1506 / TF1509 kept 1.5% until
    expiry; one product-level value cannot say both, so TF price limit and margin have **no record for 2015-03-16 →
    2015-09-12** (TF1509's last trading day 2015-09-11 = second Friday, contract rules art. 9). Known gaps G-0029 / G-0030.
  - `session_schedule`: call 09:10–09:15, continuous 09:15–11:30 / 13:00–15:15; from 2020-07-20 call 09:25–09:30, continuous
    09:30–11:30 / 13:00–15:15. `verified`.
  - New rules `trans_fee_per_lot` (CNY 3 per lot) and `delivery_fee_per_lot` (CNY 5; halved to 2.5 by yearly notices from
    2021-08-16, through 2026-12-31). The 2025 and 2026 halvings exclude traders CFFEX classifies as high-frequency (still 5);
    the records give the ordinary participant's rate and say so in `notes`. 2024-01-01 → 2024-01-08 is inferred
    (`single-source`), as for index futures. Close-today fees (waived or equal to the trading fee) are in `notes` only.
  - `min_holding_days` 0: `single-source`, inferred from the close-today fee waivers; no text stating it was found.
  - Researched by an automated agent; all 152 citations (41 documents) re-fetched and re-hashed by the maintainer.
- **SHFE non-ferrous metal futures** (new file `data/cn/shfe_futures.yaml`, market `XSGE`, 308 records; new scopes `shfe_cu`
  `shfe_al` `shfe_zn` `shfe_pb` `shfe_ni` `shfe_sn` `shfe_ao`). Coverage starts **2024-01-01**; earlier dates have no record.
  - `margin_ratio` (speculative / 一般持仓, 147 records) and `price_limit_pct_of_prev_settlement` (147): the general-month
    value is the minimum over the product's contracts in the daily settlement-parameter file (`js*.dat`, margin) or
    trade-argument file (`ContractDailyTradeArgument*.dat`, band), leaving out for margin the two nearest expiries and
    contracts that hit a limit that day, for the band one-sided-market and listing-day contracts. A margin starts on the first settlement day its value
    appears in the file, a band on the first trading day it applies (one trading day later; the night session belongs to
    the next trading day). Every value matches its notice; all `verified`. The records in force on 2024-01-01 start at the
    real change dates (margin 2023-10-09, AO 2023-12-28; band 2023-10-10, AO 2023-12-29). Temporary one-sided-market
    raises, near-delivery raises and listing-day bands are described in `notes`, not encoded.
  - `session_schedule` (7, `single-source`): night call 20:55–21:00, night session 21:00–01:00 (`night`), day call
    08:55–09:00 (`day_call`), continuous 09:00–10:15 / 10:30–11:30 / 13:30–15:00, no closing call. Times come from the
    undated trading-hours page; the auction structure from 交易管理办法 art. 33 and 连续交易细则 art. 8. Holiday eves without
    a night session are in `notes` only.
  - `min_holding_days` 0 (7, `single-source`): inferred from close-today fee notices (NI, SN, AO) and the close-today
    discount on each product page.
  - **Gaps, not guesses**: in 2026 SHFE set levels for contracts already listed (已上市合约) apart from new listings
    (CU/AL/ZN/PB/AO 2703 on, NI/SN 2704 on), so general months carried two values at once. No product-level margin record
    for [2026-03-17, 2026-04-29), [2026-05-06, 2026-09-29) and [2026-10-08, open) (NI/SN from 2026-04-16); bands one
    trading day later. The holiday windows in between were uniform and are recorded. Known gaps G-0031..G-0072; queries
    inside them raise `KeyError` (`OUT_OF_COVERAGE` in `resolve()`).
  - Fees are not in this batch (see the SHFE fee batch below): the files' `TTRADEFEERATIO` / `TTRADEFEEUNIT` fields are
    the hedge-position fee, not the close-today fee.
  - Researched by an automated agent; the maintainer re-downloaded all 113 URLs (699 citation hashes, 1785 quote segments)
    and recomputed all 684 trading days independently.
- **SHFE precious and ferrous metal futures** (same file `data/cn/shfe_futures.yaml`, 268 records; new scopes `shfe_au`
  `shfe_ag` `shfe_rb` `shfe_wr` `shfe_hc` `shfe_ss`), so SHFE now covers 13 products. Coverage starts **2024-01-01**, same
  method as the non-ferrous metals above.
  - `margin_ratio` (129 records) and `price_limit_pct_of_prev_settlement` (127): 251 `verified` (notice + daily file);
    5 `single-source` where no notice was located and the value and date come from the daily files only (wire rod margin
    2023-07-19 and band 2023-07-20; RB margin 2024-08-16 and band 2024-10-16, AG margin 2025-12-16, which start when a
    separately adjusted contract left the sample). The records in force on 2024-01-01 start at the real change dates
    (margin 2023-10-09, band 2023-10-10; wire rod 2023-07-19 / 2023-07-20). Wire-rod contracts that keep the listing-day
    double band while untraded (交易管理办法 art. 37) are left out of the band sample until their first ordinary band.
  - `session_schedule` (6, `single-source`): night session AU/AG 21:00–02:30, RB/HC 21:00–23:00, SS 21:00–01:00, each
    with night call 20:55–21:00 and day call 08:55–09:00; **wire rod has no night session** (`night: null`,
    `day_call: null`, `open_call` 08:55–09:00). Day session as above. Start is the coverage floor 2024-01-01.
  - `min_holding_days` 0 (6, `single-source`): inferred from the close-today fee treatment (平今折扣率 on each product page)
    and the risk-control rules' matching exception for closing same-day new positions; no text stating it was found.
  - **Gaps, not guesses** (G-0073..G-0101, 29): RB 2024-07/08 (RB2410 special margin, RB2408–2410 separate bands, again
    2024-10-09 → 10-16); AG2602 raised on its own from 2025-12-12; after New Year 2026 the named AU/AG near months kept the
    holiday levels; 2026 levels for already-listed vs new contracts (AU/AG from 2026-05-18, AG still open; RB/WR/HC/SS from
    2026-03-17, uniform again RB/HC 2026-05-19, SS 2026-07-02, WR 2026-09-29). Queries inside them raise `KeyError`.
  - Fees are not in this batch (as above).
  - Researched by an automated agent; the maintainer re-downloaded all 118 URLs (617 citation hashes, 1544 quote segments)
    and recomputed all 684 trading days independently.
- **SHFE energy, chemical and newly listed futures** (same file `data/cn/shfe_futures.yaml`, 290 records; new scopes
  `shfe_fu` `shfe_bu` `shfe_ru` `shfe_sp` `shfe_br`, and `shfe_ad` / `shfe_op` from their listing days 2025-06-10 /
  2025-09-10), so SHFE now covers 20 products. Coverage starts **2024-01-01** for the first five, same method as above.
  - `margin_ratio` (140 records) and `price_limit_pct_of_prev_settlement` (136): 274 `verified` (notice + daily file);
    2 `single-source` where no notice was located and the value and date come from the daily files only (FU margin
    2026-11-02, FU band 2026-07-01: a separately adjusted contract left the sample). The records in force on 2024-01-01
    start at the real change dates (FU/BU/BR margin 2023-12-28, band 2023-12-29; RU/SP 2023-10-09 / 2023-10-10). AD and OP
    start on the listing day with the ordinary band (AD 7%, OP 6%); the listing-day double band (交易管理办法 art. 37) is
    left out, here and for later contracts that keep it while untraded, until their first ordinary band.
  - `session_schedule` (7, `single-source`): night session AD 21:00–01:00, FU/BU/RU/SP/BR/OP 21:00–23:00, each with night
    call 20:55–21:00 and day call 08:55–09:00; day session as above. AD and OP had only a day session on the listing day
    (call 08:55–09:00), described in `notes`.
  - `min_holding_days` 0 (7, `single-source`): inferred as for the precious and ferrous metals.
  - **Gaps, not guesses** (G-0102..G-0125, 24): FU 2026-03 (near and far months at different levels until 03-10 / 03-11),
    FU band 2026-06-26 → 07-01 (FU2607), FU band from 2026-09-15 and margin 2026-10-12 → 11-02; BU named contracts raised
    from 2026-10-12 / 10-13 (open); RU/SP/OP already-listed vs new contracts 2026-04-16 → 07-10 / 07-13 (uniform for the
    Labour Day window; OP band only 2026-06-04 → 07-13); AD from 2026-03-17 / 03-19 (uniform for the Labour Day and National
    Day windows; open from 2026-10-08 / 10-09). Queries inside them raise `KeyError`.
  - Fees are not in this batch.
  - Researched by an automated agent; the maintainer re-downloaded all 121 URLs (688 citation hashes, 1718 quote segments)
    and recomputed all 684 trading days independently.
- **SHFE exchange fees, first batch: non-ferrous and precious metals** (same file `data/cn/shfe_futures.yaml`, 23 records,
  6 `verified` + 17 `single-source`; scopes `shfe_cu` `shfe_al` `shfe_zn` `shfe_pb` `shfe_ni` `shfe_sn` `shfe_ao` `shfe_ad`
  `shfe_au` `shfe_ag`), from 2024-01-01 (AD from its listing day 2025-06-10). Speculative / general-position exchange fee
  only: no hedge-position fees, no declaration fees, no broker commissions.
  - Trading fee for opening and closing earlier positions: `trans_fee_rate` (CU 0.00005, PB 0.00004, AO, AD) or
    `trans_fee_per_lot` (AL, ZN, NI, SN CNY 3), from the daily settlement-parameter file, whose `TRADEFEERATIO` is per
    mille (fraction = value / 1000) and `TRADEFEEUNIT` CNY per lot. `verified` where a notice agrees (AO from its real
    change 2023-09-08, then 0.0003 from 2024-10-30, 0.00015 from 2025-03-11, 0.0001 from 2025-04-08; AD 0.0001, 0.00005
    from 2025-11-10); values already in force before 2024 without a located start are clipped at 2024-01-01 and
    `single-source`, as are records that start when a specially priced contract left the listing.
  - Close-today fee, from notices only (the daily file has no close-today field; its `TTRADEFEERATIO` / `TTRADEFEEUNIT`
    are the hedge-position fee): `close_today_fee_rate` for AO (as its trading fee) and AD (0.0001; waived from 2025-11-10,
    recorded as 0), and the **new rule `close_today_fee_per_lot`** (`unit: CNY`) for SN (CNY 3 for SN2507 on and later
    listings, from 2025-06-17 when SN2504–2506 had expired). All `single-source`.
  - **Gaps, not the mode** (G-0345..G-0363, 19): wherever listed contracts of one product carry different fees, there is no
    product-level record. Trading fee: NI 2024-05-13 → 07-02 (NI2409 CNY 6), AO 2024-01-05 → 03-18 (AO2402/2403) and
    2025-05-26 → 09-16 (AO2509); gold and silver over the whole window (month-category tiers that roll towards expiry).
    Close-today fee: CU, AL, ZN, PB, NI, AU, AG over the whole window (no dated product-wide value located), SN until
    2025-06-17 and 2025-12-17 → 2026-02-25 (SN2601 / SN2602), AO 2024-01-05 → 2025-03-11 and 2025-05-26 → 09-16. Queries
    inside them raise `KeyError`. Share of days with one value across all contracts and the tier structure per product
    are in docs/SCHEMA.md; a contract-level context key is left for later (since added: next entry).
  - **Fuel oil margin from 2026-11-03** (`cn.futures.margin_ratio.shfe_fu.2026-11-03`, 0.16, `single-source`): the
    2026-10-30 notice raised only FU2612 / FU2701, the two nearest expiries that the general-month sample leaves out;
    FU2702–FU2711 stay at 16%. It continues the record that ended at 2026-11-03.
  - Researched by an automated agent; the maintainer re-downloaded all 24 cited URLs (hashes unchanged), rechecked 93
    quote segments (0 mismatches) and recomputed the opening fee from the raw daily files for all 6,496 product trading
    days (0 differences from the records and gaps). Sources are taken unchanged; at merge the candidate gaps G-N01..G-N19
    were numbered G-0345..G-0363.
- **SHFE fees that differ by contract: contract selectors** (same file `data/cn/shfe_futures.yaml`, now `schema: 1.2`, 42
  records, 3 `verified` + 39 `single-source`, each with a `contracts` selector — see Changed — schema). Pass the contract
  (`contract="au2606"`, or `context={"contract": "au2606"}` in `resolve`).
  - **Gold trading fee** (`trans_fee_per_lot`, 2024-01-01 → open, 11 records): the higher tier is the contracts within the
    current and next two calendar months plus the June and December contracts; until 2024-05-31 only the even months among
    the near three. CNY 10 / 2 until 2025-05-16, then 20 / 10; 2025-04-25 → 05-16 AU2506 alone at CNY 20 (2025-04-23
    notice, `verified`); 2025-05-16 → 06-03 the near four months were in the higher tier. **Silver trading fee**
    (`trans_fee_rate`, 2 records): the same near-three-plus-June/December tier at 0.00005, the rest 0.00001, over the
    whole window. These tier rules are read from the daily settlement-parameter files (`single-source`); no tier-setting
    notice was located.
  - **Named contracts**: NI2409 CNY 6 vs 3 for the other nickel contracts (2024-05-13 → 07-02); AO2402 / AO2403 0.0004 vs
    0.0001 (2024-01-05 → 03-18), both from the daily files only; AO2509 0.0003 vs 0.0001 (2025-05-26 → 09-16, notice + daily
    file, `verified`).
  - **Close-today fees for named contracts** (notices only, `single-source`): AU2506 CNY 20; AG2406, AG2412, AG2602, AG2604;
    NI2405–NI2409 CNY 9; SN2405–2407, SN2408–2410, SN2504–2506, SN2601, SN2602, with the other tin contracts at CNY 3 where
    the 2025-03-31 fee table prices every other contract and later listings; AO2411–AO2510 in three steps and AO2509 vs the
    rest in 2025. The other contracts in those windows stay gaps that carry a `none` selector.
  - **Gaps**: 15 removed (G-0345..G-0351 and G-0356..G-0363, now records or split), 26 added (G-0364..G-0389; 14 with a
    selector). Every trading-fee contract-day of the ten products from 2024-01-02 to 2026-11-02 now has a record: 74,980
    contract-days recomputed from the raw daily files through `rule_at(..., contract=)`, 0 differences, 0 in gaps (15,600
    were in gaps before). Close-today: every contract-day has either one record or a gap covering that contract.
  - Researched by an automated agent (38 records; the 4 NI / AO 2024 records were added at merge from the daily files,
    which the agent had left as gaps because no notice names those contracts). The maintainer re-downloaded the 20 cited
    URLs (hashes unchanged; 80 quote segments, the `.doc` fee-table quotes checked on its `textutil` text) and ran the
    contract-day recheck above. Seven ids listing three or more consecutive codes were shortened to `<first>_to_<last>`.
- **SHFE exchange fees, second batch: ferrous metals, energy and chemicals** (same file, 112 records, 18 `verified` + 94
  `single-source`, 88 with a contract selector; scopes `shfe_rb` `shfe_wr` `shfe_hc` `shfe_ss` `shfe_fu` `shfe_bu`
  `shfe_ru` `shfe_sp` `shfe_br` `shfe_op`), from 2024-01-01 (OP from 2025-09-10). SHFE fees now cover all 20 products.
  - Trading fee: WR, SS (CNY 2), BU, RU (CNY 3), SP, BR, OP uniform across contracts; HC and RB from 2024-05-31 near three
    calendar months plus January / May / October at 0.0001 and the other months at 0.00002 (2024-05-29 notice); RB2410 /
    RB2501 at 0.0003 apart in early 2024 (daily files only for RB2501); FU in month tiers (near months plus January / May /
    September at 0.00005, the rest 0.00001), one rate for all contracts from 2026-03-11, then named contracts FU2604–FU2703
    and FU2607 apart until 2026-07-01.
  - Close-today (notices only, `single-source`): BR and OP over their whole window; BU waived from 2024-04-26; SP 0 from
    2026-07-10; FU, RB, WR, HC, RU for the contracts or month classes the notices price. 35 gaps G-0390..G-0424 (25 with
    a `none` selector), SS close-today for the whole window.
  - Researched by an automated agent (177 requests, serial). The maintainer re-downloaded the 48 cited URLs (hashes
    unchanged; 304 quote segments, the 17 in `.doc` / `.docx` attachments checked on their `textutil` text), recomputed
    the trading fee for every listed contract on every trading day of all 20 SHFE products through `rule_at(...,
    contract=)` (153,378 contract-days, 0 differences, none in a gap), checked that every close-today contract-day has
    exactly one record or a covering gap, and checked the initial records' `published_at` against the 2023 files (FU lower
    tier set to null, see docs/SCHEMA.md). Three ids listing consecutive codes were shortened to `<first>_to_<last>`.
- **INE energy, rubber, copper and freight futures** (new file `data/cn/ine_futures.yaml`, market `XINE`, 241 records; new
  scopes `ine_sc` `ine_lu` `ine_nr` `ine_bc` `ine_ec`). Coverage starts **2024-01-01**; EC sessions and same-day round trips
  from its listing day 2023-08-18.
  - `margin_ratio` (117 records) and `price_limit_pct_of_prev_settlement` (114): 225 `verified` (notice + daily file);
    6 `single-source` where no notice was located and the value and date come from the daily files only (EC margin
    2024-01-04 and 2024-06-24, EC band 2024-01-05 and 2024-06-25; SC and LU band 2026-07-01, when a specially set July
    contract left the sample). **The margin sample follows INE's own delivery ladder** (风险控制管理细则 arts. 5, 64, 68,
    72, 78, 85), judged for the next trading day, not "the two nearest expiries": SC / LU / NR / BC leave out contracts
    from the month before delivery, EC from the settlement eight trading days before its last trading day; EC's band
    sample also leaves out the last-trading-day ±20% band (art. 86). The records in force on 2024-01-01 start at the real
    change dates (SC / LU margin 2023-12-28, band 2023-12-29; NR / BC 2023-10-09 / 2023-10-10).
  - `session_schedule` (5, `single-source`): night session SC 21:00–02:30, BC 21:00–01:00, LU / NR 21:00–23:00, each with
    night call 20:55–21:00 and day call 08:55–09:00 (交易细则 art. 19); **EC has no night session** (`night: null`,
    `day_call: null`, `open_call` 08:55–09:00). Day session 09:00–10:15 / 10:30–11:30 / 13:30–15:00, no closing call.
  - `min_holding_days` 0 (5, `single-source`): inferred from 风险控制管理细则 art. 15 (平当日新开仓位) and, for EC, the
    listing notice's close-today fee treatment; no text stating it was found.
  - **Gaps, not guesses** (G-0126..G-0157, 32): SC / LU named-contract levels in March 2026, the old July contracts' band
    2026-06-26 / 06-29 → 07-01, and from 2026-09-14 (margin uniform again 2026-09-30 → 10-12, then open; band open from
    2026-09-15); NR already-listed vs new contracts 2026-04-16 → 07-10 (band 04-22 → 07-13; uniform for the Labour Day
    window); BC from 2026-03-17 (band 04-28; uniform for the Labour Day and National Day windows; open from 2026-10-08 /
    10-09); EC 2023-12-27 → 2024-01-04, 2024-02-27 → 06-24 (uniform for the Labour Day window), 2026-03-04 → 03-09 and from
    2026-05-26 (open), bands one trading day later. Queries inside them raise `KeyError`.
  - Fees are not recorded (as above).
  - Researched by an automated agent; the maintainer re-downloaded all 119 URLs (704 citation hashes, 1622 quote segments) and recomputed all 684 trading days independently.
- **INE exchange fees** (same file `data/cn/ine_futures.yaml`, now `schema: 1.2`, 40 records, 8 `verified` + 32
  `single-source`, 31 with a contract selector; scopes `ine_sc` `ine_lu` `ine_nr` `ine_bc` `ine_ec`), from 2024-01-01.
  Trading fee: SC CNY 20 per lot, LU 0.00001, NR 0.00002, BC 0.00001, EC 0.0006; from 2026-03-11 the already-listed SC /
  LU contracts CNY 40 / 0.0001 and later listings at the old fee, restored for named contracts on 2026-05-19 and
  2026-06-25, uniform again from 2026-07-01. Close-today for the named SC / LU contracts of the 2026 notices and for
  EC2504 / EC2506 (0.0012); 21 gaps G-0425..G-0445 (15 with a `none` selector), NR and BC close-today for the whole
  window.
  - Researched by an automated agent (128 requests, serial; it stopped at once when the INE notice index returned a
    firewall verification page, without retrying). The maintainer re-downloaded the 10 cited SHFE-hosted URLs (hashes
    unchanged; 82 quote segments, the 48 in `.doc` / `.docx` attachments checked on their `textutil` text), did **not**
    contact ine.cn again and checked the 26 INE daily-file sources against the copies downloaded for the INE margin batch
    (hashes and quotes match), recomputed the trading fee for every listed contract on every trading day through
    `rule_at(..., contract=)` (42,700 contract-days, 0 differences, none in a gap), and checked that every close-today
    contract-day has one record or a covering gap and that the initial records hold back to their `published_at`.
- **CZCE agricultural, chemical, ferroalloy and thermal coal futures** (new file `data/cn/czce_futures.yaml`, market `XZCE`,
  690 records; 27 new scopes `czce_ap` `czce_cf` `czce_cj` `czce_cy` `czce_pk` `czce_sr` `czce_oi` `czce_rm` `czce_ta`
  `czce_ma` `czce_sa` `czce_fg` `czce_ur` `czce_pf` `czce_px` `czce_sh` `czce_sf` `czce_sm` `czce_pr` `czce_pl` `czce_wh`
  `czce_rs` `czce_pm` `czce_ri` `czce_jr` `czce_lr` `czce_zc`). Coverage starts **2024-01-01** (PET bottle chip from its
  listing day 2024-08-30, propylene from 2025-07-22; late indica rice ends 2026-01-19, when the daily file stops listing
  any LR contract).
  - `margin_ratio` (311 records) and `price_limit_pct_of_prev_settlement` (350): 27 `verified` — the 2024 National Day
    raises, where the notice attachment ("9月27日结算时起") and the daily file agree (margin from 2024-09-27, band from
    2024-09-30). **Most values are `single-source`: value and date come from the daily settlement-parameter file only,
    because CZCE notice pages block automated retrieval.** The file's price-limit column is the band for the **next**
    trading day (期货交易管理办法 2023 art. 32), so a band starts one trading day after the file date. **The general-month
    sample follows CZCE's delivery ladder** (风险控制管理办法 2018 arts. 5, 7), judged for the next trading day: contracts
    are left out from the 16th calendar day of the month before delivery (dried jujube from the 1st); the band sample also
    leaves out one-sided contracts (`U` / `D` in the file) and listing-day double bands. A record is made only where all
    remaining contracts agree. The records in force on 2024-01-01 start at the real change dates where one was observed
    (2023-09-05 → 2023-12-15, most 2023-10-09 / 2023-10-10).
  - **Thinly traded products** (strong wheat, rapeseed, common wheat, early indica rice, japonica rice, late indica rice,
    thermal coal): where every listed contract keeps the doubled listing band all window because it never trades (common
    wheat, early indica rice, japonica rice, late indica rice ±14, thermal coal ±20), **no band record is made and a known
    gap covers it**; an ordinary level from a notice before the window is not carried forward. Strong wheat keeps a 7% band
    record: the ordinary band is observed in the daily file (early 2023, and WH509 from 2025-08-15). Margin records are made
    where the general months agree (thermal coal 50%).
  - `session_schedule` (2, `single-source`): polyester staple fiber and PET bottle chip only — night 21:00–23:00 (listing
    notices), `open_call` 20:55–21:00, `day_call: null` (08:55–08:59 only cancels unfilled night orders, 交易管理办法 art. 30),
    day session 09:00–10:15 / 10:30–11:30 / 13:30–15:00. The other 25 products have no session record yet (known gaps).
  - `min_holding_days` 0 (27, `single-source`): inferred from the daily file's close-today fee column; no text stating it
    was found.
  - **Gaps, not guesses** (G-0158..G-0284, 127): 91 margin / band windows where general months carried two values at once
    (all products except peanut kernel, white sugar, ferrosilicon and the thinly traded ones; PTA, methanol and paraxylene
    bands open from 2026-10-12, PTA and methanol margin from 2026-10-26 / 10-27), paraxylene, caustic soda, PET bottle chip
    and propylene margin for the whole window (no quotable delivery-ladder source), propylene's first-day band, 5
    listing-band-only band windows (common wheat, early indica rice, japonica rice, late indica rice, thermal coal), late
    indica rice margin [2025-12-15, 2026-01-19) (no general month left), and 25 session gaps. Queries inside them raise
    `KeyError`.
  - Fees are not recorded (as above).
  - Researched by an automated agent; the maintainer re-downloaded all 74 URLs (1923 citation hashes, 2392 quote segments) and recomputed all 684 trading days independently.
- **CZCE exchange fees** (same file `data/cn/czce_futures.yaml`, now `schema: 1.2`, 182 records, all `single-source`,
  90 with a contract selector; all 27 CZCE scopes), from 2024-01-01 (PR from 2024-08-30, PL from 2025-07-22, LR until
  2026-01-19). Trading and close-today fees both come from the daily settlement-parameter file, per contract: `绝对值`
  is CNY per lot, `比例值` is 1/10000 of turnover (archived 2024-08-16 PET bottle chip notice: "成交金额的万分之一"
  against 1.00). Contract tiers for CF, CJ, CY, OI, RM, SA, FG, UR, SF, SM and SH; PL changed from rate to per lot on
  2026-06-08. No gaps.
  - Researched by an automated agent; the CZCE site answered its first request with HTTP 412 and the agent stopped
    contacting it, reading notices only from web.archive.org. The maintainer did not contact czce.com.cn either: the 233
    daily-file sources were checked against the copies downloaded for the CZCE margin batches (hashes and quotes match),
    the 3 archived notices re-downloaded from web.archive.org (hashes unchanged, 70 quote segments), both fee columns
    recomputed for every listed contract on every trading day through `rule_at(..., contract=<three-digit code>)`
    (319,390 contract-day checks, 0 differences), and the initial records checked back to their `published_at` (57, 6
    null, 0 breaks).
- **GFEX industrial silicon, lithium carbonate, polysilicon, platinum and palladium futures** (new file
  `data/cn/gfex_futures.yaml`, market `GFEX`, 121 records; 5 new scopes `gfex_si` `gfex_lc` `gfex_ps` `gfex_pt`
  `gfex_pd`). Coverage starts **2024-01-01** (polysilicon from its listing day 2024-12-26, platinum and palladium from
  2025-11-27).
  - `margin_ratio` (66 records, all `verified`): value and date from dated GFEX notices (holiday adjustments, listings,
    ad-hoc adjustments), effective from the settlement the notice names; every record also checked against the exchange's
    daily settlement parameters, where all remaining general-month contracts carry the notice standard. **The
    general-month sample follows GFEX's delivery ladder** (product rules arts. 12 / 13, 风险管理办法 art. 9), judged for the
    next trading day: contracts are left out from the 15th trading day of the month before delivery for industrial
    silicon and for lithium carbonate before LC2512, from the 10th for LC2512 on, polysilicon, platinum and palladium. The
    settlement-parameter page answers only by POST with a server timestamp, so it is used for checking and is not cited.
  - `price_limit_pct_of_prev_settlement` (50, `single-source`): the ordinary general-month band from the same notices;
    the settlement parameters do not publish the band, so value and date rest on the notice alone. A band set at a
    settlement applies from the **next** trading day; conditional restoration dates are fixed from the return of the
    general-month margins. Polysilicon's 14% listing-day band is not a record (ordinary 7% from the listing day).
  - `min_holding_days` 0 (5, `single-source`): inferred from the settlement rules (结算管理办法 art. 46, 平当日仓盈亏); no text
    stating it was found.
  - **Gaps, not guesses** (G-0285..G-0344, 60): 36 margin / band windows with no complete dated notice chain (the
    settlement parameters changed but are not a source; including industrial silicon and lithium carbonate from
    2024-01-01, platinum and palladium from listing, and industrial silicon, lithium carbonate and polysilicon
    2025-09-29 → 2025-12-30 and from 2026-02-12 / 2026-04-29 to 2026-09-29), 19 margin windows where the remaining general months did not all equal
    the notice standard (no one-sided-market flag is available, so no contract is silently dropped), and 5 session gaps
    (no dated night-session product list; no session record is made). Queries inside them raise `KeyError`.
  - Fees: see **GFEX exchange fees** below.
  - Researched by an automated agent; the maintainer re-downloaded all 28 URLs, recomputed all 358 citation hashes and
    358 quote segments, and checked every margin record day by day against the exchange's settlement parameters for 684
    trading days (0 mismatches).
- **GFEX exchange fees** (same file `data/cn/gfex_futures.yaml`, now `schema: 1.2`, 99 records, all `single-source`, 80
  with a contract selector; all 5 GFEX scopes), from 2024-01-01 (PS from 2024-12-26, PT and PD from 2025-11-27):
  `trans_fee_rate` and `close_today_fee_rate`, all a share of turnover. Values and dates come from 12 archived GFEX
  notices (listing notices, the 2023 industrial silicon close-today waiver, eight adjustment notices naming contracts);
  the POST-only settlement parameters are a check. Where the fee changed and no notice was located, 67 gaps
  (G-0446..G-0512, 49 for named contracts) — mostly lithium carbonate, polysilicon from 2025-12-29 to 2026-04-03, and
  platinum and palladium outside PT2606 / PD2606 in 2026-04-27 → 06-15.
  - Researched by an automated agent from web.archive.org only (22 requests; gfex.com.cn was not contacted). The
    maintainer re-downloaded the 12 notices (hashes unchanged, 100 quote segments found) and recomputed both fees for
    every listed contract on every trading day from the settlement parameters through `rule_at(..., contract=)` (47,058
    contract-day checks: 0 differences; 12,152 of them in gaps).
- **Hong Kong ordinary shares and ETFs — the first market outside mainland China** (new directory `data/hk/`: data file
  `equity.yaml`, market `XHKG`, 39 records; its own scope registry `scopes.yaml` with `hk_stock` and `hk_etf`, and known
  gaps `known_gaps.yaml`). Coverage starts **2010-01-01**. Six new rules: `transaction_levy_each_side` (SFC levy),
  `afrc_levy_each_side`, `trading_fee_each_side`, `settlement_fee_each_side` (`{rate, min, max}`, HKD),
  `trading_tariff_per_trade` (HKD) and `settlement_cycle_days`; definitions in docs/SCHEMA.md.
  - `stamp_duty_buy` / `stamp_duty_sell`: shares 0.1% → 0.13% from 2021-08-01 → 0.1% from 2023-11-17 (both changes
    `verified`: Inland Revenue Department / GovHK / Government press release and HKEX circulars); ETFs 0 from 2015-02-13,
    the all-ETF waiver (`verified`). Duty rounded up to HKD 1 (notes).
  - SFC levy 0.004% / 0.003% (2010-10-01) / 0.0027% (2014-11-01); AFRC levy 0.00015% from 2022-01-01 (no record before
    the levy existed); trading fee 0.005% → 0.00565% and trading tariff HKD 0.50 → 0 from 2023-01-01; CCASS settlement fee
    0.002% (HKD 2–100) → 0.0042% without floor or cap from 2025-06-30. All `single-source` (HKEX and HKSCC are one
    publisher); pre-2023 trading fee / tariff and pre-2025 settlement fee start at the coverage floor (original start not
    located). Crossed-trade and market-maker rates are in notes only.
  - `price_limit_pct` **`unlimited`** for both scopes from 2010-01-01 (`single-source`): HKEX states that securities listed
    on the Exchange are not subject to trading bands; the Volatility Control Mechanism (from 2016-08-22) and the closing
    auction's ±5% reference-price band are intraday mechanisms with rules of their own (second batch, below).
    `limit_price()` returns `None`.
  - `session_schedule` for shares (ordinary full day, Hong Kong time): pre-opening input to the start of matching, morning
    and afternoon sessions, and the closing auction's input window 16:01–16:10 from 2019-10-08 (random close 16:08–16:10
    in notes); changes 2011-03-07, 2012-03-05, 2019-10-08 and 2020-10-19 (random opening match to 09:22). Half-day and
    severe-weather trading are not modelled.
  - `settlement_cycle_days` 2 (T+2) and `min_holding_days` 0 (same-day resale) for both scopes, `single-source` from the
    coverage floor (the T+2 FAQ and the Stock Connect investor book; ETFs by analogy).
  - **Gaps, not guesses** (G-HK-0001..G-HK-0004, a new id namespace): share sessions during the closing-auction phase-in
    2016-07-25 → 2019-10-08 (CAS and non-CAS stocks in one scope); ETF stamp duty both sides before 2015-02-13 (taxed and
    remitted ETFs coexisted); ETF sessions from 2010-01-01 (no complete history). Queries inside them raise `KeyError`.
  - Not covered: REITs, warrants, callable bull / bear contracts, rights, debt securities, leveraged and inverse products;
    board lot (the spread table is in the second batch, below).
  - Researched by an automated agent; the maintainer re-downloaded 21 URLs and rechecked 69 citation hashes and 76 quote
    segments, then changed one finding: the candidate gaps for the daily price limit became the two `unlimited` records
    above (their two sources re-hashed from the research downloads).
- **Hong Kong second batch: spread table, closing-auction price limit, Volatility Control Mechanism** (same file
  `data/hk/equity.yaml`, 9 records, all `single-source`: HKEX circulars, rules, mechanism papers and announcements are one
  publisher). Three new rules, definitions in docs/SCHEMA.md: `tick_size_table` (a list of price bands
  `{gt | ge, le, tick}`, HKD: a price p is in the band with gt < p ≤ le, the first band uses ge and starts at HKD 0.01;
  bands must meet end to end, checked at load), `closing_auction_limit_pct` (fraction of the CAS reference price) and
  `vcm_trigger_pct` (`{tier: fraction}`; five tier keys defined in docs/SCHEMA.md). `tick_size_table` is not
  `tick_size`: no tick family, `tick_size()` does not read it; neither new band is used by `limit_price()`.
  - `tick_size_table` (`hk_stock`, Part A): the 11-band table from the coverage floor (restated by HKEX's 2024
    consultation; the previous reform was 2006-07-24) → **2025-08-04** minimum-spread reduction phase 1 (over HKD 10–20:
    0.01, over 20–50: 0.02) → **2026-08-03** phase 2 (over HKD 0.50–10: 0.005). ETFs are excluded from both phases; their
    tables are the ETF spread tables entry below.
  - `closing_auction_limit_pct` 0.05 for both scopes from **2016-07-25** (CAS phase 1, which already included all ETFs):
    ±5% of the CAS reference price (median of five nominal prices 15:59:00–16:00:00), unchanged by the 2017 phase 2; the
    value describes CAS securities only (shares were phased in until 2019-10-08). No record and no gap before 2016-07-25.
  - `vcm_trigger_pct`: shares `{hsi_hscei_constituents: 0.1}` from **2016-08-22** → HSCI LargeCap / MidCap / SmallCap
    0.1 / 0.15 / 0.2 from **2020-05-11** → same fractions from **2021-03-29** (multiple triggers per session); ETFs
    `{vcm_eligible_etfs: 0.05}` from **2022-05-03** (outside the VCM before: no record, no gap). Index membership and the
    HKEX VCM list are the caller's; reference price, cooling-off period and unmonitored periods are in notes.
  - Known gaps G-HK-0001 (share sessions during the CAS phase-in) and G-HK-0004 (ETF sessions) re-researched: both stay
    open over the same intervals; reasons and evidence rewritten (phase-1 / phase-2 eligibility; the 2011 / 2012
    extended-morning ETFs and the designation mechanism still in the Rules).
  - Researched by an automated agent; the maintainer re-downloaded all 22 URLs, recomputed every content hash and checked
    57 quote segments (0 mismatches), then re-encoded the band bounds from `{over, up_to}` to `{gt | ge, le}`.
- **Hong Kong ETF spread tables: new context key `spread_table`, new scope `hk_etf_part_b`** (same file
  `data/hk/equity.yaml`, 3 records, all `single-source`: HKEX alone; Hong Kong now 51 records, 6 `verified` + 45
  `single-source`). Which Part of the Second Schedule an ETF trades under on a date is a per-security fact, so it is
  context the caller supplies (`spread_table`: `part_a` | `part_b` | `part_d`; Marina does not infer it). Under `hk_etf`
  only `tick_size_table` asks for it (`rule_asserts`): `part_a` before 2020-06-01, `part_d` from it; any other value, a
  missing key, or Part D before 2020-06-01 is `MISSING_CONTEXT`. Fees, sessions, VCM and every other `hk_etf` rule need no
  context, as before. ETFs on Part B use the new scope `hk_etf_part_b` (`requires: [spread_table]`, asserts `part_b`;
  excludes `hk_stock` but not `hk_etf`, so the same ETF's fees are still asked under `hk_etf`).
  - `hk_etf` **Part A** from the coverage floor to **2020-06-01** (the shares' 11-band table and sources, plus the
    undated ETP trading-arrangements leaflet assigning ordinary ETPs to Part A; continuity is an inference) → **Part D
    from 2020-06-01** (`published_at` 2020-05-18; ten bands from HKD 0.01 to 9,999: 0.001 to 1, 0.002 to 5, 0.005 to 10,
    0.01 to 20, 0.02 to 100, 0.05 to 200, 0.1 to 500, 0.2 to 1,000, 0.5 to 2,000, 1 to 9,999; ETP/004/20, the 18 May 2020
    announcement, the rule update index and the current Second Schedule agree). ETPs are excluded from the 2025-08-04 and
    2026-08-03 share reductions, so Part D is unchanged through them.
  - `hk_etf_part_b` **Part B** from the coverage floor, open-ended: one band, HKD 0.05 from 0.50 to 9,999.95 (current
    Second Schedule; the leaflet's uniform 0.050 for fixed-income and currency ETPs before 2020-06-01; ETP/004/20 keeps
    Part B as an option for fixed-income ETFs; the HKD 0.05 standardisation for debt securities dates from 2004).
  - Draft gaps G-HK-0005 / G-HK-0006 (`hk_etf` / `tick_size_table`, never in a published release) are replaced by these
    records and removed; Hong Kong now declares 4 gaps (G-HK-0001..G-HK-0004).
- **Hong Kong third batch: short-selling tick rule, Investor Compensation levy, pre-opening price limit** (same file
  `data/hk/equity.yaml`, 16 records, all `single-source`; Hong Kong now 67 records, 6 `verified` + 61 `single-source`).
  Two new rules, definitions in docs/SCHEMA.md: `investor_compensation_levy_each_side` (fraction of consideration per
  side, [0, 1)) and `opening_auction_limit_pct` (fraction of the POS reference price, (0, 1)); and a Hong Kong shape for
  `short_sale_price_test`, `{restriction, duration}` with `restriction` `not_below_best_ask` | `exempt` and `duration`
  `always` (all three validated at load). Same-value records are split on the dates the arrangements changed, so each
  record's `notes` describe its own period (as for `vcm_trigger_pct` 2020-05-11 → 2021-03-29).
  - `short_sale_price_test`: `hk_stock` `not_below_best_ask` (a short sale of a designated security not below the best
    current ask in continuous trading; Rule 563D, Eleventh Schedule (15)) from the coverage floor (a truncation; HKEX
    stated the rule in 2001) → same value from **2017-07-24** (short-sale input in the closing auction at or above the CAS
    reference price), **2020-10-19** (pre-opening input at or above the POS reference price) and **2023-06-19** (Dual
    Counter Market Maker short selling exempt). `hk_etf` `exempt` from **2002-03-25** (all ETFs, all participants; HKEX's
    2002-03-28 status report) → same value from 2017-07-24, 2020-10-19 and **2024-11-01** (ETF market makers in POS /
    CAS). Designation lists, the market-maker and hedging exemptions and the naked short-selling ban are in `notes`; the
    archived SFC guidance cited does not make a record `verified`.
  - `investor_compensation_levy_each_side` 0 for both scopes from **2005-12-19** (suspended by the SFC; unsuspended rate
    0.002% per side in `notes`; `published_at` 2005-11-11 as reported by HKEX's CT/134/19) → same value from
    **2020-01-01** (suspension / reinstatement trigger levels raised to HKD 3 billion / 2 billion; the Government's
    2019-10-11 announcement and HKEX). No reinstatement found before 2026-11-04.
  - `opening_auction_limit_pct` 0.15 for both scopes from **2020-10-19** (POS enhancement: first-stage ±15% around the
    previous close; ETFs on their listing day around the pre-listing NAV per unit; the 09:15 inner band in `notes`) → same
    value from **2026-11-02** (the nine-times quotation check tightened to five times). Before 2020-10-19 the old POS had
    "No fixed price range (except 9-times rule)", which this rule cannot encode: known gaps **G-HK-0005** (`hk_stock`) /
    **G-HK-0006** (`hk_etf`) [2010-01-01, 2020-10-19). The ids reuse the never-released drafts' numbers above.
  - Settlement cycle rechecked: HKEX's 2026-10-16 T+1 roadmap targets the second half of 2028 (not implemented); T+2
    stays open-ended.
  - Researched by an automated agent; the maintainer independently re-downloaded the 21 cited URLs and rechecked their
    hashes and 99 quote segments (0 mismatches). Sources are taken unchanged; at merge the candidate gaps G-HK-N01 /
    G-HK-N02 were numbered G-HK-0005 / G-HK-0006.
- **Hong Kong fourth batch: quotation spread limit and order-price multiple check** (same file `data/hk/equity.yaml`, 8
  records, all `single-source`; Hong Kong now 75 records, 6 `verified` + 69 `single-source`). Two new rules, definitions
  in docs/SCHEMA.md, both validated at load and accepted for market `XHKG` only:
  - `order_spread_limit` `{max_spreads, wider_pct, reference}`: the continuous-trading passive-side limit-order boundary
    of Rules 503, 506A and 507A, counted from the same-side best price (`reference` `same_side_best_or_rule_fallback`;
    the missing-queue and first-quotation fallbacks are in `notes`). **24 spreads from 2005-07-04** (eight → twenty-four;
    HKEX's 2005-06-29 announcement and the rule-amendment register; a real start before the coverage floor) with
    `wider_pct` null → `hk_etf` **24 spreads or 3.5%, whichever is wider, from 2023-03-20** (`wider_pct` 0.035; ETP/001/23)
    → `hk_stock` **24 spreads or 5% from 2025-08-04** (`wider_pct` 0.05; LSD/030/2025). The percentage boundary is rounded
    to a valid spread (up below the reference, down above it). Not applicable to auction orders (Rule 505; see
    `opening_auction_limit_pct` / `closing_auction_limit_pct`). The 2026-11-02 reform did not change it.
  - `order_price_multiple_limit` `{max_multiple, reference}`: an order is rejected at a price P ≥ N × R or P ≤ R / N
    (equality rejected) against the nominal price, or the previous close for the opening quotation (Rules 501I, 503,
    505A; `reference` `nominal_or_previous_close_for_opening`). Applies in CTS and to priced at-auction limit orders in
    POS and CAS. **9 from the coverage floor** (a truncation: the nine-times rule is stated as existing in HKEX's 2008
    consultation; its original start was not found) → **5 from 2026-11-02** (pre-trade controls enhancements phase 1;
    LSD/072/2026 of 2026-10-26, CT/159/26 and the rule-amendment register). Structured products keep nine times (outside
    both scopes). The phase 1 rule changes (Rules 501I, 503, 505A) touch no other market-wide price or quantity parameter.
  - The candidate's spread value was `{max_spreads, reference}` with the percentage alternative in `notes` only; at merge
    the maintainer added `wider_pct` so that the value alone states the boundary. Notes were reworded accordingly; sources
    are unchanged.
  - Researched by an automated agent; the maintainer independently re-downloaded the 14 cited URLs and rechecked their
    hashes and 81 quote segments (0 mismatches). No new known gap.
- **US equities: NYSE and Nasdaq common stocks and ETFs — the third market family** (new directory `data/us/`: data file
  `equity.yaml`, market `XNYS+XNAS`, 68 records; its own scope registry `scopes.yaml` with `us_stock` and `us_etf`, and
  known gaps `known_gaps.yaml`). Coverage starts **2010-01-01**. Three new rules: `sec_fee_rate_sell` (fraction),
  `finra_taf_sell` (`{per_share, max_per_trade}`, USD) and `min_quote_increment` (`{threshold, at_or_above, below}`,
  USD); `settlement_cycle_days` as for Hong Kong; definitions in docs/SCHEMA.md. Both scopes share every value.
  - `sec_fee_rate_sell` (Exchange Act Section 31): every SEC rate order in the window, USD 25.70 per million at the
    coverage floor through 27.80 (2024-05-22), **0 from 2025-05-14** and **20.60 from 2026-04-04** (`verified`: SEC
    order and FINRA information notice; 12.70 from 2010-01-15 upgraded to `verified` in the second batch, below; the
    rest `single-source`). The 2009 start (conditional on appropriations) is not
    established, so the first record starts at the coverage floor; the conditional fiscal-2012 rate never took effect and
    has no record.
  - `finra_taf_sell`: eight Schedule A versions from USD 0.000075 per share (cap 3.75) to 0.000195 (cap 9.79) from
    2026-01-01, then **0 / 0 from 2026-10-01 to 2027-01-01**, the fee holiday for transactions from 2026-10-01 through
    2026-12-31. The resumption stated in the filing is not encoded: from 2027-01-01 there is no record and no gap (after
    the coverage window), so a 2027 query raises `KeyError`. All `single-source` (FINRA texts and FINRA filings).
  - `settlement_cycle_days`: T+3 (from 1995-06-07) → **T+2 from 2017-09-05** → **T+1 from 2024-05-28**, the SEC
    compliance dates (`verified`: SEC final rules and FINRA notices).
  - `min_quote_increment`: Rule 612, USD 0.01 at or above USD 1.00 and 0.0001 below, from the 2006-01-31 compliance date
    (`single-source`); the 2024 half-cent amendments' compliance date is deferred to November 2027 and is not encoded.
  - `min_holding_days` 0 (same-day resale) from the coverage floor, `single-source` (inferred from FINRA's day-trading
    definition; pattern-day-trader rules are account-level).
  - **Gaps, not guesses** (G-US-0001, G-US-0002, a new id namespace): `price_limit_pct` for both scopes from 2010-01-01,
    open. No official text stating the absence of a daily price limit was found, and LULD and market-wide circuit
    breakers do not establish one, so no `unlimited` record is written. Queries raise `KeyError`.
  - Not encoded in this batch (researched, see docs/SCHEMA.md): LULD, market-wide circuit breakers and trading sessions
    (second batch, below), and CAT fees. Not covered: preferred shares, warrants, rights, closed-end funds, ETNs, OTC
    equities, options.
  - Researched by an automated agent; the maintainer independently rechecked 47 URLs and 146 quote segments (all
    consistent; one FINRA page fetched from an archived copy differed only in site navigation), normalised the rates to
    the exact decimals the sources state, and changed one finding: the fee-holiday record now ends on 2027-01-01 as the
    filing states, instead of staying open.
- **US equities second batch: LULD, market-wide circuit breakers, trading sessions, extended hours** (same file
  `data/us/equity.yaml`, 15 new records, 2 upgraded; US equities now 83 records, 10 `verified` + 73 `single-source`).
  **Market is the security's primary listing exchange** (as `XSHG` / `XSHE` for A shares): federal and national-plan
  rules keep market `XNYS+XNAS`; the new exchange rules are recorded per exchange (market `XNYS` or `XNAS`, ids
  `us.<rule>.<scope>.xnys|xnas.<date>`) and describe that exchange's primary-listed securities; trading of the same
  security on other exchanges (UTP, NYSE Tape B / C) is not modelled, and a query with `XNYS+XNAS` finds no such record.
  Three new rules, definitions in docs/SCHEMA.md: `extended_hours` (`{pre_market, post_market}`), `luld_band` (tier map
  of price brackets `{gt | ge, lt | le, pct, abs_cap, doubled}` + `hours`, USD; validated at load) and
  `mwcb_decline_levels` (`{reference, levels}`); `session_schedule` gains the optional keys `open_cross` / `close_cross`.
  - `luld_band` (both scopes, `single-source`): above USD 3 Tier 1 5% / Tier 2 10%, USD 0.75–3.00 20%, below USD 0.75 the
    lesser of USD 0.15 and 75%, from **2013-12-08** (all NMS securities; hours 09:30–15:45, doubled 09:30–09:45 and
    15:35–15:45) → **2014-02-24** (hours to 16:00, doubled 09:30–09:45 and 15:35–16:00) → **2020-02-24** (Amendment 18: no
    opening doubling; Tier 2 above USD 3 no longer doubled at the close). The 2013-04-08 → 2013-12-08 phase-in is known gaps
    **G-US-0005** / **G-US-0006**; before 2013-04-08 no record and no gap. Tier and leveraged-ETP ratio are the caller's.
  - `mwcb_decline_levels` (both scopes): DJIA quarterly points 10 / 20 / 30% from the coverage floor (`single-source`;
    the old regime's start was not located) → S&P 500 previous close 7 / 13 / 20% from **2013-04-08** (`verified`:
    Nasdaq and NYSE). Halt durations and cut-offs in notes.
  - `session_schedule` 09:30–16:00 with the opening cross at 09:30 and the closing cross at 16:00 (no call windows), from
    the coverage floor, open-ended, `single-source`: `us_stock` on `XNYS` (NYSE-listed stocks; auctions are exclusive to
    them), `us_stock` and `us_etf` on `XNAS` (Nasdaq-listed). Continuity through the window is an inference; MOC / LOC /
    MOO / LOO cut-offs and their history (NYSE 15:40 → 15:45 on 2010-03-01 → 15:50 on 2019-04-01; Nasdaq's current
    times, earlier deployment dates not verified) are in notes only; half days not encoded. `us_etf` on `XNYS`: known
    gap **G-US-0007** (ETFs are almost all primary-listed on NYSE Arca, not a market here).
  - `extended_hours` on `XNAS`, both scopes: pre-market 04:00–09:30 and post-market 16:00–20:00 from **2013-03-18**
    (`single-source`); before it known gaps **G-US-0003** / **G-US-0004** (the 07:00 regime's start was not located).
    `XNYS`: known gaps **G-US-0008** / **G-US-0009** (pre-opening order entry only for NYSE-listed securities; the 2018
    early session is for Tape B / C; no text on a post-market session for NYSE-listed securities).
  - Section 31 USD 12.70 per million from 2010-01-15 (`us.sec_fee_rate_sell.us_stock|us_etf.2010-01-15`) upgraded to
    `verified` in place (same ids, value and interval): FINRA's notice states rate and date, and the SEC's 2010 mid-year
    order applies 12.70 to sales from 1/15/10 to 3/31/10.
  - Not encoded: CAT fees; the single-stock circuit breaker pilot (LULD's predecessor, from 2010-06-11; docs/SCHEMA.md).
  - Researched by an automated agent; the maintainer re-downloaded 15 URLs and rechecked their hashes and 78 quote
    segments (0 mismatches). The three session records were added at merge from the downloaded official texts (new
    quotes; the candidate had left all session schedules as gaps); after merge the maintainer re-downloaded all 21 URLs
    cited by the 17 new or upgraded records and rechecked 58 sources and 101 quote segments (0 mismatches), the XNYS gap reasons were rewritten for the
    primary-listing reading, and the candidate gaps were renumbered G-US-0003..G-US-0009.
- **US equities third batch: single-stock trading pause, CAT LLC fees** (same file `data/us/equity.yaml`, 18 new
  records; US equities now 101 records, 12 `verified` + 89 `single-source`). Three new national rules (market
  `XNYS+XNAS`), definitions in docs/SCHEMA.md: `single_stock_pause_pct` (group map of price brackets `{gt | ge, lt | le,
  pct}` + `hours` + `lookback_minutes`, USD; validated at load; group keys `sp500_constituents`,
  `russell1000_constituents`, `specified_etps`, `other_nms_stocks`, membership the caller's), `cat_fee_per_share` and
  `cat_historical_assessment_per_share` (USD per executed equivalent share, per CAT Executing Broker role).
  - `single_stock_pause_pct` (both scopes, `verified`: FINRA's 2011 filing and the NYSE Arca bulletin / NYSE notice):
    Phase III from **2011-08-08** to **2013-04-08** — S&P 500, Russell 1000 and designated ETPs 10%; other NMS stocks 30%
    at a previous close of USD 1.00 or more, 50% below; five-minute lookback, monitored 09:45–15:35. Phases I and II are
    known gaps **G-US-0010** (`us_stock` from 2010-06-11) / **G-US-0012** (`us_etf` from 2010-09-14): group membership
    is the caller's and not a gap, but the pilot was activated security by security and no text dates full activation.
    The LULD migration 2013-04-08 → 2013-12-08 is **G-US-0011** / **G-US-0013**; after it, and before each scope's start,
    no record and no gap.
  - `cat_fee_per_share` (both scopes, `single-source`): 0.000035 from **2024-09-01** → 0.000022 from 2025-01-01 → 0.000009
    from 2025-07-01 → **0 from 2025-12-01** → 0.000001 from **2026-05-01**, open. `cat_historical_assessment_per_share`:
    0.000013 from **2024-10-01** → **0 from 2025-12-01** → 0.000002 from **2026-05-01** (Assessment 1A), open. Dates are
    charged transaction months; no record and no gap before the first billed month. Charged once to each of the buyer's
    and the seller's CAT Executing Broker; not a mandated customer charge. FINRA's own Historical CAT Cost Recovery
    Assessment and Participant fees are not encoded.
  - Known gaps G-US-0003 / G-US-0004 (Nasdaq extended hours before 2013-03-18) and G-US-0008 / G-US-0009 (NYSE
    extended hours) re-researched: same ids and intervals, reasons and evidence updated in place (no candidate record:
    the pre-2013 Nasdaq chronology and the NYSE-listed securities' extended sessions are still not established). The
    23-hour sessions planned on Nasdaq and NYSE Arca from 2026-12-06 are after the window.
  - Researched by an automated agent; the maintainer independently re-downloaded the 23 cited URLs and rechecked their
    hashes and 190 quote segments (0 mismatches). At merge the candidate gaps were numbered G-US-0010..G-US-0013, the
    reasons of G-US-0010 / G-US-0012 rewritten (per-security activation, not group membership, is the gap), and
    source entries repeated verbatim within a record were listed once.
- **US equities fourth batch: short-sale price test, pattern day trader** (same file `data/us/equity.yaml`, 6 new
  records; US equities now 107 records, 14 `verified` + 93 `single-source`). Two new national rules (market
  `XNYS+XNAS`), definitions in docs/SCHEMA.md: `short_sale_price_test` (`none`, or `{trigger_decline_pct, reference,
  restriction, duration}` with enumerated `prior_close` / `above_national_best_bid` / `rest_of_day_and_next_day`;
  validated at load) and `pattern_day_trader_min_equity` (`{min_equity, day_trades, window_business_days}`, USD; an
  account-level rule for margin accounts; validated at load).
  - `short_sale_price_test` (both scopes): `none` from **2007-07-06** (compliance date of the SEC's 2007 rule removing
    Rule 10a-1; `single-source`: the SEC rule and NYSE Arca's own system notice) → the Rule 201 circuit breaker from
    **2011-02-28** (`verified`: the SEC's 2010 final rule and compliance-date extension, FINRA Notice 10-48 and NYSE's
    implementation notice): a decline of 10% or more from the prior close restricts short sales at or below the national
    best bid for the rest of the day and the next day, open. Rule 201 exemptions (short exempt orders) are in `notes`.
  - `pattern_day_trader_min_equity` (both scopes, `single-source`: NASD / FINRA notices and SEC approvals of their
    filings are one publisher): USD 25,000 minimum equity, four or more day trades in five business days, from
    **2001-09-28** (NASD Notice to Members 01-26; unchanged by the 2010 consolidation into FINRA Rule 4210) to
    **2026-06-04**. FINRA's intraday margin standards replace the requirement from 2026-06-04, but members may implement
    them one by one until 2027-10-20, so which regime applies depends on the broker: known gaps **G-US-0014** /
    **G-US-0015** [2026-06-04, open), no record.
  - Known gaps G-US-0010 / G-US-0012 (trading-pause pilot phases) re-researched: same ids and intervals, reasons extended
    and evidence appended in place (NYSE's rollout schedule and eligibility lists are plans, not completion notices; no
    XNYS completion notice found).
  - Researched by an automated agent; the maintainer independently re-downloaded the 14 cited URLs and rechecked their
    hashes and 64 quote segments (0 mismatches). At merge the candidate's two `none` records for
    `pattern_day_trader_min_equity` from 2026-06-04 were not taken: Notice 26-10 lets members switch broker by broker
    until 2027-10-20, the same kind of mixed applicability as a security-by-security rollout, so the interval became the
    known gaps G-US-0014 / G-US-0015 and their four sources the gaps' evidence; the reasons of G-US-0010 / G-US-0012 keep
    the third batch's reading (group membership is the caller's, per-security activation is the gap).

### Corrected (re-run needed)
- `cn.futures.delivery_fee_rate.cffex_index_futures.2018-12-03` → **renamed `….2015-04-16`** (never released, so the id
  could change), `effective_from` 2018-12-03 → **2015-04-16**, now `verified` (re-run: CCFX / `cffex_index_futures` /
  `delivery_fee_rate` [2015-04-16, 2018-12-03) — only if something was substituted for the missing rule there).
  交割金额的万分之一 is set by the IF and IH/IC listing notices (中金所办字【2010】36号; 2015-03-30, 自2015年4月16日起上市交易)
  and shown for every IF/IH/IC contract by the settlement-parameter CSV of 2015-04-16 and every later file until the first
  halving on 2021-08-16. The old 2018-12-03 start was conservative, not a change date, and its notes wrongly said no founding
  notice had been found. IF alone (2010-04-16 → 2015-04-16) is not recorded under this all-products scope.
- **SZSE convertible tick 2011-02-28 → 2012-12-10 is disputed** (`cn.tick.convertible.szse.2011-02-28`, now `unverified`,
  `effective_to` 2022-08-01 → 2012-12-10; value 0.001 kept): the SZSE convertible-bond rules of 2008-10-28 (深证上〔2008〕152号,
  art. 14, found as web.archive.org captures of szse.cn) set **0.01** for convertibles and stayed in force until 2017-09,
  while the 2011 trading rules (3.3.13) set 0.001 for 债券 without saying they prevail over earlier rules. Per GOVERNANCE,
  two disagreeing official sources make the record `unverified` with both cited. Re-run XSHE / `convertible` / `tick_size`
  [2011-02-28, 2012-12-10) if a result depends on the third decimal.
- **New `cn.tick.convertible.szse.2012-12-10`** (0.001, `verified`): the SZSE bond-trading rules (深证会〔2012〕144号, in force
  2012-12-10) name 可转换公司债券 (art. 4), set the tick at 0.001 (art. 9) and prevail over earlier inconsistent rules
  (art. 66) — which settles the conflict from that day; restated by the 2016 / 2020 revisions and the SZSE convertible rules
  2017-09 / 2018-12 (art. 13). Same value as before for these dates.

### Changed — re-verified (`single-source` → `verified`, 12 records; one of them also re-dated, above)
- **SZSE REITs bands** `cn.limit.reits.szse.2021-01-29` (10%) and `cn.limit.reits_day1.szse.2021-01-29` (30%): the SZSE REITs
  measures themselves (2021-01-29, art. 34; in force on publication, art. 73; notice 深证上〔2021〕144号) replace the
  investor-class article as the basis. The measures were replaced on 2025-12-31 (深证上〔2025〕1519号) by measures whose art. 35
  keeps 30% / 10%; cited, interval unchanged.
- **SZSE commodity-futures ETFs** `cn.settle.etf_commodity.szse.2019-01-11` (T+0) and `….2006-07-01` (T+1 before it): the SZSE
  notice 深证会〔2019〕23号 is on szse.cn; it was previously cited only from a reprint.
- **CFFEX close-today fee**, all six records 2015-08-26 → 2023-03-20: each CFFEX notice states value and date; now also the
  settlement-parameter CSV of the same day (`/sj/jscs/…/YYYYMMDD_1.csv`), whose 平今仓收取率 column × trading fee equals the
  notice's close-today fee and changes on exactly those dates (the XML version has no such column). Same publisher — two
  official forms, not two independent publishers.
- **CFFEX delivery fee** 2015-04-16 → 2021-08-16: see Corrected above.
- **SSE B-share tick** `cn.tick.b_share.sse.2011-02-28` (USD 0.001): stated by every SSE trading-rules text in force since
  (2006 rules in force on 2011-02-28; 2012, 2015, 2018, 2020: 3.4.11; 2023, 2026: 3.3.11), all cited. The 2011-02-28 start is
  only an alignment cut borrowed from SZSE (no SSE rule changed then); it is kept because the id was released (2026.10.26)
  and ids never change once released.

### Changed — sources and notes (still `single-source`)
- **Convertibles before 2022-08-01** (`cn.limit.convertible*`, `cn.settle.convertible`, `cn.tick.convertible.szse.*`,
  `cn.session.convertible.szse`): official texts naming convertibles added (SZSE bond-trading rules 深证会〔2012〕144号 from
  2012-12-10; 深证会〔2020〕402号 / 上证发〔2020〕57号; SSE investor hotline 2020-07). The old note "no SSE text names
  convertibles as unlimited" was wrong and is removed. **Against** the existing reading: the SZSE 2006 bond-trading rules
  (4.1) exclude convertibles from 债券, recorded in the notes. `cn.tick.convertible.szse.2006-07-01` also cites the 2008 SZSE
  convertible rules (0.01 by name). For 2011-02-28 onward see Corrected.
- `cn.fee.transfer_fee_each_side.bjse.2021-11-15`: the withdrawn CSDC Beijing fee table cited from a web.archive.org capture.
- `cn.futures.delivery_fee_rate.cffex_index_futures.2024-01-01`: CFFEX publishes settlement parameters only on change days;
  the 2024-01-02..05 files are empty because 2023-12-18 was still in force (cited).
- `cn.session.reits.szse.2021-01-29`: the reference is SZSE REITs measures art. 33.
- `cn.settle.etf_bond.sse.2013-03-15`: the number 上证基字〔2013〕86号 comes only from the press reprint, not from SSE's Q&A.

### Changed — schema
- **Schema 1.2: futures contract selectors** (docs/SCHEMA.md "Schema 1.2 — contract selectors"). A record or known gap
  may carry `contracts: {any | none: [clause]}`; a clause ANDs `code` (`in` / `not_in`, lower-case product + YYMM),
  `delivery_month` (`in` / `not_in`) and `months_to_delivery` (`min` / `max` / `in`, delivery month index minus trade
  month index). It covers only those contracts of the scope's product; without it a record covers every contract, as
  before. Files that use it declare `schema: 1.2`. Loading refuses a selector on a scope that is not one product,
  codes of another product, and two records of one key that share a day unless both carry selectors and no contract
  is covered by both (checked month by month). `record_at` / `rule_at` / `coverage` take `contract=` and `resolve`
  reads `context["contract"]`; where the records in force differ by contract and none is given: `ContractRequired`
  (a `KeyError`) / `MISSING_CONTEXT` with `missing_context: ["contract"]`. `coverage` without a contract lists those
  ranges under `contract_required`. New public helpers `parse_contract` and `contract_matches` (CZCE three-digit codes
  are read against the trade date). The decision schema's `result` may carry `contracts`; release JSON and SQLite carry
  the selector (`contracts_json`); capabilities list `contract_keyed_scopes`. Answers without a contract are unchanged
  wherever no selector record is in force.
- `session_schedule` gains two optional keys (docs/SCHEMA.md): `night` — the night session's continuous window, held on
  the previous working day's evening and counted to the next trading day (`end < start` crosses midnight; with a night
  session, `open_call` is the auction before it) — and `day_call`, the call auction before the day session. A missing key
  means `null`, so A-share and CFFEX records are unchanged. The SHFE, INE and CZCE records use both.
- `capabilities.json` regenerated from the data; its `rules` and `known_gaps` sections now also list the CFFEX trading and
  treasury-bond-futures additions above, the SHFE precious, ferrous, energy and chemical scopes and gaps, the SHFE fee
  rules (incl. `close_today_fee_per_lot`) and fee gaps, and the new INE market `XINE`, CZCE market `XZCE` and GFEX market `GFEX`.
- **Market registries.** Scope registry and known gaps are per market family directory (`data/cn/`, `data/hk/`,
  `data/us/`). `coverage()`, `gaps_for()` and `contract.resolve()` now default `market_prefix` to
  `market_prefix_for(market)` (`hk` for `XHKG`, `us` for `XNYS`, `XNAS` and `XNYS+XNAS`, `cn` for every other market and
  for `market=None`), so China answers are unchanged. New `capabilities-hk.json` and `capabilities-us.json`
  (`python -m marina_rules.contract --capabilities hk` / `us`); `scripts/export_release.py` also exports the Hong Kong
  and US scopes, gaps and capabilities.
- **Gap ids** may carry a market namespace (`G-HK-0001`, `G-US-0001`); the decision schema's `known_gap_ids` pattern is now
  `^G-([A-Z]{2}-)?\d{4}$` (docs/decision.schema.json).
- **Band tables** (`tick_size_table`): the loader refuses a record without a `unit` or whose bands do not meet end to end
  (`{gt | ge, le, tick}`, `ge` only on the first band, each `gt` equal to the previous `le`, positive `tick`).
- **LULD tier maps** (`luld_band`): the loader refuses a record without a `unit`, or whose brackets in a tier do not
  cover every positive price exactly once (`gt` / `ge`, `lt` / `le`, inclusive on exactly one side of each shared
  bound), or with `pct` ≤ 0, `abs_cap` ≤ 0, or a `doubled` window outside `hours`.
- **Trading-pause group maps** (`single_stock_pause_pct`): the loader refuses a record without a `unit`, without
  `hours` (a valid window) or a positive integer `lookback_minutes`, with no group or a group key that is not lower-case
  snake_case, or whose brackets in a group do not cover every positive price exactly once (same bracket check as
  `luld_band`, now shared), or with `pct` ≤ 0.
- **Short-sale price tests** (`short_sale_price_test`), checked per market: for `XNYS`, `XNAS` and `XNYS+XNAS` the
  loader refuses a value that is neither `none` nor a mapping with exactly `trigger_decline_pct` (a number in (0, 1)),
  `reference`, `restriction` and `duration` (each one of the values defined in docs/SCHEMA.md); for `XHKG` anything but
  exactly `{restriction, duration}` with the Hong Kong values (`not_below_best_ask` | `exempt`, `always`); and the rule in
  any other market. **Fractions**: it refuses an `investor_compensation_levy_each_side` outside [0, 1) and an
  `opening_auction_limit_pct` or `closing_auction_limit_pct` outside (0, 1), and a futures `trans_fee_rate` or
  `close_today_fee_rate` outside [0, 0.01). **Per-lot futures fees** (`trans_fee_per_lot`, `close_today_fee_per_lot`): it
  refuses a record without `unit: CNY` or with a value below 0. **Order-entry price controls** (`XHKG` only;
  the rules in any other market are refused): an `order_spread_limit` that is not exactly `{max_spreads, wider_pct,
  reference}` with `max_spreads` a positive integer, `wider_pct` null or a number in (0, 1) and `reference`
  `same_side_best_or_rule_fallback`; an `order_price_multiple_limit` that is not exactly `{max_multiple, reference}` with
  `max_multiple` a number > 1 and `reference` `nominal_or_previous_close_for_opening`. **Pattern-day-trader requirements** (`pattern_day_trader_min_equity`): it refuses a
  record without a `unit`, or a value that is not exactly `{min_equity, day_trades, window_business_days}` with
  `min_equity` > 0 and the two counts positive integers.
- **Dataset digest** now walks the data files in relative-path order across directories, as documented; before, the
  directory order came from the filesystem, which with two market directories made the digest machine-dependent. The
  digest of any earlier dataset (one directory) is unchanged.
- **`marina check`** reports a Hong Kong row (market `XHKG`, scope `hk_stock` / `hk_etf`) or a US row (market `XNYS` /
  `XNAS`, scope `us_stock` / `us_etf`) as `MARKET_UNSUPPORTED` and runs no other check on it: the tick, band and
  statutory-fee checks are China A-share only.

### Conformance
- FUT-0030..FUT-0035: SHFE (CU margin in the 2024 Spring Festival raise, AO band, NI margin, CU session with `night` and
  `day_call`, CU margin 2026-06-01 refused inside a known gap, SN T+0 refused under `min_verification="verified"`).
- FUT-0036..FUT-0041: SHFE precious and ferrous metals (AU margin, RB band, AG session with night 21:00–02:30, WR session
  with `night: null`, RB margin 2024-08-05 refused inside a known gap, HC T+0 refused under `min_verification="verified"`).
- FUT-0042..FUT-0049: SHFE energy, chemical and new products (FU margin, RU band, AD band on its listing day = the ordinary
  7%, OP margin on its listing day, OP margin the day before listing refused (no record), AD session with night 21:00–01:00,
  BU margin 2026-10-20 refused inside a known gap, BR T+0 refused under `min_verification="verified"`).
- FUT-0080..FUT-0088: SHFE fees (CU trading fee rate, AL per lot, AO 0.0003 after the 2024-10-30 raise, AD close-today
  0 after the waiver, SN close-today CNY 3 per lot, NI 2024-06-03 and AU 2025-05-06 without a contract answered
  `MISSING_CONTEXT` (`contract`), SN close-today refused under `min_verification="verified"`) and FU margin 0.16 on
  2026-11-03.
- FUT-0089..FUT-0099: SHFE fees by contract (NI2409 CNY 6 and NI2410 CNY 3; AU2402 CNY 10 and AU2403 CNY 2 on 2024-01-02;
  AU2509 CNY 20 and AU2510 CNY 10 on 2025-07-10, AU2510 CNY 20 from 2025-08-01; AG2606 0.00005 and AG2607 0.00001; AU2506
  close-today CNY 20, AU2508 close-today refused inside the selector gap G-0368).
- FUT-0100..FUT-0108: SHFE fees, second batch (RB2507 non-main month 0.00002, RB2505 0.0001, RB2501 0.0003 in early 2024,
  RB without a contract `MISSING_CONTEXT`, FU one rate 2026-03-12 without a contract, FU2607 0.0001 after the June 2026
  cut, BU 0.00005, SS close-today refused inside G-0405, SP close-today 0 from 2026-07-10).
- FUT-0109..FUT-0115: INE fees (SC CNY 20; SC 2026-04-15 without a contract `MISSING_CONTEXT`, SC2606 CNY 40 and SC2704 CNY
  20; EC 0.0006; SC2606 close-today CNY 240 from 2026-03-11; NR close-today refused inside G-0439).
- FUT-0116..FUT-0124: CZCE fees (AP CNY 5 and close-today CNY 20; MA 0.0001; SA501 close-today 0.0004 and SA505 0.0002 on
  2024-10-23 with three-digit codes, SA without a contract `MISSING_CONTEXT`; PL CNY 3 per lot from 2026-06-08 and its
  rate form refused after it; PR close-today 0 from 2025-03-17).
- FUT-0125..FUT-0133: GFEX fees (SI 0.0001 and close-today 0 from the 2023 waiver; SI 2025-08-01 without a contract
  `MISSING_CONTEXT` and SI2509 0.00025; LC2609 close-today 0.00032 after the 2026-07-07 notice; LC2401 2024-01-02 refused
  inside a gap; PS close-today 0.00025 from 2026-04-03; PT2606 0.0001 in 2026-05 and PT2610 refused).
- FUT-0050..FUT-0057: INE (SC margin, SC band, BC margin, NR band, EC session with `night: null`, SC session with night
  21:00–02:30, SC margin 2026-10-20 refused inside a known gap, LU T+0 refused under `min_verification="verified"`).
- FUT-0058..FUT-0065: CZCE (CF margin, OI band on 2024-09-30 = the trading day after the 2024-09-27 National Day raise, MA
  margin on 2024-09-27, SR band, SF margin, PF session with night 21:00–23:00 and `day_call: null`, AP margin 2024-03-01
  refused inside a known gap, SR T+0 refused under `min_verification="verified"`).
- FUT-0066..FUT-0069: CZCE (PR band on 2024-09-30 after the National Day raise, RS margin 2026-09-22, PM band refused
  inside a known gap (listing band only), ZC margin 0.5).
- FUT-0070..FUT-0079: GFEX (SI margin from the 2024-02-07 Spring Festival settlement, LC band from the next trading day
  2024-02-08, PS margin on its listing day 2024-12-26, SI band, PD margin, PT band on 2026-09-30 after the National Day
  raise, LC margin 2024-06-14 refused inside a known gap, PT T+0 on its listing day 2025-11-27, SI session refused inside a
  known gap, LC T+0 refused under `min_verification="verified"`).
- FEE-0044..FEE-0053, LPX-0043, LIM-0084, SES-0009, SES-0010, SET-0010, T0-0016: Hong Kong (share stamp duty on the
  last day of 0.1% and the first trading days of 0.13% and of 0.1% again, ETF stamp duty 0 from 2015-02-13 and refused
  inside a known gap before it, settlement fee on both sides of 2025-06-30, trading fee 2023-01-03, trading tariff
  2022-12-30, AFRC levy before commencement (no record, no gap), `unlimited` band and `limit_price` `None`, share session
  2020-10-19 and refused inside the closing-auction phase-in gap, ETF T+2, share T+0 refused under
  `min_verification="verified"`).
- TCK-0022..TCK-0024, LIM-0087..LIM-0093: Hong Kong second batch (share spread table on the last day of the old table
  and the first days of phases 1 and 2, closing-auction limit on
  its first day and refused the trading day before (no record, no gap), VCM on its first day, on the 2020-05-11 tiered
  expansion and for ETFs on 2022-05-03, refused the day before ETF commencement (no record, no gap), VCM refused under
  `min_verification="verified"`).
- TCK-0025..TCK-0034, FEE-0062: Hong Kong ETF spread tables (`hk_etf` Part A in 2019 and on 2020-05-29, Part D on
  2020-06-01 and on 2026-08-03; refused without `spread_table`, with `part_a` in 2021 and with `part_d` on 2020-05-29;
  `hk_etf_part_b` Part B in 2015 and on 2026-08-03, refused with `part_d`; ETF trading fee needs no `spread_table`).
  TCK-0025 / TCK-0026 had expected the draft gaps above and now expect the records.
- FEE-0054..FEE-0060, LIM-0085, LIM-0086, SET-0011..SET-0014, TCK-0021, T0-0017: US equities (Section 31 fee on the last
  day of 27.80 per million, on 2025-05-14 (0) and after 2026-04-04 under `min_verification="verified"`, refused before
  the coverage floor; TAF on the last day before the fee holiday, on its first day, and refused in January 2027 (no
  record, no gap); daily price limit refused inside the known gaps for both scopes; settlement cycle on the last day of
  T+3, the first day of T+2, the last day of T+2 and the first day of T+1; Rule 612 increment; ETF T+0 refused under
  `min_verification="verified"`).
- LIM-0094..LIM-0099, SES-0011..SES-0017, FEE-0061: US equities second batch (LULD on 2014-06-02 and on the first day of
  Amendment 18, refused inside the phase-in gap and the trading day before the Plan (no record, no gap); circuit-breaker
  levels on the last day of the DJIA regime and the first day of the S&P 500 regime under `min_verification="verified"`;
  NYSE-listed stock session, Nasdaq ETF session at the coverage floor, NYSE ETF session refused inside G-US-0007, a
  session query for `XNYS+XNAS` refused (per-exchange rule, no gap); Nasdaq extended hours refused the trading day
  before 2013-03-18 inside G-US-0003 and answered on it, NYSE ETF extended hours refused inside G-US-0009; Section 31
  12.70 on 2010-01-15 under `min_verification="verified"`).
- LIM-0100..LIM-0105, FEE-0063..FEE-0069: US equities third batch (trading-pause thresholds in 2012 and on the last
  trading day before the LULD migration under `min_verification="verified"`, refused inside G-US-0010 and G-US-0013,
  after the mechanism ended and for ETFs before their pilot start (no record, no gap); CAT Fee on 2024-09-02, at 0 in
  December 2025 and on 2026-05-01, refused on 2024-08-30 (no record, no gap) and under `min_verification="verified"`;
  Historical CAT Assessment on 2024-10-01 and in June 2026).
- LIM-0106..LIM-0110, T0-0018..T0-0022: US equities fourth batch (short-sale price test `none` in 2010 and on the last
  trading day before Rule 201, Rule 201 on 2011-02-28 under `min_verification="verified"` and in 2020, the `none` record
  refused under `min_verification="verified"`; pattern-day-trader minimum in 2015 and on 2026-06-03, refused inside
  G-US-0014 on 2026-06-04 and G-US-0015 in November 2026, and under `min_verification="verified"`).
- LIM-0111..LIM-0119, FEE-0070..FEE-0072: Hong Kong third batch (share tick rule in 2015 and on the 2023-06-19
  same-value split, ETF exemption in 2015 and on 2009-12-31 (record from 2002-03-25), tick rule refused under
  `min_verification="verified"`; pre-opening ±15% on 2020-10-19 and for ETFs on 2026-11-03, refused inside G-HK-0005 on
  2020-10-16 and inside G-HK-0006 in 2015; Investor Compensation levy 0 in 2012 and for ETFs in 2021, refused under
  `min_verification="verified"`).
- LIM-0120..LIM-0129: Hong Kong fourth batch (share spread limit in 2015, on 2009-06-01 (record from 2005-07-04), on the
  last day without and the first day with the 5% alternative; ETF spread limit on the last day without and the first day
  with the 3.5% alternative; multiple check 9 for ETFs on 2026-10-30, 5 for shares on 2026-11-02, refused on 2009-12-31
  (no record, no gap) and under `min_verification="verified"`).
- FUT-0012, RTS-0004, T0-0007 now expect `DETERMINED` under `min_verification="verified"`; new FUT-0017 keeps a futures
  refusal case (delivery fee 2024-01-03, still `single-source`).
- FUT-0024..FUT-0029: treasury bond futures (TF 2015-06-01 refused: no record in the coexistence gap).
- FUT-0018..FUT-0023: the new CFFEX trading rules (limits incl. the 2016 ±7% week, both session regimes, T+0 refused under
  `min_verification="verified"`).
- S3-0010 (SZSE convertible tick on 2011-02-28) now expects `UNVERIFIED`; new S3-0041 (2013-06-03) expects 0.001 under
  `min_verification="verified"`.
- SUI-0001..SUI-0007: STAR growth-tier risk disclosure (new-registration `true` and legacy `false` the day after the
  notice; refused the day before it (no record, no gap); a contradicting `star_growth_tier` and a missing one
  `MISSING_CONTEXT`; no answer under `star`; refused under `min_verification="verified"`).

## [2026.10.26.7] - 2026-10-26

Dataset: `sha256:1934640d7bc9a853` · 189 records (146 `verified`, 43 `single-source`): China A-share 143 (108 / 35),
CFFEX 46 (38 / 8). Releases **everything since 2026.10.26.5**: 2026.10.26.6 was never tagged and its content (CFFEX
stock-index futures, the correctness fixes from the independent boundary audit — 34 → 55 PASS — the coverage
denominator of step 1, and the fee records of step 2; see the section below) ships here, together with coverage
step 3 (this section). Not yet tagged at the time of writing; the tag date is the heading date.

**Coverage statement.** China A-shares from 2006-07-01: **134 targets, 97.25% of target-days** (684,641 / 703,975 to
2026-10-29; 127 targets complete); 96.40% after step 3, 83.70% (132 targets) before it. Unresolved — counted as not covered, listed with
search notes in `coverage/cn_targets.yaml`: convertible commission cap (SZSE 2006-07-01 → 2006-12-30 and 2014-08-25 → open; SSE
2021-12-31 → open) and minimum (SZSE 2006-07-01 → open; SSE 2021-12-31 → open); BJSE stock commission cap / minimum (2021-11-15 →
open); context-free `delisting_chinext` 2020-08-24 → 2020-12-31 (answered by the two split scopes, G-0016). No other gap: CI
now fails on any gap that is not listed as unresolved.

### Added
- **One-tick floor, explicit `false`** (`limit_price_min_tick`): XSHE 2006-07-01..2011-02-28, XSHG 2006-07-01..2023-04-10,
  BJSE from 2021-11-15 — the rules of those periods (SZSE 2006 3.3.14; SSE 2006 3.4.13, 2012 revision, 2020 restatement;
  BSE 2021/2026 3.3.11) contain the band formula and rounding only. `limit_price()` behaves exactly as before (a false
  value is no floor; the SSE delisting-board cent band still takes precedence). Closes G-0006.
- **BJSE**: tick 0.01 (`cn.tick.bse.2021-11-15`, BSE rules 3.3.10), T+1 (`cn.settle.bse.2021-11-15`, 3.1.4 买入当日不得卖出),
  sessions 9:15–9:25 / 9:30–11:30, 13:00–14:57 / 14:57–15:00 (`cn.session.stock.bse.2021-11-15`, 2.3.2), all verified.
- **Convertibles**: same-day rotation from 2006-07-01 (as 债券 under the trading rules: SZSE 2006 3.1.5, 2011 3.1.4; SSE 2006
  3.1.5, 2020 3.1.5 — single-source) and from 2022-08-01 (both exchanges' convertible rules art. 5 — verified); sessions per
  exchange (SZSE with closing call throughout; SSE continuous to 15:00 without a closing call, also under the 2022 rules art. 12
  and not changed by the SSE 2026 trading rules); tick per exchange before 2022-08-01 from the 债券 tick: SZSE 0.01
  (2006-07-01) → 0.001 (2011-02-28; the 2011 text already has 0.001, not 2012 as G-0025 said), SSE 0.01 until 2022-08-01 —
  single-source (债券, not named convertibles). Closes G-0025.
- **SSE convertible commission** 2010-12-01..2021-12-31: cap 0.2‰, minimum CNY 1 (上证财字〔2010〕6号, bonds including
  可转换公司债券; repealed by 上证发〔2021〕95号). Verified.
- **Convertible commission, coverage step 4** (all `single-source`; official exchange fee tables read from web.archive.org
  captures of sse.com.cn / szse.cn, hashes computed on the archived copies): SSE 2006-07-01..2007-10-12 cap 0.1% (1‰), minimum
  CNY 5 (SSE fee table 时间：2005 年 8 月 — 债券（国债、企业债券、可转换公司债券等）佣金 不超过成交金额的 0.1%，起点5元); SSE 2007-10-12..2010-12-01
  cap 0.2‰, minimum CNY 1 (SSE 关于调整固定收益类产品收费标准的通知 of 2007-10-11, 自2007年10月12日起执行 — text via 上海证券报 reprint — and the
  official SSE fee table dated 2007-10-12); SZSE 2006-12-30..2014-08-25 cap 0.1% (深圳证券交易所收费（及代收税费）明细表: 佣金 可转债
  不超过成交金额的 0.1%, versions 2006-12-30 / 2007-11-12 / 2013-11-14; the 2014-08-25 version drops the 佣金 section). No SZSE
  minimum is stated, so none is recorded. No official text says convertible or BJSE commissions are uncapped (CSRC Order 204
  证券经纪业务管理办法 art. 28 sets a publication duty and a below-cost floor, no cap) — no `unlimited` value was introduced.
- **REITs**: T+1 from 2021-01-29 (SZSE investor Q&A in terms; SSE via REITs measures → fund trading, not a 3.1.5 type) and
  sessions (SSE fund sessions — no closing call until 2026-07-06, then the 2026 rules' closing call; SZSE trading-rules
  schedule). All single-source (derived through the measures' reference to fund trading).
- **Same-day fund types before 2015-01-19**, per exchange from the first official text: bond ETF XSHG 2013-03-15 (SSE guide /
  上证基字〔2013〕86号 as restated by SSE), XSHE 2013-08-05 (SZSE 2013 rules 3.1.4); gold ETF XSHG 2013-07-27 (SSE gold-ETF guide
  art. 3, verified), XSHE 2013-11-30 (SZSE decision, verified); money-market ETF XSHG **T+1** 2013-01-28..2013-12-09 (listed
  before the SSE 2013 revision made it same-day), XSHE 0 from 2013-11-30, both 0 from 2013-12-09. Coverage targets for these
  types now start at the type's first listing (SSE yearbook; SZSE notices / fund report); G-0019..G-0021 shrink to "before the
  type existed" (XSHG) and new G-0026..G-0028 (XSHE) say the same — wontfix, outside the denominator.
- **ChiNext delisting split (深证上〔2020〕620号)**: new context key `delisting_entry_before_2020_08_24`; new scopes
  `delisting_chinext_pre0824` (10%, entered before 2020-08-24) and `delisting_chinext_post0824` (20%, entered on/after, first
  day included) with declarative `asserts`, records for 2020-08-24..2020-12-31; `delisting_day1` on XSHE in that window is the
  main board only (10%, record `cn.limit.delisting_day1.szse.2020-08-24`) and asserts `board: main_board` there. Closes G-0017.
  G-0016 stays (reworded, status `open`): the context-free `delisting_chinext` has no record in that window by design.
- Coverage targets: two new targets (the split scopes, 2020-08-24..2020-12-31, complete); 134 targets in total.
- **Bitemporal `as_of`** on `record_at`, `rule_at`, `coverage`, `contract.resolve`, `limit_price`, `tick_size`,
  `min_tick_band` (keyword, ISO `YYYY-MM-DD`, bad input → `ValueError`): answer only from rules with
  `published_at <= as_of`. In-force record published later → `NotYetPublished` (KeyError subclass) / status
  `NOT_YET_PUBLISHED`, never a fallback to the predecessor; `published_at: null` → `PublicationUnknown` / status
  `UNKNOWN_PUBLICATION`; `coverage` reports `publication_unknown` / `not_yet_published` ranges and is then `partial`.
  CLI `--as-of`. `as_of=None` is unchanged (checked over every record key × 1,000+ dates). Two new statuses in the
  decision schema and capabilities; semantics and out-of-scope note in docs/SCHEMA.md "as_of". 16 records have
  `published_at: null` (none filled: no record's own sources quote the original notice's date). Boundary audit 55 → 59
  PASS (the four `as_of` probes; `KNOWN_FAILING` is empty). 16 conformance vectors `conformance/vectors/as_of.json`
  (oracles: quoted publication dates), `conformance/run.py` passes `query.as_of`; `tests/test_as_of.py`.
- 42 new conformance vectors (`ruleset_version_min: 2026.10.26.7`) and 6 updated (TCK-0005, TCK-0007, T0-0002, CNV-0013 now expect the new records; LPX-0022, LPX-0031 oracle text); 273 in total; `tests/test_step3.py`.

### Corrected (re-run needed)
`diff_rules origin/main → this`: 13 `correction` (all "new interval inside or before existing history", i.e. a former
`KeyError` now answered), 18 `coverage_added`, nothing removed or revalued:
- `limit_price_min_tick` XSHE [2006-07-01, 2011-02-28), XSHG [2006-07-01, 2023-04-10): `KeyError` → `false`. `limit_price()`
  unchanged; `rule_at` / `resolve` callers that treated the KeyError as "no floor" get the same meaning explicitly.
- `tick_size` convertible XSHE [2006-07-01, 2011-02-28) 0.01, [2011-02-28, 2022-08-01) 0.001; XSHG [2006-07-01, 2022-08-01)
  0.01: `KeyError` → value. `marina check` now flags off-tick convertible prices there.
- `min_holding_days` etf_bond / etf_gold / etf_money 2013 → 2015-01-19 (intervals above): `KeyError` → value.
- `price_limit_pct` delisting_day1 XSHE [2020-08-24, 2020-12-31): `KeyError` → 0.1 (main board only).
- **Behaviour (lookups without a market):** `commission_cap` / `convertible` with `market=None` now raises `RuleConflict` for 2010-12-01 onward on dates where SSE and SZSE convertible records coexist with different values (SZSE 0.1% to 2014-08-25, SSE 0.02%). Pass `market=`. 37 sampled no-market answers that previously returned the SSE 0.0002 now refuse; none returns a different value.
- **Source policy:** archived web.archive.org copies of official exchange pages may be cited (see docs/SCHEMA.md); records resting on them are at most `single-source`.
- **Behaviour (lookups without a market):** `rule_at` / `record_at` called with `market=None` now raise `RuleConflict` for `limit_price_min_tick`/`stock` (from 2006-07-01: explicit SSE `false` vs SZSE records before 2023-04-10, and two separate per-exchange `true` records after it — `rule_at` has no agreement logic) and `price_limit_pct`/`delisting_day1` (2020-08-24 → 2020-12-31, SSE vs SZSE delisting day 1). `tick_size`/`stock` and `min_holding_days`/`stock` do **not** raise: the BSE records live under family scope `bse_stock` (see Changed), so only the XSHG+XSHE record answers (0.01 / 1). `session_schedule`/`stock` without a market raises from 2006-07-01 as before (SSE and SZSE have separate records). Values with a market given are unchanged (checked: 0 of 30,575 market-specific answers changed). **Pass `market=`.** 123 sampled no-market answers that 2026.10.26.5 returned now refuse (120 `limit_price_min_tick`/`stock`, 3 `price_limit_pct`/`delisting_day1`); none returns a different value.
- **Behaviour (code):** `limit_price(…, market=None)` now uses the tick when every in-force record of the family agrees
  instead of raising `RuleConflict`; with differing ticks it still raises. (Stock ticks no longer need it: the BSE tick is
  under family scope `bse_stock`, and the BSE board scopes map to that family.) `resolve('price_limit_pct', d, 'delisting_day1', 'XSHE', {board: chinext, …})` for
  2020-08-24 ≤ d < 2020-12-31 is now `MISSING_CONTEXT` (use `delisting_chinext_post0824`).
**Re-run** anything that touched those intervals (list printed by `python -m marina_rules.diff origin/main .`).

### Changed
- BSE transfer fee 2021-11-15 → 2022-04-29 moved to new family scope `bse_stock` (was `stock` with market BJSE), so
  market-less `stock` lookups no longer conflict; reported by the maintainer. The record was never released (absent
  from 2026.10.26.5), so its id `cn.fee.transfer_fee_each_side.bjse.2021-11-15` is kept and only `scope` changed.
  `rule_at("transfer_fee_each_side", d, "stock")` for 2021-11-15 ≤ d < 2022-04-29 now returns 0.00002 (SSE/SZSE);
  the BSE value is `rule_at(…, "bse_stock", "BJSE")` = 0.000025; `stock` + `BJSE` on those dates is `KeyError`.
  `bse_stock` registered in `data/cn/scopes.yaml` (no context requirements) and `docs/SCHEMA.md`; coverage target
  split into `BJSE:bse_stock:transfer_fee_each_side` (to 2022-04-29) and `BJSE:stock:…` (from it), still 100%;
  `marina check` looks up BJSE transfer fees under `bse_stock` first. Vectors: FEE-0024 (no market, 2022-04-28) now
  `DETERMINED` 0.00002, FEE-0029 repointed to scope `bse_stock`, +3 (FEE-0041..0043).
  The four other BSE-only records that sat under `stock` moved to `bse_stock` the same way (all unreleased, ids kept):
  `cn.tick.bse.2021-11-15` (tick_size 0.01), `cn.settle.bse.2021-11-15` (min_holding_days 1),
  `cn.session.stock.bse.2021-11-15` (session_schedule) and `cn.limit.min_tick.bse.2021-11-15` (limit_price_min_tick
  false). Family map: `tick_family()` / `lookup_scope()` send `bse`, `st_bse`, `ipo_day1_bse`, `delisting_bse`,
  `delisting_day1_bse` (and family `stock` asked with market BJSE) to `bse_stock`, so `tick_size()`, `resolve()`,
  `coverage()`, `limit_price()` and `marina check` answer BSE scopes exactly as before; `limit_price()` /
  `min_tick_band()` with market BJSE look up the scope, then `bse_stock`, then `stock`. `rule_at(r, d, "stock")`
  without a market now answers `tick_size` 0.01 and `min_holding_days` 1; `rule_at(r, d, "stock", "BJSE")` for these
  four rules is `KeyError` (use `bse_stock`). Coverage targets `BJSE:stock:{tick_size,min_holding_days,session_schedule,
  limit_price_min_tick}` → `BJSE:bse_stock:…` (applies to the five BSE scopes), still 100%. Vectors (allowed only
  because the records were never released): S3-0004/0005/0007/0008 repointed from `stock` to `bse_stock`; +5
  (S3-0036..0040: market-less `stock` tick and T+1, `bse_stock`/`stock`/`st_bse` tick with BJSE).
- **Publication dates researched for 10 of 16 records** with `published_at: null` (metadata only — no value or effective date changed; answers without `as_of` are byte-identical). Dated from official texts: 1996 10% band for `main_board`, `etf`, `b_share` and both `ipo_day1_main` records → 1996-12-13 (SSE/SZSE repeal registers of 2003: 上证交（96）字第036号 and 深证发（96）477号, both dated 1996.12.13; SZSE 1996 chronicle) — basis is an official register, not the notice text, noted per record; A-share T+1 → 1994-12-08 (SSE register: 上证交（94）字第3023号; SSE only); `st_chinext` 5% → 2009-10-26 (SZSE ChiNext trading notice); SSE B-share tick and SSE money-ETF T+1 → 2006-05-15 (SSE 2006 trading rules); CFFEX delivery fee 万分之一 → 2015-03-30 (CFFEX IH/IC listing notice; IF 2010-03-26). Still null, with search notes: 1998 ST 5% (`st_main`, `st_b_share`), `limit_price_rounding`, SZSE / SSE / BJSE transfer fees. `as_of` vectors: +20 (ASOF-0017..0036); ASOF-0013 repointed to a still-undated record. Under `as_of`, queries on the newly dated records now answer instead of `UNKNOWN_PUBLICATION`.
- `tests/test_coverage_targets.py`: the strict xfail is gone; `test_no_gap_outside_unresolved` fails on any gap not listed as
  unresolved. CI's coverage step is blocking (still printed to the job summary).
- Known gaps: G-0006, G-0017, G-0025 removed; G-0016 reworded and set to `open`; G-0019..G-0021 shrunk to XSHG before first listing; G-0026..G-0028 added.
- VERSION 2026.10.26.7 (`__init__`, pyproject, README, SKILL); README Status / Coverage table / coverage statement;
  capabilities.json and docs/decision.schema.json regenerated.

### Notes
- **ChiNext delisting window — maintainer decision 2026-10-26.** The independent audit is the spec (55 PASS / 4 FAIL, only
  `as_of`): its probe GAP-CHINEXT expects `resolve('price_limit_pct', '2020-09-01', 'delisting_chinext', …)` to report G-0016.
  So G-0016 is not removed: the context-free scope keeps no record in 2020-08-24..2020-12-31 and its target keeps that window
  as `unresolved` (counted against coverage, target not shrunk); both 620号 branches are recorded under new split scopes with
  their own complete targets.
- Single-source records rest on reading a complete official text for an absence (no floor) or on a scope covered as 债券 /
  基金 rather than by name; each record's notes say which.
- SSE 2013 trading-rules revision (上证发〔2013〕9号) and 上证基字〔2013〕86号 were found only as press reprints; the dates used
  come from SSE's own investor Q&A of 2013-12-03 (edu.sse.com.cn), cited verbatim.
- The SZSE 2022 convertible rules file cited is the 2022 attachment (page now marks it 已废止 after the 2025 re-publication;
  the 2025 revision is cited alongside with identical wording).

## [2026.10.26.6] - never tagged (content ships in 2026.10.26.7)

Dataset: `sha256:22869ed2ece35af0` · 153 records (132 `verified`, 21 `single-source`) ·
a pull request merged to `main` on 2026-10-25 as
`f0ae8b6`, plus the correctness fixes below (independent boundary audit) and coverage steps 1 and 2 (coverage
targets; fees). **Not tagged, not on PyPI, no GitHub release yet** — to be released next. The digest was
`sha256:23b8f92dcc262f92` at `f0ae8b6` and `sha256:cf6f6b31cd3edf68` after the audit fixes (which changed
`data/cn/equity_price_limits.yaml`, `known_gaps.yaml` and `scopes.yaml`); coverage step 1 changed `known_gaps.yaml`
statuses and step 2 changed `data/cn/equity_fees.yaml` (the digest covers every file under `data/`; the coverage
targets live in `coverage/` and do not affect it). If data changes again before the tag, it changes too.

### Added
- First non-equity market: **CFFEX** (`CCFX`) stock-index futures IF / IH / IC / IM, 46 records in the
  new file `data/cn/index_futures_margin_fee.yaml`:
  - `margin_ratio` (non-hedge position margin), scopes `cffex_if` `cffex_ih` `cffex_ic` `cffex_im` — 34 records, 2015-09-07 onward;
  - `trans_fee_rate` (trading fee on turnover), scope `cffex_index_futures` — 1 record, from 2015-08-03;
  - `close_today_fee_rate` (平今仓 fee) — 7 records, 2015-08-26 onward;
  - `delivery_fee_rate` (交割手续费) — 4 records, 2018-12-03 onward.
- New scopes in `data/cn/scopes.yaml`; rule names registered in `docs/SCHEMA.md`.
- 16 conformance vectors (`conformance/vectors/futures.json`; 182 vectors in total).

### Corrected (re-run needed)
None. `diff_rules 2026.10.26.5 → f0ae8b6`: `coverage_added=46` only; no existing record changed.
**Re-run:** nothing.

### Correctness fixes (independent audit)
An independent boundary audit (2026-10-26) probed 59 boundaries: 34 PASS / 25 FAIL on `f0ae8b6`, 55 / 4 after
these fixes. The audit now runs unchanged in CI as `tests/audit/boundary_audit.py` (gate:
`tests/test_boundary_audit.py`); only the four `as_of` probes may fail (separate feature, not implemented).
`diff_rules f0ae8b6 → this`: `coverage_added=1` (`cn.tick.convertible.2022-08-01`). The behaviour changes below
are invisible to the diff because they are code or registry changes:
- **Convertible tick 0.001 元** from 2022-08-01 (`cn.tick.convertible.2022-08-01`, verified: SSE 上证发〔2022〕117号 /
  SZSE 深证上〔2022〕719号 art. 6 「申报价格最小变动单位为0.001元」, also the 2025 revisions). `tick_size('convertible'|
  'convertible_day1', …)` used to fall through to the stock family and return 0.01, so `limit_price` rounded
  convertible bands to the cent (100.003 → 120.00 / 80.00; now 120.004 / 80.002). Before 2022-08-01 the convertible
  tick is new gap **G-0025** (exchange texts give a 债券 tick that differed by exchange). Closes CB-TICK-XSHE,
  CB-TICK-XSHG, CB-ROUND-XSHE, CB-ROUND-XSHG.
- **Market-set conflicts.** `record_at` / `coverage` treated in-force records with different market strings as
  non-conflicting even when the sets intersect (`XSHG+XSHE` vs `XSHE`); the loader's overlap check compared exact
  strings. Both now use set intersection. The current dataset has no such overlap. Closes OVERLAP-MARKET.
- **Contradictory / null context → `MISSING_CONTEXT`.** Ad-hoc `_SCOPE_ASSERTS/_SCOPE_RANGES` replaced by declarative
  per-scope `asserts` / `rule_asserts` in `data/cn/scopes.yaml` (published in capabilities.json): board must match
  the scope; ordinary boards exclude the IPO window (main board day ≥ 2, ≥ 6 from 2023-04-10 unless
  `issue_regime: approval`; ChiNext likewise from 2020-08-24; STAR ≥ 6); `ipo_first5_*` days 1–5 and registration
  regime; `etf_20pct` ⇔ `all_20pct_band`; `convertible` ≥ 2 / `convertible_day1` = 1; delisting / reits day 1 vs
  later; `bse` not ST; a key passed as `null` is missing; `min_holding_days` under `etf` with a cross-border fund
  requires `underlying_t0` (false → T+1). Closes CTX-BOARD, CTX-IPO-ORDINARY, CTX-REGIME, CTX-ETF-CONTENTS,
  CTX-CB-DAY1, CTX-DELIST-DAY, CTX-REITS-DAY, CTX-BSE-ST, CTX-NULL, CROSSBORDER-UNKNOWN.
- **`scripts/audit_bars.py` IPO regime** now follows the listing date per board (main board 2023-04-10, ChiNext
  2020-08-24, STAR from inception): sh.603000 listed 2023-03-01 is `ipo_day1_main`, not `ipo_first5_main`; rows
  2–5 of a pre-cutoff listing are the ordinary band. Closes AUDIT-IPO-DATE.
- **`marina check`**: non-finite price / prev_close (nan, inf, empty) is `ROW_INVALID` even for unlimited scopes;
  new finding `PRICE_OFF_TICK` (price not a multiple of the family tick in force, Decimal comparison). Closes
  CHECK-NAN-UNLIMITED, CHECK-OFFTICK.
- **Stamp** now commits to every column a check uses (date, code, side, price, prev_close, scope, market, decimals,
  fee, turnover) plus the strict flag, in a documented canonical form (`marina-check-canon/2`). Stamps issued by
  earlier versions are not comparable. Closes STAMP-FEE, STAMP-MARKET.
- **Coverage vs resolve for `tick_size`**: one shared mapping (`marina_rules.lookup_scope` / `tick_family`) used by
  `tick_size()`, `resolve()` and `coverage()`; `coverage('XSHE','main_board',['tick_size'],…)` is now `complete`.
  Closes COVER-TICK-FAMILY.
- **JSON-safe output**: YAML date objects inside record values and sources are normalised to ISO strings at load
  time; `json.dumps(resolve(...))` no longer fails on evidence dates. Every record is now tested through `resolve`
  against `docs/decision.schema.json`.
- 23 conformance vectors (`ruleset_version_min: 2026.10.26.7`; 205 in total before coverage step 2, 231 after).

**Re-run needed** if you used: convertible-bond ticks or `limit_price` on convertibles from 2022-08-01 (cent
rounding was wrong); `resolve()` with contradictory context (wrong board, listing day inside the IPO window, wrong
day index, mixed constituents under `etf_20pct`, ST under `bse`, null values, cross-border funds under `etf`) — such
calls returned DETERMINED and now return MISSING_CONTEXT; `scripts/audit_bars.py` on main-board listings
2023-02-17 … 2023-04-09 or ChiNext/STAR listing windows; `rules-verified` stamps (recompute — the canonical form
changed); `coverage()` conflict reports where market strings differed.

### Changed
- README Status / Coverage table and SKILL.md citations updated to 2026.10.26.6; capabilities.json regenerated.
- README/SKILL/SCHEMA: finding codes, stamp canonical form, context constraints; capabilities.json regenerated (scope `asserts`, tick families).
- Coverage targets (step 1 of 3): `coverage/cn_targets.yaml` declares the A-share denominator
  (XSHG, XSHE, BJSE from 2006-07-01; maintainer decision 2026-10-25), `scripts/coverage_report.py` reports
  target-days covered and every gap interval (`--json`, `--markdown`, `--brute`), CI prints it (informational).
  No record changed.
- Known gaps lying wholly before 2006-07-01 (G-0001, G-0005, G-0007, G-0013, G-0014, G-0015, G-0018,
  G-0022, G-0023, G-0024) set to `status: wontfix` — out of scope by maintainer decision 2026-10-25.

### Step 2 (fees) — coverage targets, step 2 of 3
- **Added** 18 fee records, new rules `stamp_duty_buy` and `transfer_fee_par_value` (registered in `docs/SCHEMA.md`):
  bilateral stamp duty 2005-01-24 (1‰) / 2007-05-30 (3‰) / 2008-04-24 (1‰), buy side 0 from 2008-09-19; SSE transfer
  fee by par value 0.5‰ / 0.375‰ (2012-06-01) / 0.3‰ (2012-09-01) until 2015-08-01; SZSE 0.0255‰ of turnover inside
  the handling fee 2006-07-01..2015-08-01; BJSE stamp duty and transfer fee (0.025‰ until 2022-04-29) from
  2021-11-15; commission cap / minimum for funds (`etf`) and REITs (`reits`).
- **Corrected (re-run needed)** — `diff_rules origin/main → step 2` reports 8 `correction`s, none of which changes a
  value previously returned for XSHG/XSHE: (a) stamp duty before 2008-09-19 and SZSE transfer fee before 2015-08-01
  were `KeyError` and now have records (classified as correction because the key already had later history);
  (b) `cn.fee.stamp_duty_sell.2008-09-19` now ends 2021-11-15 and continues unchanged (0.1%) as
  `cn.fee.stamp_duty_sell.2021-11-15` covering XSHG+XSHE+BJSE; (c) `cn.fee.stamp_duty_sell.2023-08-28` and
  `cn.fee.transfer_fee_each_side.2022-04-29` now also cover BJSE (their notices are national / name the Beijing
  market). The BSE 0.025‰ transfer fee (2021-11-15 → 2022-04-29) is recorded under the new family scope `bse_stock`
  (see Changed), so market-less `stock` lookups do not conflict. Conformance FEE-0001 (now 1‰) and
  FEE-0005 (now `market: XSHG+XSHE`) changed accordingly; 26 new vectors in `conformance/vectors/fees.json`.
- `marina check`: the statutory fee floor now uses the fill's side (`stamp_duty_buy` for buys) and the row's `market`;
  a par-value transfer fee is never multiplied by turnover (it is left out of the lower bound).
- Coverage targets: `not_applicable` (structured, hashed sources) for stamp duty and transfer fee on funds, REITs and
  convertibles; transfer-fee target for XSHG split at 2015-08-01 (`transfer_fee_par_value` before);
  `unresolved`: convertible commission (delegated to exchanges, no filing found) and BJSE commission.
  `scripts/coverage_report.py` lists not-applicable targets separately. Coverage 59.87% → 83.27% on the pre-audit base (83.70% on top of the audit fixes, whose convertible tick record shrinks that gap to 2006-07-01..2022-08-01, G-0025); no fee gap left
  unexplained.

### Notes
- CFFEX settlement-parameter XML field `JG_TRANSFEE_RATE` is the **delivery** fee, not the close-today
  fee (it halves exactly on the delivery-fee halving dates 2021-08-16 and 2024-01-08). The close-today
  fee is sourced from notices.
- `single-source` (8): six historical close-today fees 2015-08-26 … 2023-03-20 (no XML field; notice is
  the only official source); delivery fee base 1e-4 from 2018-12-03 (founding notice not located, start
  date conservative); delivery fee 2024-01-01 … 01-07 (inferred; XML for those days returned empty).
- Not covered: hedge-position margins, per-order declaration fees, the 2025–2026 high-frequency-trader
  exclusion from the delivery-fee halving, and the 2015-07/08 asymmetric long/short margin steps.
- The PR description says "version 2026.10.26.5" in one sentence; the merged code sets 2026.10.26.6.

## [2026.10.26.5] - 2026-10-25

Dataset: `sha256:4b17aa985fe49ae7` · 88 records (78 `verified`, 10 `single-source`) ·
on PyPI.

### Added
- Rule `session_schedule` (6 records): SZSE stocks and funds from 2006-07-01 (close call 14:57–15:00);
  SSE stocks 2006-07-01 → 2018-08-20 without a close call, then with one; SSE funds continuous to 15:00
  from 2006-07-01, close call from 2026-07-06.
- `min_holding_days` for funds (11 records): new scopes `etf_bond`, `etf_money`, `etf_gold`,
  `etf_crossborder` = 0 (T+0) from 2015-01-19; `etf_commodity` T+0 from 2019-01-11 (XSHE, single-source
  date) / 2020-01-20 (XSHG), T+1 before from 2006-07-01; `etf_crossborder` T+1 2006-07-01 → 2015-01-19;
  `etf`, `etf_20pct` T+1 from 2006-07-01.
- Context keys `fund_type` and `underlying_t0`. 166 conformance vectors (+30).

### Corrected (re-run needed)
- `correction` `cn.limit.convertible.2006-07-01` — `XSHG+XSHE/convertible/price_limit_pct` [2006-07-01, 2022-08-01): `unlimited`.
- `correction` `cn.limit.convertible_day1.2006-07-01` — `XSHG+XSHE/convertible_day1/price_limit_pct_of_issue_price` [2006-07-01, 2022-08-01): `unlimited`.

Both are "history re-cut": new intervals before existing history. 2026.10.26.4 had no record there (known
gap G-0001 → `KeyError` / `OUT_OF_COVERAGE`), so no value Marina previously returned changed.
**Re-run:** pre-2022-08-01 convertible-bond backtests that substituted a price band for the missing rule — the rule was "no band".

### Changed
- `resolve()` asks rule-specific context: `min_holding_days` needs only `fund_type` / `underlying_t0`;
  for `etf` / `etf_20pct` it requires `fund_type` and rejects a same-day type. `session_schedule` needs no context.
- `resolve("tick_size", …)` uses the same fund-family map as `tick_size()`; `price_limit_pct_of_issue_price` may be `unlimited`.
- Known gaps: G-0013 closed from 2006-07-01 on; G-0001 and G-0007 shrunk to before 2006-07-01; new
  G-0018 … G-0024 (pre-2006 residuals; bond/money/gold ETF T+0 before 2015-01-19).

### Notes
- SSE convertibles 2006–2022 rest on "convertibles are bonds" plus the monitoring rules' wording; no SSE
  text names convertibles as unlimited → `single-source`.
- Bond / money / gold ETF T+0 actually started in late 2013; the 2013 switch texts were found only as
  press reprints, so the records start at 2015-01-19 and 2013–2015 stays a declared gap.
- One secondary source is cited (SZSE 深证会〔2019〕23号, found only as a reprint); that record is `single-source`.
- Convertible intraday halt thresholds are noted, not encoded.
- The GitHub release originally carried only auto-generated notes; this entry replaces them.

## [2026.10.26.4] - 2026-10-25

Dataset: `sha256:ab6d42b9282414d5` · 69 records (63 `verified`, 6 `single-source`) ·
on PyPI.

### Added
- `limit_price_min_tick` for the SSE delisting board (¥0.01 band when prev close is below ¥0.05 from
  2013-01-01, at or below ¥0.05 from 2020-12-31 to 2023-04-10; `delisting_day1` 2013-01-01 → 2020-12-31)
  — 3 `coverage_added` records.
- 136 conformance vectors (+23).

### Corrected (re-run needed)
`diff_rules`: 10 corrections, all "history re-cut" — new intervals placed before existing history:
- `cn.settle.b_share.2006-07-01` — `XSHG+XSHE/b_share/min_holding_days` [2006-07-01, 2011-02-28)
- `cn.tick.a_share.2006-07-01` — `XSHG+XSHE/stock/tick_size` [2006-07-01, 2011-02-28)
- `cn.tick.fund.2006-07-01` — `XSHG+XSHE/etf/tick_size` [2006-07-01, 2011-02-28)
- `cn.tick.b_share.sse.2006-07-01` — `XSHG/b_share/tick_size` [2006-07-01, 2011-02-28)
- `cn.tick.b_share.szse.2006-07-01` — `XSHE/b_share/tick_size` [2006-07-01, 2011-02-28)
- `cn.limit.delisting.szse.2012-12-17` — `XSHE/delisting/price_limit_pct` [2012-12-17, 2020-12-31)
- `cn.limit.delisting_chinext.2012-12-17` — `XSHE/delisting_chinext/price_limit_pct` [2012-12-17, 2020-08-24)
- `cn.limit.delisting_day1.szse.2012-12-17` — `XSHE/delisting_day1/price_limit_pct` [2012-12-17, 2020-08-24)
- `cn.limit.delisting_day1_star.2019-07-22` — `XSHG/delisting_day1_star/price_limit_pct` [2019-07-22, 2020-12-31): 20% (the 2019 rules did not exempt day 1)
- `cn.limit.delisting_day1_star.2020-12-31` — `XSHG/delisting_day1_star/price_limit_pct` [2020-12-31, 2023-04-10): unlimited

Each fills a range where 2026.10.26.3 raised `KeyError` (declared known gap); per the PR, no value
Marina previously returned changed. One behaviour change the diff does not label a correction:
`limit_price(0.04, "delisting", d, "XSHG")` for 2013-01-01 ≤ d < 2023-04-10 now returns (0.05, 0.03)
instead of (0.04, 0.04). **Re-run:** SSE delisting-board backtests with prev close ≤ ¥0.05 in
[2013-01-01, 2023-04-10), and anything that substituted a value for the ten intervals above.

### Changed
- **STAR citation fixed: consultation draft → final text.** Four `verified` STAR records
  (`cn.limit.star.2019-07-22`, `cn.limit.st_star.2019-07-22`, `cn.limit.ipo_first5.star.2019-07-22`,
  `cn.limit.delisting_star.2019-07-22`) cited a municipal reprint of the **consultation draft**
  (征求意见稿, art. 16, jrj.wuhan.gov.cn). Replaced with the final **上证发〔2019〕23号** PDF on
  sse.com.cn (art. 18), quoted verbatim and hashed. Values unchanged (`diff_rules`: `metadata`); dataset
  digest changed. Commit `b211dd8`, squashed into the pull request of this release.
- `limit_price()` / `min_tick_band()` look up a scope-specific `limit_price_min_tick` before scope
  `stock`; a dict value is a board-specific absolute band. `round_half_up` untouched.
- Known gaps: G-0011 closed; G-0005 and G-0014 shrunk to before 2006-07-01; G-0010 / G-0012 shrunk to
  before 2012-12-17; new G-0016 / G-0017 (`wontfix`: SZSE 2020-08-24 → 2020-12-31 band depends on the
  delisting-period entry date, which a scope cannot carry).
- `metadata` on 9 records (the four STAR records above plus notes on five successor records).

### Notes
- G-0005 / G-0014 before 2006-07-01: the 2001 joint trading rules were found only on press / commercial
  law databases. G-0010 / G-0012 before 2012-12-17: earlier SZSE arrangements unsourced.
- SSE 2015/2017/2018 risk-warning-board revisions were not hashed; the "低于" → "低于或等于" wording
  change is attributed to 2020-12-31 (first hashed text with it). It only affects prev close exactly ¥0.05.
- The GitHub release originally carried only auto-generated notes; this entry replaces them.

## [2026.10.26.3] - 2026-10-25

Dataset: `sha256:b7e1c4ec8d08d5e9` · 56 records (50 `verified`, 6 `single-source`) ·
on PyPI.

### Added
17 records (`coverage_added`), closing known gaps G-0002, G-0004, G-0008, G-0009:
- Delisting arrangement period: SSE main 10% from 2013-01-01 (day 1 not exempt until 2020-12-31, then
  unlimited); SZSE main 10% / ChiNext 20% with day 1 unlimited from 2020-12-31; STAR 20% (day 1
  unlimited from 2023-04-10); BSE delisting band and day 1.
- REITs: ±30% listing day / ±10% after, from 2021-01-29 (SSE `verified`, SZSE `single-source`).
- `min_holding_days` (T+1): A shares 1 from 1995-01-01 (start date `single-source`); B shares 1 from 2011-02-28.
- BSE ST: one 30% band, no ST exception (`st_bse`).
- Context key `delisting_day_index`. 113 conformance vectors (+25).

### Corrected (re-run needed)
None (`diff_rules 2026.10.26.1 → 2026.10.26.3`: `coverage_added=17`). **Re-run:** nothing.

### Changed
- Known gaps: G-0002, G-0004, G-0008, G-0009 closed; residuals recorded as new gaps G-0010 … G-0015
  (SZSE delisting before 2020-12, STAR delisting day 1 2019–2023, same-day-rotation funds, B-share T+1
  2001–2011, pre-1995 T+0 `wontfix`).

### Notes
- **There is no 2026.10.26.2 tag.** `2026.10.26.2` was set as the version in commit `6656041` (delisting
  period + REITs, 12 records; citation in that commit: `sha256:a2ece0f1027c3717`). Its pull request was
  closed unmerged; the work continued on branch `feat/t-plus-one`, whose pull request was squash-merged as
  2026.10.26.3. 2026.10.26.2 was never tagged, released or published.
- The GitHub release originally carried only auto-generated notes; this entry replaces them.

## [2026.10.26.1] - 2026-10-25

Dataset: `sha256:1bf8eb29d05157c6` · 39 records (36 `verified`, 3 `single-source`) ·
**first version on PyPI**.
**Data identical to 2026.10.26** (same digest; `diff_rules` reports no change).

### Added
- Rule Decision Contract: `resolve(rule, trade_date, scope, market, context, min_verification)` returns
  one dict with `status ∈ {DETERMINED, MISSING_CONTEXT, OUT_OF_COVERAGE, CONFLICT, UNVERIFIED}`; CLI
  `python -m marina_rules.contract`. `docs/decision.schema.json` and `capabilities.json` are generated
  from the data and CI diffs them against a fresh generation.
- 88 conformance vectors with independent oracles; `conformance/run.py`.
- Release pipeline: wheel with the dataset vendored inside (digest checked against the repo), JSON /
  SQLite dumps, `SHA256SUMS`, PyPI trusted publishing.

### Corrected (re-run needed)
None (no data change). **Re-run:** nothing.

### Changed
- **Version scheme → `YYYY.MM.DD.N`**. The first release-workflow run, on tag `2026.10.26b`
  (commit `1ee5b99`), built `2026.10.26b0` — a PEP 440 pre-release; its PyPI publish step failed. No
  GitHub release exists for `2026.10.26b` and the tag is no longer on the remote. GOVERNANCE.md now
  forbids letter suffixes and the release workflow rejects pre-release tags.

### Notes
- The GitHub release originally carried only auto-generated notes; this entry replaces them.

## [2026.10.26] - 2026-10-25

Dataset: `sha256:1bf8eb29d05157c6` · 39 records (36 `verified`, 3 `single-source`) ·
GitHub only (not on PyPI).

### Added
- One-tick floor, sourced per exchange: rule `limit_price_min_tick` — SZSE from 2011-02-28, SSE only
  from 2023-04-10.
- Rule `tick_size` (from 2011-02-28): A shares 0.01 CNY, funds 0.001 CNY, B shares 0.001 USD (SSE) / 0.01 HKD (SZSE).
- `data/cn/known_gaps.yaml`: 9 declared non-coverages; `coverage()` attaches `known_gap_ids`.
- `diff_rules`: `coverage_added=6`.

### Corrected (re-run needed)
None in `diff_rules`. Behaviour change it cannot see: `limit_price()` now composes band × tick × floor,
so results differ **only** when prev close ≤ ¥0.05 at 10% / ≤ ¥0.09 at 5% / ≤ ¥0.02 at 20%, and it raises
`ValueError` at that boundary when no `market` is given. **Re-run:** only backtests that hit those
sub-¥0.10 prev closes (the maintainers' 9.1M-bar audit was byte-identical; 9 boundary rows, all
forward-adjustment artefacts).

### Changed
- `check.py` adds `MARKET_REQUIRED`; the `decimals` column is optional.

### Notes
- Release title: "one-tick floor (per exchange), tick sizes, known gaps as data". 69 tests.

## [2026.10.25c] - 2026-10-25

Dataset: `sha256:a360d49eb6511b91` · 33 records (31 `verified`, 2 `single-source`) ·
GitHub only; PEP 440 reads this
version as `2026.10.25rc0` (pre-release).

### Added
- `python -m marina_rules.diff <from> <to>` (`diff_rules`): every change classified as `correction`,
  `regime_change`, `coverage_added`, `rename`, `bookkeeping` or `metadata`, ending with the re-run list.
- `errata/` registry: E-0001 (stale pct-change column), E-0002 (sub-¥1 adjusted-price rounding).
- `st_b_share`: 5% from 1998-04-22 to 2026-07-06 (`single-source`), then 10% (`verified`).
- `etf_20pct` SSE record from 2020-08-21 (上证发〔2020〕61号).

### Corrected (re-run needed)
None (`diff_rules`: `coverage_added=3`, `rename=1`, `metadata=2`). **Re-run:** nothing.

### Changed
- Rename: scope `etf_chinext` → `etf_20pct` (`cn.limit.etf_chinext.2020-08-24` → `cn.limit.etf_20pct.szse.2020-08-24`). Update code, not results.

### Notes
- 58 tests.

## [2026.10.25b] - 2026-10-25

Dataset: `sha256:2cc08f77e95c7e3c` · 30 records (29 `verified`, 1 `single-source`) ·
GitHub only; PEP 440 pre-release (`b0`).

### Added
- `st_star`: STAR has risk warnings — \*ST since the 2019 listing rules, ST since the 2024-04-30
  revision; band stays ±20%. `star` now requires `st_status`.
- `convertible` 20% from 2022-08-01; `convertible_day1` +57.3% / −43.3% of issue price (rule
  `price_limit_pct_of_issue_price`); `etf` 10%; `etf_chinext` 20% from 2020-08-24; `b_share` 10%
  (`single-source` start date).
- `scripts/audit_bars.py --use-st`.

### Corrected (re-run needed)
None in `diff_rules` (`coverage_added=6`, `metadata=1`). The release notes call the STAR finding a
correction ("Marina said no ST on STAR"); the band is unchanged at ±20%, so no limit price changes.
**Re-run:** nothing for price limits; revisit any STAR logic that assumed no risk-warned STAR stocks.

### Changed
- Docs: launchd + macOS folder protection (first scheduled audit exited 126), `docs/automation.md`.

### Notes
- First ST audit over 9.1M bars: `st_main` (5%) 170,939 ST-days / 3 violations, attributed to vendor
  adjusted-price rounding below ¥1 (errata E-0002).

## [2026.10.25] - 2026-10-24

Dataset: `sha256:8e4e9a7a7b556d6e` · 24 records (all `verified`) ·
GitHub only. Published 2026-10-24 (JST)
despite the name.

### Added
- `coverage(market, scope, rules, start, end)`; scope registry `data/cn/scopes.yaml` (`requires` /
  `excludes`); `RuleConflict`; `published_at` / `recorded_at` on every record; `SKILL.md` and
  `examples/agent_walkthrough.py`.
- Source watch and daily audit automation (`scripts/source_watch.py`, `ops/`); `content_sha256`.

### Corrected (re-run needed)
- `correction` `cn.limit.ipo_day1.1996-12-16` — `XSHG+XSHE/ipo_day1/price_limit_pct` [1996-12-16, 2014-01-01): superseded by per-exchange records.
- `correction` `cn.limit.ipo_day1.main.sse.1996-12-16` — `XSHG/ipo_day1_main/price_limit_pct` [1996-12-16, 2013-12-13).
- `correction` `cn.limit.ipo_day1.main.szse.1996-12-16` — `XSHE/ipo_day1_main/price_limit_pct` [1996-12-16, 2014-06-13).

In 2026.10.24b one unlimited listing-day record covered both exchanges until 2014-01-01, so SSE had two
records in force 2013-12-13 → 2014-01-01 and SZSE had none 2014-01-01 → 2014-06-13. It is now split and
ends on each exchange's own switch date (SSE 2013-12-13, SZSE 2014-06-13). **Re-run:** main-board listing-day
(day 1) backtests in [1996-12-16, 2014-06-13), in particular SSE 2013-12-13 → 2014-01-01 and SZSE 2014-01-01 → 2014-06-13.

### Changed
- **Breaking** — listing-window scopes split per board (`ipo_day1_main`, `ipo_day1_bse`,
  `ipo_first5_main`, `ipo_first5_chinext`, `ipo_first5_star`); 6 renames. See `docs/SCHEMA.md`.
- Bookkeeping: `stamp_duty_sell` 2008 record closed at 2023-08-28; `transfer_fee_each_side` 2015 record closed at 2022-04-29 (lookups unchanged).
- Policy: `sha256` + verbatim `quote` mandatory for every source of a `verified` / `single-source` record, enforced at load time.

### Notes
- 47 sources content-hashed.

## [2026.10.24b] - 2026-10-24

Dataset: `sha256:9b0332574af22659` · 23 records (all `verified`) ·
GitHub only; PEP 440 pre-release (`b0`).
Primary-source audit: `docs/sources-audit-2026-10-24.md`.

### Added
- `regime_change` `cn.limit.st_main.2026-07-06` — main-board ST band ±10% from 2026-07-06
  (2026.10.24 carried ±5% as still in force; the release notes count this as correction no. 1).

### Corrected (re-run needed)
- `correction` `cn.limit.st_main.1998-04-22` — `XSHG+XSHE/st_main/price_limit_pct` [1998-04-22, ∞): start 1998-04-27 → 1998-04-22, now ends 2026-07-06.
- `correction` `cn.limit.ipo_first5.main.2023-04-10` — `XSHG+XSHE/ipo_first5/price_limit_pct` [2023-02-17, ∞): main-board "first 5 days unlimited" from 2023-04-10, not 2023-02-17.
- `correction` `cn.limit.ipo_day1.2014-01-01` — `XSHG+XSHE/ipo_day1/price_limit_pct` [2014-01-01, 2023-02-17): superseded by per-exchange records.
- `correction` `cn.limit.ipo_day1.sse.2013-12-13` — `XSHG/ipo_day1/price_limit_pct` [2013-12-13, 2023-04-10): 64%–144% band on SSE from 2013-12-13.
- `correction` `cn.limit.ipo_day1.szse.2014-06-13` — `XSHE/ipo_day1/price_limit_pct` [2014-06-13, 2023-04-10): on SZSE only from 2014-06-13.

**Re-run:** main-board ST after 2026-07-06; main-board IPO days 2023-02-17 → 2023-04-10; listing days
2013-12-13 → 2023-04-10 (especially SZSE 2014-01-01 → 2014-06-13). The 1998 ST start moved 5 days; per
the audit no bar after 1998 is affected.

### Changed
- `metadata` on 18 records: every record raised from `unverified` to `verified` with official sources and quotes.

### Notes
- Items 1–3 were also wrong in `data-backtest-live-common` 0.3.0.

## [2026.10.24] - 2026-10-24

Dataset: `sha256:49bbded901560bd6` · 21 records (all `unverified`) · first release, GitHub only.

### Added
- China A-share price limits (15 records, 1996 →) and transaction fees (6 records).
- `python -m marina_rules.check` fill-log checker and `scripts/audit_bars.py`.

### Corrected (re-run needed)
None (first release).

### Changed
None.

### Notes
- All records `unverified` at this tag: consistent with 9.1M daily bars and an independent chronology,
  but primary sources not yet individually confirmed. Superseded the same day by 2026.10.24b.
