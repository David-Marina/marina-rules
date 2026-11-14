"""Two distributions, one repository: marina-rules (the code, semantic versions) and marina-rules-data (the dataset,
date versions, generated from data/ by scripts/vendor_data.py). These tests pin how the code finds the data, how the
two versions are named, how an incompatible pair is refused, and that the generated data package is what data/ is."""
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
from marina_rules import _precompiled as pc

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PKG = os.path.join(ROOT, "packages", "marina-rules-data")
DIGEST_2026_11_13 = "a66ca0e3fe8e3659f16b708d2af698d12ab85d3c34525bb2cf5632a8a9d8959e"


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
    assert mr.DATA_VERSION == _read("data", "VERSION").strip()
    assert re.match(r"^\d{4}\.\d{2}\.\d{2}(\.\d+)?$", mr.DATA_VERSION)
    assert re.match(r"^\d+\.\d+\.\d+$", mr.__version__)
    assert not hasattr(mr, "VERSION")   # one name meant two things; it is gone, not aliased


def test_pyprojects_agree_with_the_code():
    root = _read("pyproject.toml")
    assert re.search(r'^version = "(.+)"$', root, re.M).group(1) == mr.__version__
    assert f'"marina-rules-data>={mr.MIN_DATA_VERSION}"' in root
    assert "data/" not in root.split("[tool.setuptools.package-data]")[1]       # the code wheel carries no data
    data = _read("packages", "marina-rules-data", "pyproject.toml")
    assert 'name = "marina-rules-data"' in data and 'dynamic = ["version"]' in data
    assert 'version = {file = ["marina_rules_data/data/VERSION"]}' in data
    assert re.search(r"^dependencies = \[\]$", data, re.M)                       # the data depends on nothing


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


def test_digest_of_this_dataset_version_is_unchanged_by_the_split():
    # the split added data/VERSION and data/SCHEMA and changed no YAML: the 2026.11.13 data keeps its digest
    if mr.DATA_VERSION == "2026.11.13":
        assert mr.dataset_digest() == DIGEST_2026_11_13


def test_citation_names_data_version_digest_and_code_version():
    m = re.match(r"^rules: marina-rules-data@(\S+) sha256:([0-9a-f]{16}) code: marina-rules@(\S+)$", mr.citation())
    assert m and m.groups() == (mr.DATA_VERSION, mr.dataset_digest()[:16], mr.__version__)
    assert mr.citation(short=False).split()[2] == "sha256:" + mr.dataset_digest()


def test_decisions_and_capabilities_carry_the_data_version():
    from marina_rules.contract import resolve, capabilities
    d = resolve("stamp_duty_sell", "2023-08-28", "stock", "XSHG")
    assert d["ruleset_version"] == mr.DATA_VERSION and d["ruleset_hash"] == mr.dataset_digest()
    assert capabilities()["ruleset_version"] == mr.DATA_VERSION


# --- compatibility of data and code ----------------------------------------------------------------------------------

def _meta_dir(tmp_path, version="2026.11.13", schema="1.2"):
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
    with pytest.raises(mr.IncompatibleData, match=r"needs marina-rules-data .* or later.*pip install -U marina-rules-data"):
        mr._check_data(_meta_dir(tmp_path, "2026.01.01"))


def test_data_newer_than_the_code_reads_says_upgrade_the_code(tmp_path):
    with pytest.raises(mr.IncompatibleData, match=r"schema 1\.3.*newer than this code.*pip install -U marina-rules$"):
        mr._check_data(_meta_dir(tmp_path, "2099.01.01", "1.3"))
    with pytest.raises(mr.IncompatibleData, match=r"schema 2.*pip install -U marina-rules$"):
        mr._check_data(_meta_dir(tmp_path / "data", "2099.01.01", "2"))


@pytest.mark.parametrize("version, schema, match", [
    (None, "1.2", "no readable VERSION"), ("2026.11.13", None, "no readable SCHEMA"),
    ("2026-11-13", "1.2", "not a dataset version"), ("2026.11.13", "0.5", "Reinstall the data"),
    ("2026.11.13", "one", "Reinstall the data")])
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
    with pytest.raises(ValueError, match=r"unsupported or missing schema version: schema 1\.3 is newer.*-U marina-rules$"):
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
    """An installed-like layout: the code package alone in site/, the generated data package in pkg/."""
    base = tmp_path_factory.mktemp("layout")
    site, pkg = base / "site", base / "pkg"
    shutil.copytree(os.path.join(ROOT, "src", "marina_rules"), site / "marina_rules",
                    ignore=shutil.ignore_patterns("__pycache__", "data", "SKILL.md"))
    os.makedirs(pkg / "marina_rules_data")
    shutil.copyfile(os.path.join(DATA_PKG, "marina_rules_data", "__init__.py"), pkg / "marina_rules_data" / "__init__.py")
    vd = _load_script("vendor_data")
    data = vd.vendor_data(str(pkg))
    assert not os.path.exists(base / "data")   # nothing the code could take for a source checkout
    return {"site": str(site), "pkg": str(pkg), "data": data}


_PROBE = ("import json, marina_rules as mr; c = mr._compiled(); "
          "print(json.dumps({'dir': mr.DATA_DIR, 'version': mr.DATA_VERSION, 'digest': mr.dataset_digest(), "
          "'records': len(mr.records()), 'compiled': c is not None, 'citation': mr.citation()}))")


def _run(paths, code=_PROBE, block_data=False):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(paths))
    if block_data:
        code = "import sys; sys.modules['marina_rules_data'] = None\n" + code
    return subprocess.run([sys.executable, "-B", "-W", "error", "-c", code], capture_output=True, text=True, env=env,
                          cwd=os.path.dirname(paths[0]), timeout=300)


def test_generated_data_package_is_found_and_used_precompiled(layout):
    p = _run([layout["site"], layout["pkg"]])
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)
    assert got["dir"] == layout["data"] and got["version"] == mr.DATA_VERSION
    assert got["digest"] == mr.dataset_digest() and got["records"] == len(mr.records())
    assert got["compiled"] is True          # and no warning: -W error
    assert got["citation"] == mr.citation()
    with open(os.path.join(layout["pkg"], "LICENSE"), encoding="utf-8") as fh, \
            open(os.path.join(ROOT, "LICENSE-DATA"), encoding="utf-8") as ref:
        assert fh.read() == ref.read()


def test_code_without_data_says_what_to_install(layout):
    p = _run([layout["site"]], block_data=True)
    assert p.returncode != 0
    assert "DataNotInstalled" in p.stderr and "pip install marina-rules-data" in p.stderr


def test_upgrading_only_the_data_keeps_the_code_and_the_fast_path(layout, tmp_path):
    pkg = tmp_path / "pkg"
    shutil.copytree(layout["pkg"], pkg)
    data = pkg / "marina_rules_data" / "data"
    (data / "VERSION").write_text("2099.01.01\n", encoding="ascii")
    stale = _run([layout["site"], str(pkg)], code="import marina_rules as mr; mr.records()")
    assert stale.returncode != 0 and "dataset version" in stale.stderr     # the old compiled file names the old version
    (data / pc.FILE).write_bytes(pc.build(str(data)))
    p = _run([layout["site"], str(pkg)])
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)
    assert got["version"] == "2099.01.01" and got["compiled"] is True and got["digest"] == mr.dataset_digest()
    assert got["citation"].startswith("rules: marina-rules-data@2099.01.01 sha256:")


def test_installed_data_older_than_the_code_needs_is_refused_at_import(layout, tmp_path):
    pkg = tmp_path / "pkg"
    shutil.copytree(layout["pkg"], pkg)
    (pkg / "marina_rules_data" / "data" / "VERSION").write_text("2026.01.01\n", encoding="ascii")
    p = _run([layout["site"], str(pkg)])
    assert p.returncode != 0 and "IncompatibleData" in p.stderr and "pip install -U marina-rules-data" in p.stderr


def test_data_package_init_reads_its_own_metadata(layout):
    p = _run([layout["pkg"]], code="import marina_rules_data as d; print(d.DATA_VERSION, d.SCHEMA, d.__version__)")
    assert p.returncode == 0 and p.stdout.split() == [mr.DATA_VERSION, _read("data", "SCHEMA").strip(), mr.DATA_VERSION]


def test_vendored_data_is_byte_identical_to_the_repository(layout):
    def files(base):
        return {os.path.relpath(os.path.join(r, f), base): open(os.path.join(r, f), "rb").read()
                for r, _, fs in os.walk(base) for f in fs if "__pycache__" not in r}
    got, want = files(layout["data"]), files(os.path.join(ROOT, "data"))
    assert set(got) == set(want) | {pc.FILE}
    assert all(got[k] == want[k] for k in want)


def test_release_workflow_publishes_each_package_from_its_own_tag():
    with open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8") as fh:
        wf = yaml.safe_load(fh)
    on = wf.get("on", wf.get(True))       # YAML 1.1 reads the key `on` as True
    tags = on["push"]["tags"]
    assert "v[0-9]*.[0-9]*.[0-9]*" in tags and any(t.startswith("20[0-9][0-9]") for t in tags)
    jobs = wf["jobs"]
    assert (jobs["pypi-data"]["environment"], jobs["pypi-data"]["if"]) == ("pypi-data", "needs.build.outputs.kind == 'data'")
    assert (jobs["pypi"]["environment"], jobs["pypi"]["if"]) == ("pypi", "needs.build.outputs.kind == 'code'")
    steps = "\n".join(str(s.get("run", "")) for s in jobs["build"]["steps"])
    assert "python -m build packages/marina-rules-data" in steps and "scripts/vendor_data.py" in steps
    with open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as fh:
        ci = fh.read()
    assert "pip install ./packages/marina-rules-data" in ci and "VERSION)" not in ci.replace("data/VERSION)", "")
