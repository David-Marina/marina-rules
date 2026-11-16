# Answer format

Write one JSON file, `answers.json`:

```json
{
  "citation": "<the citation string the package gives for the dataset version you used>",
  "answers": {
    "T01": { "status": "determined", "value": {"2020-08-21": 1.23, "2020-08-24": 4.56}, "carry_forward": false },
    "T06": { "status": "needs_context", "missing_context": ["<fact 1>", "<fact 2>"] }
  }
}
```

`citation` is the package's own citation of the rules dataset (name, version and content hash), copied as the package
prints it. One citation for the whole file.

`answers` maps each task id to one object. Every task gets an entry. Keys an entry does not need may be left out.

## `status`: one of five words

| status | use it when | then also give |
|---|---|---|
| `determined` | you have the answer | `value`, `carry_forward` |
| `needs_context` | the answer depends on facts about the security or contract that the task does not give | `missing_context` |
| `not_covered` | the dataset has no rule for this market, product or date, and does not list it as a known gap | nothing else |
| `known_gap` | the dataset has no value here and lists the case as a known gap | `gap_ids` |
| `beyond_tracking` | you decline to give a value because it could only be carried forward past what was checked (see `carry_forward`) | nothing else |

## Fields

- `value`: what the task's "return" line asks for. Rates and percentages as fractions (`0.05` for 5%). Prices and amounts
  as numbers in CNY. Where the task asks for several values, an object with exactly the keys the task names. Where no
  price limit applies, the string `"no_limit"`. Only with status `determined`; with any other status leave it out or
  `null` (a value next to another status counts as giving a value).
- `carry_forward`: `true` when the value is **not confirmed for that date**: the dataset's sources for that market were
  checked for rule changes only up to an earlier date, or that market is not checked for changes at all, so the value is
  the last known rule carried forward. `false` otherwise. Give it with every `determined` answer.
- `missing_context`: a list of short names, one per missing fact about the security or contract (for example
  `"currency of the security"`).
- `gap_ids`: the identifiers of the known gaps the dataset gives (strings).

## Pre-flight task

Status `determined`; instead of `value`, give:

- `complete`: `true` if the dataset can answer every requested rule on every day of the window, else `false`;
- `gaps`: a list of `{"rule": "<rule name>", "from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}`, one per missing stretch, `to`
  exclusive (the first day that is covered again, or the window end);
- `gap_ids`: identifiers of the known gaps those stretches fall under (empty list if none);
- `required_context`: the facts about each security you must supply yourself to select the right rules.

## Fill-log tasks

Status `determined`. Rows are numbered from 1 = the first line after the CSV header.

- `violations`: a list of `{"row": <n>, "check": "<kind>"}`, one entry per row and kind of problem, where kind is one of
  `band` (price outside the day's price-limit band), `tick` (price not on the price tick in force), `fee` (fee below the
  statutory charges) or `other` (any other rule; say which in an extra key `note`). An empty list if every row is fine.
- `tolerated` (only where the task gives an allowance): the row numbers that are beyond a limit but within the
  allowance. These rows are not violations.

Extra keys anywhere are ignored, so you may add a short `note` to any answer.
