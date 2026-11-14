"""Generate what the two wheels ship but the repository does not commit. Run before building either package.

    python scripts/vendor_data.py            # both
    python scripts/vendor_data.py --data     # only the marina-rules package content (the dataset)
    python scripts/vendor_data.py --code     # only SKILL.md into the marina-rules-core package (the code)

marina-rules (packages/marina-rules/): copies the forwarding module src/marina_rules/*.py into marina_rules/, data/ into
marina_rules/data/, and README.md, LICENSE and LICENSE-DATA beside the pyproject; checks that data/SCHEMA is the highest
``schema:`` of the data files; and writes data/compiled.json into the copy: the YAML loaders' output
(marina_rules_core._precompiled), so the installed dataset is not parsed on first use. Building it runs every load-time
check; invalid data stops the build here. The repository's data/ stays the only source: the copy is git-ignored and
must give the same dataset_digest() (the release workflow checks the installed wheel).

marina-rules-core (the repository root): copies SKILL.md into src/marina_rules_core/ (read by skill_text()). The code
wheel carries no data.
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
DATA_PKG = os.path.join(ROOT, "packages", "marina-rules")


def declared_schema_problem(data_dir: str):
    """None if data/SCHEMA equals the highest ``schema:`` among the data files, else the problem in words."""
    import yaml
    import marina_rules_core as mr
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
    """Write the marina-rules package content under ``out_pkg``; return the data directory written."""
    from marina_rules_core import _precompiled
    src, pkg = os.path.join(ROOT, "data"), os.path.join(out_pkg, "marina_rules")
    dst = os.path.join(pkg, "data")
    problem = declared_schema_problem(src)
    if problem:
        raise SystemExit(problem)
    if os.path.isdir(pkg):
        shutil.rmtree(pkg)
    shutil.copytree(os.path.join(ROOT, "src", "marina_rules"), pkg,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "data"))
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", _precompiled.FILE))
    for name in ("README.md", "LICENSE", "LICENSE-DATA"):
        shutil.copyfile(os.path.join(ROOT, name), os.path.join(out_pkg, name))
    n = sum(len(f) for _, _, f in os.walk(dst))
    print(f"vendored {n} files into {os.path.relpath(dst, ROOT)} and the module marina_rules beside them")
    # precompiled loader output, checked at run time against the YAML beside it and the loader revision that wrote it
    raw = _precompiled.build(dst)
    with open(os.path.join(dst, _precompiled.FILE), "wb") as fh:
        fh.write(raw)
    print(f"wrote {os.path.relpath(os.path.join(dst, _precompiled.FILE), ROOT)} ({len(raw)} bytes, "
          f"loader revision {_precompiled.LOADER_REVISION})")
    return dst


def vendor_skill() -> None:
    """The usage notes travel with the code wheel (skill_text()); a copy, never committed."""
    shutil.copyfile(os.path.join(ROOT, "SKILL.md"), os.path.join(ROOT, "src", "marina_rules_core", "SKILL.md"))
    print("vendored SKILL.md into src/marina_rules_core")


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
