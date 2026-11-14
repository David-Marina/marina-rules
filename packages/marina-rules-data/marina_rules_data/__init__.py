"""marina-rules-data — the Marina dataset (point-in-time trading rules), packaged on its own.

Data only: the YAML records, scope registries, known gaps and tracking registries under :data:`DATA_DIR`, sample
files, and ``compiled.json`` (the loaders' output, so the first lookup does not parse YAML). Read it with the
``marina-rules`` package. ``DATA_VERSION`` is the dataset version (``data/VERSION``, also this distribution's
version); ``SCHEMA`` is the data format (``data/SCHEMA``: the highest ``schema:`` of any data file), which
``marina-rules`` checks before reading. This package imports nothing and depends on nothing.
"""
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _read(name: str) -> str:
    with open(os.path.join(DATA_DIR, name), encoding="ascii") as fh:
        return fh.read().strip()


DATA_VERSION = _read("VERSION")
SCHEMA = _read("SCHEMA")
__version__ = DATA_VERSION
