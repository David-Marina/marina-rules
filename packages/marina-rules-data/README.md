# marina-rules-data

The dataset of [Marina](https://github.com/David-Marina/marina-rules): point-in-time trading rules for financial
markets — price limits, fees, sessions, ticks, settlement — as YAML, every record with the date it took effect and the
official source it was taken from.

This package holds data only. Read it with the `marina-rules` package, which depends on it:

```bash
pip install marina-rules              # installs marina-rules-data too
pip install -U marina-rules-data      # later: newer rules, same code
```

Versions are dates (`YYYY.MM.DD`, `YYYY.MM.DD.N`); a new one is released whenever the data changes (new or
corrected rules, or later tracking dates). `marina_rules_data.DATA_DIR` is the directory holding the YAML files,
`marina_rules_data.DATA_VERSION` the version and `marina_rules_data.SCHEMA` the data format; `marina_rules.citation()`
names the data version and digest it read, and the code version that read them.

Data: CC0 1.0. Generated from the repository's `data/` directory at release time; the repository is the only source.
