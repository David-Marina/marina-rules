# Primary-source audit — 2026-10-24

All 21 records in the first tag (2026.10.24) were released at `verification: unverified`. The same day, every record was traced to primary sources. Result: **23 records (after two splits and one addition), all `verified`**, and **four substantive corrections** to what the maintainers — and the independent chronology in `data-backtest-live-common` 0.3.0 — had believed.

Method: for each record, locate the exchange / ministry / depository notice; open it (HTML, PDF, or DOCX attachment); copy the sentence that states the value and date into `quote`; record the page SHA-256. Secondary sources were used only to locate primaries. Where officials disagree, the disagreement is in `notes`.

## Corrections

| # | before | after | source | affects |
|---|---|---|---|---|
| 1 | Main-board ST band ±5%, still in force | **±10% from 2026-07-06** | SSE & SZSE 2026-04-24 notices, 2026 Trading Rules (SSE art. 3.3.13) | every main-board ST bar after 2026-07-06 |
| 2 | Main-board "first 5 days unlimited" from 2023-02-17 | **from 2023-04-10** (first registration-based main-board listing); approval-regime IPOs listed 2023-02-17..04-07 kept the 64–144% day-1 band | SSE 上证发〔2023〕32号: 自按照《首次公开发行股票注册管理办法》发行的首只主板股票上市首日起施行 | IPO days Feb–Apr 2023 |
| 3 | 64%–144% day-1 band on both exchanges from 2014-01-01 | **SSE from 2013-12-13** (上证发〔2013〕47号); **SZSE only from 2014-06-13** (深证会〔2014〕54号) — before that SZSE had an opening-auction ±20% range plus halts, not a full-day band | SSE 2013-12-13 notice; SZSE 2014-06-13 notice | SZSE listing days Jan–Jun 2014 |
| 4 | ST regime start 1998-04-27 | **1998-04-22** per SSE event chronology (04-27 SZSE retrospective; 04-28 first ST stock). No bar after 1998 is affected. | SSE events page; SZSE 2018 retrospective | nothing material |

Items 1–3 were wrong in `data-backtest-live-common` 0.3.0 as well. Item 1 had been reported correctly by `ashare-data-immunity` 0.1.4, which the maintainers initially declined to adopt for lack of a source. The source existed; we had not found it. That is the whole argument for this repository.

## Things learned that are *not* encoded (yet)

- **Bond / money-market ETFs are not "unlimited".** SSE's 债券ETF业务指南 and interface spec treat all funds as having a 10% band. Any engine that exempts them is wrong; the price just never gets near the band. An `etf` scope will be added in a later tag.
- **ChiNext 2020-08-24 exception.** Stocks already in the delisting consolidation period on that date stayed at 10%. Not encoded; affects three securities.
- **Convertibles.** ±20% from 2022-08-01; listing day +57.3% / −43.3% with 20%/30% intraday halts. Will be added under a `convertible` scope.
- **2026 rounding addendum.** When |limit − prev_close| is less than one tick, the limit is prev_close ± one tick (SSE 2026 rules 3.3.17). `round_half_up` does not implement this edge case yet.
- **B shares.** 10%; ST B shares followed the A-share ST band (5% → 10% on 2026-07-06). Pending a `b_share` scope.

## Verification policy applied

- `verified` requires an official source whose text states the value and the date, or two independent official sources that agree.
- Where a source states a rule only by reference ("halved"), the derived number is recorded and the derivation is said in `notes` (stamp duty 2023-08-28).
- Page hashes are recorded for every source the CI runner or the maintainers could fetch. Some exchange hosts block CI; the hash is the durable evidence, reachability is advisory.

Dataset digest after this audit: see the 2026.10.24b entry in [docs/history/CHANGELOG-through-2026.11.02.md](history/CHANGELOG-through-2026.11.02.md).
