# Agent evaluation

**Question:** can an AI coding assistant that has never seen marina-rules use it correctly from the installed package
alone? Correctly means: pre-flight a window before trusting it, query the rule in force on the right date with the
right rounding, stop and name the missing facts instead of assuming them, report "not covered" and "known gap"
instead of inventing a value, notice when an answer is only carried forward past what was checked, and cite the
dataset it used.

This is a measurement of the package's usability for assistants, not a test of the package. The package's own
correctness is tested in `tests/` and `conformance/`.

## Files

| file | what |
|---|---|
| `tasks.json` | 14 short tasks, each answerable from the installed package alone, each saying what to return |
| `files/fills_exchange.csv`, `files/fills_model.csv` | the two fill logs tasks T10 and T11 read |
| `ANSWER_FORMAT.md` | what to write in `answers.json`; says what to report, not how the package works |
| `prompts/installed_only.txt` | prompt for condition A: the package is installed, nothing else |
| `prompts/with_skill.txt` | prompt for condition B: the same, plus "read SKILL.md first" |
| `build_expected.py` | builds `expected.json` (and `TASKS.md`) by calling the library, so expectations follow the data |
| `expected.json` | the expected answers, generated; `tests/test_evals.py` asserts it equals a fresh build |
| `TASKS.md` | the tasks with their expected answers, for people (generated; never give it to the assistant) |
| `grade.py` | grades one `answers.json` |

## Running it

1. Build the two wheels of the release under test (`marina-rules-data` and `marina-rules`) and install them, alone,
   into a fresh virtual environment.
2. For each run, make an empty directory and copy into it: `tasks.json`, the two CSVs from `files/`,
   `ANSWER_FORMAT.md`, and, for condition B only, `SKILL.md` from the repository root. Nothing else: not
   `expected.json`, `TASKS.md`, `grade.py` or this README.
3. Fill the prompt: replace `{PYTHON}` in the prompt file with the path of that environment's interpreter.
4. Start a **fresh** assistant session in that directory (no memory of earlier runs, no access to the repository or
   the web), give it the prompt, and let it finish.
5. Grade: `python evals/grade.py <run-dir>/answers.json` (add `--json` for machine-readable output).

Run each condition at least twice; results vary from run to run.

## Reading the grades

Per task, one of:

| grade | meaning |
|---|---|
| `correct` | matches the expected answer |
| `wrong` | a different value, status, row set or list of missing facts; also a carry-forward flag where none applies, or "needs context" where the task gives everything needed |
| `fabricated` | a value where the right answer is "needs context", "not covered" or "known gap" (a value next to such a status counts too), or the right value for a carried-forward rule without the carry-forward flag |
| `missing` | no entry for the task |

`fabricated` is the grade that matters most: it is the failure the package exists to prevent. The citation is graded on
its own line (`ok` / `missing` / `mismatch` against the version and dataset digest in `expected.json`) and does not
change the task grades. The last line is a one-line summary; the exit code is 0 whatever the grades (2 only when a file
cannot be read).

**Tolerance.** Prices: 0.001 (prices have two decimals, so a one-cent rounding error is wrong). Rates and fractions:
1e-9 (recorded exactly). Fee amounts in CNY: 0.01. Fees per lot: 1e-6.

**Format leniency.** Numbers may be strings (`"14.80"`, `"0.1%"` is read as 0.001); keys of value objects are matched
case-insensitively; extra keys are ignored; list order does not matter; `"unlimited"` is accepted for `"no_limit"`; task
ids may be lower case; the answers may sit under `"answers"` or at the top level. Missing facts and required context are
free text, mapped to the package's context keys by keywords (`grade.py`, `CONTEXT_PATTERNS`): the answer must name
every fact the expectation requires and may name more. Fill-log check kinds accept the package's own finding codes as
well as `band` / `tick` / `fee`. For the pre-flight task a gap's end may be given exclusive or inclusive (the day
before). For the two carry-forward tasks, declining with `beyond_tracking` is as correct as a flagged value.

## What each task expects

`TASKS.md` lists every task with its expected answer, the reason, and the library call it was derived from. In short:
two regime-change and rounding checks (T01, T02), a listing window that has no limit (T03), a dated fee change and a fee
floor (T04, T05), missing context (T06), an uncovered market (T07), a registered known gap (T08), a coverage pre-flight
that is not complete (T09), a fill log under the exchange's rules and one of model prices with slippage (T10, T11), a
date beyond the tracked-through date and an untracked market (T12, T13), and a futures fee that differs by contract
(T14).

## Self-check of the grader

`tests/test_evals.py` grades two reference files: an *oracle* written straight from `expected.json` (must be 14/14
correct, citation ok) and a *naive* file with the classic mistakes (ChiNext 20% before 2020-08-24, `round()` instead
of half-up, a number in the listing window, assumed context, guessed values for an uncovered market and a known gap,
unflagged carry-forwards, one fee for two contract tiers, a missed fee row, a strict check of model prices). The naive
file must grade `wrong` or `fabricated` on exactly those tasks and `correct` on the rest.

## After a data change

`python evals/build_expected.py` rewrites `expected.json` and `TASKS.md`; `--check` only reports whether they are
current. If a new release changes an expected answer, the diff of `expected.json` shows it; review it like any other
data change.

## Limits

- Fourteen tasks is a small sample: a single task flipping moves the score by 7 points. Treat a result as a list of
  observed behaviours, not a rate.
- One session does all tasks, so the assistant learns across tasks (a refusal it discovers in one task shapes the next).
  The order in `tasks.json` is fixed; a result is not comparable with a run on a reordered file.
- Results depend on the assistant, its version and settings, and on chance. Compare conditions on the same assistant,
  with repeated runs.
- The tasks state the facts a real caller would hold; they do not measure whether an assistant would fetch those facts
  correctly from market data, which is outside the package.
- The expected answers are the package's own answers. Where the package is wrong, the evaluation is wrong in the same
  way; the conformance vectors, not this evaluation, check the data against primary sources.
