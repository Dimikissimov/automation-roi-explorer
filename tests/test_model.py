"""test_model.py — unit tests for the ROI calculation model.

Run:
    pytest -q
"""

from __future__ import annotations

import json
import math

import pytest

from roi_model import compute, load_processes, rank
from roi_model.cli import export_csv, export_json, main, render_table
from roi_model.model import ProcessInput

# A hand-computable fixture so the expected numbers can be checked by hand.
#   automated_volume = 48000 * 0.70          = 33600
#   minutes saved/task = 6 - 1               = 5
#   hours saved = 33600 * 5 / 60             = 2800
#   gross saving = 2800 * 32                 = 89600
#   running cost = 400 * 12                  = 4800
#   net saving   = 89600 - 4800             = 84800
#   payback mo   = 25000 / (84800/12)       = 3.538...
#   net benefit 3y = 84800*3 - 25000        = 229400
RFQ = ProcessInput(
    name="RFQ email triage",
    annual_volume=48000, minutes_manual=6, minutes_auto=1,
    hourly_wage=32, coverage=0.70, build_cost=25000, monthly_cost=400,
)


def test_hours_and_savings_are_exact():
    r = compute(RFQ)
    assert r.automated_volume == 33600
    assert r.annual_hours_saved == 2800.0
    assert r.annual_gross_saving == 89600.0
    assert r.annual_running_cost == 4800.0
    assert r.annual_net_saving == 84800.0


def test_payback_months():
    r = compute(RFQ)
    assert r.payback_months == pytest.approx(3.54, abs=0.01)


def test_net_benefit_and_roi():
    r = compute(RFQ)
    assert r.net_benefit_3y == 229400.0
    # total 3y cost = 25000 + 4800*3 = 39400 ; roi = 229400/39400*100
    assert r.roi_3y_pct == pytest.approx(582.23, abs=0.05)


def test_npv_discounts_future_savings():
    r = compute(RFQ)
    expected = -25000 + sum(84800 / (1.08 ** t) for t in (1, 2, 3))
    assert r.npv_3y == pytest.approx(expected, abs=0.5)
    # NPV must be below the undiscounted net benefit.
    assert r.npv_3y < r.net_benefit_3y


def test_zero_volume_is_a_loss_with_no_payback():
    proc = ProcessInput("Dead process", 0, 10, 1, 30, 0.8, 10000, 200)
    r = compute(proc)
    assert r.annual_hours_saved == 0.0
    assert r.annual_gross_saving == 0.0
    # Only running cost remains -> negative net saving, never pays back.
    assert r.annual_net_saving == -2400.0
    assert r.payback_months is None
    assert r.roi_3y_pct < 0


def test_negative_minutes_saved_is_clamped():
    # Automated slower than manual -> no time saved, not negative time.
    proc = ProcessInput("Worse-off", 1000, 2, 5, 30, 1.0, 1000, 0)
    r = compute(proc)
    assert r.annual_hours_saved == 0.0


def test_coverage_scales_volume():
    full = compute(ProcessInput("full", 1200, 10, 0, 30, 1.0, 0, 0))
    half = compute(ProcessInput("half", 1200, 10, 0, 30, 0.5, 0, 0))
    assert half.annual_hours_saved == pytest.approx(full.annual_hours_saved / 2, abs=0.01)


def test_ranking_orders_by_net_benefit_desc():
    procs = load_processes()
    results = rank([compute(p) for p in procs])
    values = [r.net_benefit_3y for r in results]
    assert values == sorted(values, reverse=True)


def test_ranking_by_payback_puts_fastest_first():
    procs = load_processes()
    results = rank([compute(p) for p in procs], key="payback_months")
    paybacks = [r.payback_months for r in results if r.payback_months is not None]
    assert paybacks == sorted(paybacks)


def test_ranking_pushes_never_payback_to_bottom():
    good = compute(ProcessInput("good", 10000, 10, 1, 30, 1.0, 5000, 100))
    bad = compute(ProcessInput("bad", 0, 10, 1, 30, 1.0, 5000, 100))
    ordered = rank([bad, good], key="payback_months")
    assert ordered[0].name == "good"
    assert ordered[-1].name == "bad"


def test_load_processes_reads_all_seed_rows():
    procs = load_processes()
    assert len(procs) == 5
    names = {p.name for p in procs}
    assert "RFQ email triage" in names
    assert "Supplier onboarding" in names


def test_load_processes_rejects_missing_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("name,annual_volume\nx,10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        load_processes(bad)


def test_as_row_is_json_serialisable():
    r = compute(RFQ)
    row = r.as_row()
    # Round-trips through JSON without error.
    assert json.loads(json.dumps(row))["name"] == "RFQ email triage"


def test_render_table_contains_processes_and_headers():
    results = rank([compute(p) for p in load_processes()])
    text = render_table(results)
    assert "Process" in text
    assert "3y ROI %" in text
    assert "RFQ email triage" in text


def test_export_json_and_csv_roundtrip(tmp_path):
    results = rank([compute(p) for p in load_processes()])

    jpath = tmp_path / "out.json"
    export_json(results, jpath)
    data = json.loads(jpath.read_text(encoding="utf-8"))
    assert len(data) == 5

    cpath = tmp_path / "out.csv"
    export_csv(results, cpath)
    lines = cpath.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 6  # header + 5 rows


def test_cli_main_runs_and_exports(tmp_path, capsys):
    jpath = tmp_path / "cli.json"
    code = main(["--export-json", str(jpath)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Automation backlog" in out
    assert jpath.exists()


def test_finite_paybacks_are_positive_for_seed_data():
    for p in load_processes():
        r = compute(p)
        if r.payback_months is not None:
            assert r.payback_months > 0
            assert math.isfinite(r.payback_months)
