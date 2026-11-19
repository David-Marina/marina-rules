"""examples/fixed_parameters.py: how often today's band and today's stamp duty disagree with the rule of the day."""
import importlib.util
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _mod():
    spec = importlib.util.spec_from_file_location("fixed_parameters", os.path.join(ROOT, "examples", "fixed_parameters.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sample_bars_chinext_before_the_2020_reform():
    fp = _mod()
    res = fp.count_bands(fixed_day="2026-11-16")
    assert res["files"] == 7 and list(res["groups"]) == ["chinext: 10% on the day, 20% fixed"]
    g = res["groups"]["chinext: 10% on the day, 20% fixed"]
    assert (g["bars"], g["from"], g["to"]) == (786, "2019-01-03", "2020-08-21")     # two ChiNext stocks in the sample
    assert len(g["limit_up_seen_as_free"]) == 7 and len(g["limit_down_seen_as_free"]) == 2
    assert ("sz.300001", "2019-03-11", 0.1002) in g["limit_up_seen_as_free"]
    assert g["real_move_seen_as_impossible"] == []
    assert all(day < "2020-08-24" for _, day, _ in g["limit_up_seen_as_free"] + g["limit_down_seen_as_free"])


def test_both_directions_on_written_bars(tmp_path):
    fp = _mod()
    (tmp_path / "sz.300999.csv").write_text(
        "date,close,preclose\n"
        "2020-08-18,10.00,10.00\n"      # first bar: skipped
        "2020-08-19,11.00,10.00\n"      # at the 10% limit of the day
        "2020-08-20,11.50,11.00\n"      # an ordinary day
        "2020-08-21,10.35,11.50\n"      # at limit-down
        "2020-08-24,11.90,10.35\n"      # +15%: allowed from this day on
        "2020-08-25,11.90,11.90\n", encoding="utf-8")
    wide = fp.count_bands(str(tmp_path), fixed_day="2026-11-16")
    g = wide["groups"]["chinext: 10% on the day, 20% fixed"]
    assert g["limit_up_seen_as_free"] == [("sz.300999", "2020-08-19", 0.1)]
    assert g["limit_down_seen_as_free"] == [("sz.300999", "2020-08-21", -0.1)]
    narrow = fp.count_bands(str(tmp_path), fixed_day="2020-08-21")      # a backtest written before the reform
    g = narrow["groups"]["chinext: 20% on the day, 10% fixed"]
    assert [d for _, d, _ in g["real_move_seen_as_impossible"]] == ["2020-08-24"]


def test_stamp_duty_gap_per_unit_of_turnover():
    fp = _mod()
    rows = fp.stamp_duty_gap(fixed_day="2026-11-16")
    assert rows[0][:5] == ("2008-09-19", "2021-11-15", 0.001, 0.0005, 0.0005)
    assert rows[-1][0] == "2023-08-28" and rows[-1][4] == 0
    assert all(diff >= 0 for *_, diff, _ in rows)


def test_script_runs(capsys):
    fp = _mod()
    assert fp.main(["fixed_parameters.py"]) == 0
    out = capsys.readouterr().out
    assert "closes at limit-up that the fixed band treats as an ordinary price:   7" in out
    assert "left out per 1x yearly sell turnover: 0.05% of the portfolio a year" in out


def test_readme_quotes_the_sample_count():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        text = " ".join(fh.read().split())
    assert "two ChiNext stocks, 786 trading days before 2020-08-24 — 7 closes were at limit-up and 2 at limit-down" in text
