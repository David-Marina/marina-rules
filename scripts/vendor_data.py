"""Generate what the two wheels ship but the repository does not commit. Run before building either package.

    python scripts/vendor_data.py            # both
    python scripts/vendor_data.py --data     # only the marina-rules-data package content
    python scripts/vendor_data.py --code     # only SKILL.md into the marina-rules package

marina-rules-data (packages/marina-rules-data/): copies data/ into marina_rules_data/data/ and LICENSE-DATA into
LICENSE, checks that data/SCHEMA is the highest ``schema:`` of the data files, and writes data/compiled.json into the
copy: the YAML loaders' output (marina_rules._precompiled), so the installed dataset is not parsed on first use.
Building it runs every load-time check; invalid data stops the build here. The repository's data/ stays the only
source: the copy is git-ignored and must give the same dataset_digest() (the release workflow checks the installed
wheel).

marina-rules (the repository root): copies SKILL.md into src/marina_rules/ (read by marina_rules.skill_text()). The code
wheel carries no data; it depends on marina-rules-data.
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
DATA_PKG = os.path.join(ROOT, "packages", "marina-rules-data")


def declared_schema_problem(data_dir: str):
    """None if data/SCHEMA equals the highest ``schema:`` among the data files, else the problem in words."""
    import yaml
    import marina_rules as mr
    seen = []
    for root, _, files in os.walk(data_dir):
        for f in files:
            if f.endswith((".yaml", ".yml")):
                with open(os.path.join(root, f), encoding="utf-8") as fh:
                    seen.append((yaml.safe_load(fh) or {}).get("schema"))
    declared = mr._read_data_meta(data_dir, "SCHEMA")
    top = max((s for s in seen if isinstance(s, (int, float))), default=None)
    if top is None or float(declared) != float(top):
        return f"{data_dir}/SCHEMA says {declared}, the highest schema of the data files is {top}"
    return None


def vendor_data(out_pkg: str = DATA_PKG) -> str:
    """Write the data package content under ``out_pkg``; return the data directory written."""
    from marina_rules import _precompiled
    src, dst = os.path.join(ROOT, "data"), os.path.join(out_pkg, "marina_rules_data", "data")
    problem = declared_schema_problem(src)
    if problem:
        raise SystemExit(problem)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", _precompiled.FILE))
    shutil.copyfile(os.path.join(ROOT, "LICENSE-DATA"), os.path.join(out_pkg, "LICENSE"))
    n = sum(len(f) for _, _, f in os.walk(dst))
    print(f"vendored {n} files into {os.path.relpath(dst, ROOT)}")
    # precompiled loader output, checked at run time against the YAML beside it and the loader revision that wrote it
    raw = _precompiled.build(dst)
    with open(os.path.join(dst, _precompiled.FILE), "wb") as fh:
        fh.write(raw)
    print(f"wrote {os.path.relpath(os.path.join(dst, _precompiled.FILE), ROOT)} ({len(raw)} bytes, "
          f"loader revision {_precompiled.LOADER_REVISION})")
    return dst


def vendor_skill() -> None:
    """The usage notes travel with the code wheel (marina_rules.skill_text()); a copy, never committed."""
    shutil.copyfile(os.path.join(ROOT, "SKILL.md"), os.path.join(ROOT, "src", "marina_rules", "SKILL.md"))
    print("vendored SKILL.md into src/marina_rules")


def main(argv: list) -> int:
    want = set(argv) or {"--data", "--code"}
    if want - {"--data", "--code"}:
        print(__doc__.strip())
        return 2
    if "--data" in want:
        vendor_data()
    if "--code" in want:
        vendor_skill()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
