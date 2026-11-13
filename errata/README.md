# Errata — ways market data lies about the rules

Marina encodes what the rule *was*. When a rule looks violated by data, so far the data has been wrong
every time. This registry records those cases so the next person does not re-derive them: what the
symptom looks like, how to detect it in your own data in one command, and the arithmetic or source
that settles it. Each entry has a `reproduce.py` and a small sample taken from the maintainers' bars.

Entries are not bug reports against any vendor. They are properties of *classes* of data — adjusted
series, precomputed columns — that any pipeline can exhibit, including ours (E-0001 is ours).

| id | symptom | one-line detector |
|---|---|---|
| [E-0001](E-0001.md) | a precomputed pct-change column disagrees with close/preclose beside it; limit-up counts inflate | `python errata/E-0001/reproduce.py <bars_dir>` |
| [E-0002](E-0002.md) | forward-adjusted prices rounded to ¥0.01 below ¥1 show ±6% moves inside a 5% band | `python errata/E-0002/reproduce.py <adjusted.csv> [<unadjusted.csv>]` |

Rules of this registry: an entry needs a sample that reproduces, a detector that exits non-zero on the
defect, and the fact that settles it (exchange prices, the exchange's rounding rule, a notice). "I
think the vendor is wrong" is not an entry. Open a PR with a new `E-xxxx/` directory.

What `scripts/audit_bars.py` does about these: it never reads pct-change columns (E-0001) and it
leaves E-0002-type rows red rather than widening tolerance — a rule that is only "right" with a
tolerance wide enough to hide data defects is not being tested.
