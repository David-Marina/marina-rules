"""Two distributions, one repository: marina-rules (the dataset and the module ``marina_rules``, date versions,
generated from data/ and src/marina_rules/ by scripts/vendor_data.py) and marina-rules-core (the code, the module
``marina_rules_core``, semantic versions). These tests pin how the code finds the data, how the two versions are
named, how an incompatible pair is refused, that ``marina_rules`` is ``marina_rules_core`` under its usual name, and
that the generated package is what data/ is."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

import pytest
import yaml

import marina_rules as mr
import marina_rules_core as core
from marina_rules_core import _precompiled as pc

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PYPROJECT = ("packages", "marina-rules", "pyproject.toml")
# the regular expression readers of the 2026.11.16 citation line use; the line must keep matching it
OLD_CITATION = re.compile(r"rules: marina-rules@(?P<v>[0-9A-Za-z.]+) sha256:(?P<h>[0-9a-f]{16})\b")


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


# --- versions --------------------------------------------------------------------------------------------------------

def test_data_version_lives_in_the_data():
    assert mr.DATA_VERSION == mr.VERSION == _read("data", "VERSION").strip()
    assert re.match(r"^\d{4}\.\d{2}\.\d{2}(\.\d+)?$", mr.VERSION)
    assert re.match(r"^\d+\.\d+\.\d+$", mr.__version__)
    assert "VERSION" in mr.__all__


def test_pyprojects_agree_with_the_code():
    root = _read("pyproject.toml")
    assert 'name = "marina-rules-core"' in root
    assert re.search(r'^version = "(.+)"$', root, re.M).group(1) == mr.__version__
    assert 'packages = ["marina_rules_core"]' in root
    assert "data/" not in root.split("[tool.setuptools.package-data]")[1]       # the code wheel carries no data
    assert "[project.scripts]" not in root and "marina-rules-data" not in root and "marina-rules>=" not in root
    data = _read(*DATA_PYPROJECT)
    assert 'name = "marina-rules"' in data and 'dynamic = ["version"]' in data
    assert 'version = {file = ["marina_rules/data/VERSION"]}' in data
    assert 'packages = ["marina_rules"]' in data
    lo, hi = re.search(r'^dependencies = \["marina-rules-core>=([0-9.]+),<([0-9.]+)"\]$', data, re.M).groups()
    v = tuple(int(x) for x in mr.__version__.split("."))
    assert tuple(int(x) for x in lo.split(".")) <= v < tuple(int(x) for x in hi.split("."))
    assert 'marina-check = "marina_rules.check:main"' in data and 'marina-rules = "marina_rules.cli:main"' in data


def test_the_module_marina_rules_belongs_to_the_marina_rules_distribution():
    # Up to 2026.11.16 the wheel of marina-rules held the code in marina_rules/. `pip install -U marina-rules` installs
    # the new dependency first and then removes the old version's files by its RECORD: a module moved from
    # marina-rules into marina-rules-core would be deleted right after being installed, and so would the commands.
    # So marina_rules/ and the commands stay in marina-rules, and marina-rules-core ships only marina_rules_core/.
    root, data = _read("pyproject.toml"), _read(*DATA_PYPROJECT)
    assert re.search(r'^packages = \["marina_rules"\]$', data, re.M)
    assert re.search(r'^packages = \["marina_rules_core"\]$', root, re.M)
    assert "[project.scripts]" in data and "[project.scripts]" not in root


def test_declared_schema_is_the_highest_schema_of_the_data_files():
    vd = _load_script("vendor_data")
    assert vd.declared_schema_problem(os.path.join(ROOT, "data")) is None
    assert float(_read("data", "SCHEMA")) in mr.DATA_SCHEMAS


def test_metadata_files_are_outside_the_digest(tmp_path):
    d = str(tmp_path / "data")
    shutil.copytree(mr.DATA_DIR, d)
    before = mr._digest_dir(d)
    assert before == mr.dataset_digest()
    for name, text in (("VERSION", "2099.12.31\n"), ("SCHEMA", "1.1\n"), (pc.FILE, "{}\n")):
        with open(os.path.join(d, name), "w", encoding="ascii") as fh:
            fh.write(text)
    assert mr._digest_dir(d) == before
    os.remove(os.path.join(d, "VERSION"))
    os.remove(os.path.join(d, "SCHEMA"))
    assert mr._digest_dir(d) == before


def test_citation_names_data_version_digest_and_code_version():
    m = re.match(r"^rules: marina-rules@(\S+) sha256:([0-9a-f]{16}) code: marina-rules-core@(\S+)$", mr.citation())
    assert m and m.groups() == (mr.VERSION, mr.dataset_digest()[:16], mr.__version__)
    assert mr.citation(short=False).split()[2] == "sha256:" + mr.dataset_digest()


def test_citation_still_matches_the_single_package_pattern():
    m = OLD_CITATION.search(mr.citation())
    assert m and (m.group("v"), m.group("h")) == (mr.VERSION, mr.dataset_digest()[:16])


def test_decisions_and_capabilities_carry_the_data_version():
    from marina_rules.contract import resolve, capabilities
    d = resolve("stamp_duty_sell", "2023-08-28", "stock", "XSHG")
    assert d["ruleset_version"] == mr.VERSION and d["ruleset_hash"] == mr.dataset_digest()
    assert capabilities()["ruleset_version"] == mr.VERSION


# --- marina_rules is marina_rules_core -------------------------------------------------------------------------------

def _core_modules():
    here = os.path.join(ROOT, "src", "marina_rules_core")
    return sorted(f[:-3] for f in os.listdir(here) if f.endswith(".py") and f != "__init__.py")


def test_every_code_module_has_a_forwarding_module():
    fwd = os.path.join(ROOT, "src", "marina_rules")
    assert sorted(f[:-3] for f in os.listdir(fwd) if f.endswith(".py") and f != "__init__.py") == _core_modules()


@pytest.mark.parametrize("name", [m for m in _core_modules() if m != "__main__"])
def test_submodules_are_the_same_module_objects(name):
    a = importlib.import_module(f"marina_rules.{name}")
    assert a is importlib.import_module(f"marina_rules_core.{name}") and getattr(mr, name) is a


def test_attributes_are_read_from_and_written_to_the_code(monkeypatch):
    assert mr.rule_at is core.rule_at and mr.Record is core.Record and mr.__version__ == core.__version__
    assert mr.__all__ == core.__all__ and set(core.__all__) <= set(dir(mr))
    monkeypatch.setattr(mr, "DATA_DIR", "/nowhere")
    assert core.DATA_DIR == "/nowhere"
    monkeypatch.undo()
    assert core.DATA_DIR == mr.DATA_DIR == os.path.join(ROOT, "data")
    from marina_rules import citation, IncompatibleData     # noqa: F401  (from-imports go through the forwarding)
    assert citation is core.citation


def test_python_dash_m_runs_the_code():
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    for args in (["-m", "marina_rules", "version"], ["-m", "marina_rules.contract", "--schema"]):
        p = subprocess.run([sys.executable, "-B", "-W", "error", *args], capture_output=True, text=True, env=env,
                           cwd=ROOT, timeout=300)
        assert p.returncode == 0, p.stderr
    assert p.stdout.lstrip().startswith("{")


# --- compatibility of data and code ----------------------------------------------------------------------------------

def _meta_dir(tmp_path, version="2026.11.16", schema="1.2"):
    d = tmp_path / "data"
    d.mkdir(parents=True)
    if version is not None:
        (d / "VERSION").write_text(version + "\n", encoding="ascii")
    if schema is not None:
        (d / "SCHEMA").write_text(schema + "\n", encoding="ascii")
    return str(d)


def test_compatible_data_is_accepted(tmp_path):
    assert mr._check_data(_meta_dir(tmp_path, mr.MIN_DATA_VERSION, "1.2")) == mr.MIN_DATA_VERSION


@pytest.mark.parametrize("version", ["2099.01.01", "2099.01.01.3"])
def test_newer_data_with_a_known_schema_is_accepted(tmp_path, version):
    assert mr._check_data(_meta_dir(tmp_path, version, "1.1")) == version


def test_data_older_than_the_code_needs_says_upgrade_the_data(tmp_path):
    with pytest.raises(mr.IncompatibleData, match=r"needs the dataset marina-rules .* or later.*pip install -U marina-rules$"):
        mr._check_data(_meta_dir(tmp_path, "2026.01.01"))


def test_data_newer_than_the_code_reads_says_upgrade_the_code(tmp_path):
    with pytest.raises(mr.IncompatibleData, match=r"schema 1\.3.*newer than this code.*pip install -U marina-rules-core$"):
        mr._check_data(_meta_dir(tmp_path, "2099.01.01", "1.3"))
    with pytest.raises(mr.IncompatibleData, match=r"schema 2.*pip install -U marina-rules-core$"):
        mr._check_data(_meta_dir(tmp_path / "data", "2099.01.01", "2"))


@pytest.mark.parametrize("version, schema, match", [
    (None, "1.2", "no VERSION file: it is a marina-rules release from before"),
    ("2026.11.16", None, "no SCHEMA file"),
    ("2026-11-16", "1.2", "not a dataset version"), ("2026.11.16", "0.5", "Reinstall the data"),
    ("2026.11.16", "one", "Reinstall the data")])
def test_unreadable_metadata_is_refused(tmp_path, version, schema, match):
    with pytest.raises(mr.IncompatibleData, match=match):
        mr._check_data(_meta_dir(tmp_path, version, schema))


def test_incompatibility_errors_are_import_errors():
    assert issubclass(mr.IncompatibleData, ImportError) and issubclass(mr.DataNotInstalled, ImportError)


def test_a_data_file_in_a_newer_schema_says_upgrade_the_code(tmp_path, monkeypatch):
    d = tmp_path / "data" / "us"
    d.mkdir(parents=True)
    with open(d / "x.yaml", "w", encoding="utf-8") as fh:
        yaml.safe_dump({"schema": 1.3, "records": []}, fh)
    with pytest.raises(ValueError, match=r"unsupported or missing schema version: schema 1\.3 is newer.*-U marina-rules-core$"):
        mr._records_from_yaml(str(tmp_path / "data"))
    with open(d / "x.yaml", "w", encoding="utf-8") as fh:
        yaml.safe_dump({"schema": 0.9, "records": []}, fh)
    with pytest.raises(ValueError, match=r"unsupported or missing schema version$"):
        mr._records_from_yaml(str(tmp_path / "data"))


# --- where the data is found -----------------------------------------------------------------------------------------

def test_source_checkout_reads_the_repository_data():
    assert mr.DATA_DIR == os.path.join(ROOT, "data")


@pytest.fixture(scope="module")
def layout(tmp_path_factory):
    """An installed-like layout: the code alone in site/ (marina_rules_core), the generated marina-rules package
    (marina_rules/ with data/) in pkg/."""
    base = tmp_path_factory.mktemp("layout")
    site, pkg = base / "site", base / "pkg"
    shutil.copytree(os.path.join(ROOT, "src", "marina_rules_core"), site / "marina_rules_core",
                    ignore=shutil.ignore_patterns("__pycache__", "SKILL.md"))
    vd = _load_script("vendor_data")
    data = vd.vendor_data(str(pkg))
    assert not os.path.exists(base / "data")   # nothing the code could take for a source checkout
    return {"site": str(site), "pkg": str(pkg), "data": data}


_PROBE = ("import json, marina_rules as mr; c = mr._compiled(); "
          "print(json.dumps({'dir': mr.DATA_DIR, 'version': mr.VERSION, 'digest': mr.dataset_digest(), "
          "'records': len(mr.records()), 'compiled': c is not None, 'citation': mr.citation(), "
          "'core': mr.__version__}))")


def _run(paths, code=_PROBE):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(paths))
    return subprocess.run([sys.executable, "-B", "-W", "error", "-c", code], capture_output=True, text=True, env=env,
                          cwd=os.path.dirname(paths[0]), timeout=300)


def test_generated_package_is_found_and_used_precompiled(layout):
    p = _run([layout["site"], layout["pkg"]])
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)
    assert got["dir"] == layout["data"] and got["version"] == mr.VERSION and got["core"] == mr.__version__
    assert got["digest"] == mr.dataset_digest() and got["records"] == len(mr.records())
    assert got["compiled"] is True          # and no warning: -W error
    assert got["citation"] == mr.citation()
    for name, ref in (("LICENSE", "LICENSE"), ("LICENSE-DATA", "LICENSE-DATA"), ("README.md", "README.md")):
        with open(os.path.join(layout["pkg"], name), encoding="utf-8") as fh:
            assert fh.read() == _read(ref)


def test_code_without_data_says_what_to_install(layout):
    p = _run([layout["site"]], code="import marina_rules_core")
    assert p.returncode != 0
    assert "DataNotInstalled" in p.stderr and "pip install marina-rules\n" in p.stderr + "\n"


def test_data_without_code_says_what_to_install(layout):
    p = _run([layout["pkg"]], code="import marina_rules")
    assert p.returncode != 0
    assert "ImportError" in p.stderr and "pip install marina-rules-core" in p.stderr


def test_a_marina_rules_from_before_the_split_is_named(layout, tmp_path):
    pkg = tmp_path / "pkg"
    shutil.copytree(layout["pkg"], pkg)
    os.remove(pkg / "marina_rules" / "data" / "VERSION")
    p = _run([layout["site"], str(pkg)], code="import marina_rules_core")
    assert p.returncode != 0 and "IncompatibleData" in p.stderr
    assert "before the code and the data were split" in p.stderr and "pip install -U marina-rules" in p.stderr


def test_upgrading_only_the_data_keeps_the_code_and_the_fast_path(layout, tmp_path):
    pkg = tmp_path / "pkg"
    shutil.copytree(layout["pkg"], pkg)
    data = pkg / "marina_rules" / "data"
    (data / "VERSION").write_text("2099.01.01\n", encoding="ascii")
    stale = _run([layout["site"], str(pkg)], code="import marina_rules as mr; mr.records()")
    assert stale.returncode != 0 and "dataset version" in stale.stderr     # the old compiled file names the old version
    (data / pc.FILE).write_bytes(pc.build(str(data)))
    p = _run([layout["site"], str(pkg)])
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)
    assert got["version"] == "2099.01.01" and got["compiled"] is True and got["digest"] == mr.dataset_digest()
    assert got["citation"].startswith("rules: marina-rules@2099.01.01 sha256:")
    assert got["citation"].endswith(f" code: marina-rules-core@{mr.__version__}")


def test_installed_data_older_than_the_code_needs_is_refused_at_import(layout, tmp_path):
    pkg = tmp_path / "pkg"
    shutil.copytree(layout["pkg"], pkg)
    (pkg / "marina_rules" / "data" / "VERSION").write_text("2026.01.01\n", encoding="ascii")
    p = _run([layout["site"], str(pkg)])
    assert p.returncode != 0 and "IncompatibleData" in p.stderr and "pip install -U marina-rules\n" in p.stderr + "\n"


def test_vendored_package_is_byte_identical_to_the_repository(layout):
    def files(base):
        return {os.path.relpath(os.path.join(r, f), base): open(os.path.join(r, f), "rb").read()
                for r, _, fs in os.walk(base) for f in fs if "__pycache__" not in r}
    got, want = files(layout["data"]), files(os.path.join(ROOT, "data"))
    assert set(got) == set(want) | {pc.FILE}
    assert all(got[k] == want[k] for k in want)
    fwd = files(os.path.join(layout["pkg"], "marina_rules"))
    src = files(os.path.join(ROOT, "src", "marina_rules"))
    assert {k: v for k, v in fwd.items() if not k.startswith("data" + os.sep)} == src


def test_release_workflow_publishes_each_package_from_its_own_tag():
    with open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8") as fh:
        wf = yaml.safe_load(fh)
    on = wf.get("on", wf.get(True))       # YAML 1.1 reads the key `on` as True
    tags = on["push"]["tags"]
    assert "core-v[0-9]*.[0-9]*.[0-9]*" in tags and any(t.startswith("20[0-9][0-9]") for t in tags)
    assert not any(t.startswith("v") for t in tags)
    jobs = wf["jobs"]
    assert (jobs["pypi"]["environment"], jobs["pypi"]["if"]) == ("pypi", "needs.build.outputs.kind == 'data'")
    assert (jobs["pypi-core"]["environment"], jobs["pypi-core"]["if"]) == ("pypi-core", "needs.build.outputs.kind == 'code'")
    assert "marina[-_]rules-[0-9]" in str(jobs["pypi"]["steps"]) and "marina[-_]rules[-_]core-" in str(jobs["pypi-core"]["steps"])
    steps = "\n".join(str(s.get("run", "")) for s in jobs["build"]["steps"])
    assert "python -m build packages/marina-rules " in steps and "scripts/vendor_data.py" in steps
    with open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as fh:
        ci = fh.read()
    assert ci.index("pip install -e .") < ci.index("pip install ./packages/marina-rules")   # the code first
