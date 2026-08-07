"""test_model.py — unit tests for the ROI calculation model.

Run:
    pytest -q
"""

from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from roi_model import (
    break_even,
    compute,
    load_processes,
    phased_cashflow,
    rank,
    sensitivity,
    stress_band,
)
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


def test_ranking_by_name_is_alphabetical():
    procs = load_processes()
    results = rank([compute(p) for p in procs], key="name")
    names = [r.name for r in results]
    assert names == sorted(names)


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


def test_cli_portfolio_line_includes_fte_equivalent(capsys):
    main([])
    out = capsys.readouterr().out
    assert "FTE" in out
    assert "1,700 productive h/yr" in out


def test_cli_rejects_unknown_sort_field(capsys):
    code = main(["--sort", "bogus_key"])
    captured = capsys.readouterr()
    assert code == 2
    assert "unknown sort field 'bogus_key'" in captured.err
    assert "payback_months" in captured.err  # lists the valid fields
    assert "Traceback" not in captured.err


def test_cli_missing_input_csv_fails_cleanly(capsys):
    code = main(["--csv", "no_such_file.csv"])
    captured = capsys.readouterr()
    assert code == 2
    assert "not found" in captured.err
    assert "Traceback" not in captured.err


def test_cli_malformed_csv_fails_cleanly(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("name,annual_volume\nx,10\n", encoding="utf-8")
    code = main(["--csv", str(bad)])
    captured = capsys.readouterr()
    assert code == 2
    assert "missing columns" in captured.err
    assert "Traceback" not in captured.err


def test_finite_paybacks_are_positive_for_seed_data():
    for p in load_processes():
        r = compute(p)
        if r.payback_months is not None:
            assert r.payback_months > 0
            assert math.isfinite(r.payback_months)


# --- sensitivity ("what moves the number") -----------------------------------

def test_sensitivity_covers_every_driver_widest_first():
    rows = sensitivity(RFQ)
    assert len(rows) == 7
    swings = [row.swing_eur for row in rows]
    assert swings == sorted(swings, reverse=True)
    # Manual minutes swing widest for RFQ: +/-1.2 min moves the 5 saved
    # minutes by +/-24%, more than the +/-20% linear drivers.
    assert rows[0].field == "minutes_manual"


def test_sensitivity_coverage_row_matches_hand_math():
    # coverage 0.70 -> 0.56 / 0.84 at the default +/-20% swing:
    #   pessimistic: 26,880 tasks * 5 min / 60 = 2,240 h -> 71,680 gross
    #     -> 66,880 net -> 3y net benefit 66,880*3 - 25,000 = 175,640
    #   optimistic:  40,320 tasks -> 3,360 h -> 107,520 gross
    #     -> 102,720 net -> 3y net benefit 283,160
    row = next(r for r in sensitivity(RFQ) if r.field == "coverage")
    assert row.pessimistic_input == pytest.approx(0.56)
    assert row.optimistic_input == pytest.approx(0.84)
    assert row.pessimistic_net_3y == pytest.approx(175640, abs=1)
    assert row.optimistic_net_3y == pytest.approx(283160, abs=1)
    assert row.swing_eur == pytest.approx(107520, abs=1)


def test_sensitivity_pessimistic_never_beats_optimistic():
    for swing in (0.1, 0.2, 0.3):
        for row in sensitivity(RFQ, swing):
            assert row.pessimistic_net_3y <= row.optimistic_net_3y


def test_sensitivity_caps_optimistic_coverage_at_full():
    proc = ProcessInput("High coverage", 10000, 10, 1, 30, 0.9, 5000, 100)
    row = next(r for r in sensitivity(proc) if r.field == "coverage")
    assert row.optimistic_input == 1.0  # 0.9 * 1.2 would be 108%


def test_stress_band_brackets_base_and_every_one_way_row():
    worst, best = stress_band(RFQ)
    base = compute(RFQ)
    assert worst.net_benefit_3y < base.net_benefit_3y < best.net_benefit_3y
    for row in sensitivity(RFQ):
        assert worst.net_benefit_3y <= row.pessimistic_net_3y
        assert best.net_benefit_3y >= row.optimistic_net_3y


def test_stress_band_matches_hand_math():
    # Worst: 38,400 * 0.56 = 21,504 tasks * 3.6 min / 60 = 1,290.24 h
    #   * 25.6 EUR = 33,030.14 gross - 5,760 running = 27,270.14 net
    #   -> 3y net benefit 81,810.43 - 30,000 = 51,810.43
    worst, best = stress_band(RFQ)
    assert worst.net_benefit_3y == pytest.approx(51810.43, abs=0.5)
    assert best.net_benefit_3y == pytest.approx(563022.59, abs=0.5)
    assert worst.payback_months == pytest.approx(13.2, abs=0.05)
    assert best.payback_months == pytest.approx(1.23, abs=0.01)


def test_cli_sensitivity_report(capsys):
    code = main(["--sensitivity", "RFQ email triage"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Sensitivity - RFQ email triage" in out
    assert "+/-20%" in out
    assert "Manual min/task" in out
    assert "Stress band" in out
    assert "not a forecast" in out
    # Sensitivity mode replaces the backlog table.
    assert "Automation backlog" not in out


def test_cli_sensitivity_honors_swing(capsys):
    code = main(["--sensitivity", "RFQ email triage", "--swing", "30"])
    out = capsys.readouterr().out
    assert code == 0
    assert "+/-30%" in out


def test_cli_sensitivity_unknown_process_fails_cleanly(capsys):
    code = main(["--sensitivity", "No such process"])
    captured = capsys.readouterr()
    assert code == 2
    assert "unknown process 'No such process'" in captured.err
    assert "RFQ email triage" in captured.err  # lists the valid names
    assert "Traceback" not in captured.err


def test_cli_rejects_out_of_range_swing(capsys):
    code = main(["--sensitivity", "RFQ email triage", "--swing", "150"])
    captured = capsys.readouterr()
    assert code == 2
    assert "--swing" in captured.err
    assert "Traceback" not in captured.err


# --- break-even ("how far can each assumption move") --------------------------

def test_break_even_covers_every_driver_tightest_first():
    rows = break_even(RFQ)
    assert len(rows) == 7
    pcts = [r.margin_pct for r in rows if r.margin_pct is not None]
    assert pcts == sorted(pcts)  # tightest margin first
    # Manual minutes has the least headroom for RFQ (a 5-min gap, so a small
    # absolute change is a large relative one), so it is the most fragile.
    assert rows[0].field == "minutes_manual"


def test_break_even_build_cost_is_net_saving_over_horizon():
    # net_benefit_3y = net_saving*3 - build_cost, so it hits zero when the build
    # cost equals three years of net saving, independent of the current build.
    base = compute(RFQ)
    row = next(r for r in break_even(RFQ) if r.field == "build_cost")
    assert row.direction == "high"
    assert row.breakeven_value == pytest.approx(base.annual_net_saving * 3, abs=1)


def test_break_even_coverage_matches_hand_math():
    # net_benefit_3y = 384000*coverage - 39400  ->  zero at 39400/384000 = 0.1026
    row = next(r for r in break_even(RFQ) if r.field == "coverage")
    assert row.direction == "low"
    assert row.breakeven_value == pytest.approx(39400 / 384000, abs=1e-3)
    # headroom = (0.70 - 0.1026)/0.70 * 100
    assert row.margin_pct == pytest.approx((0.70 - 39400 / 384000) / 0.70 * 100, abs=0.1)


def test_break_even_value_zeroes_the_net_benefit():
    # The solver's contract, checked against compute() itself for every driver:
    # putting a driver at its break-even value drives 3y net benefit to ~0.
    for row in break_even(RFQ):
        if row.breakeven_value is None:
            continue
        r = compute(replace(RFQ, **{row.field: row.breakeven_value}))
        assert r.net_benefit_3y == pytest.approx(0.0, abs=1.0)


def test_break_even_margin_abs_matches_base_minus_breakeven():
    row = next(r for r in break_even(RFQ) if r.field == "monthly_cost")
    assert row.margin_abs == pytest.approx(abs(row.base_value - row.breakeven_value), abs=1e-6)


def test_break_even_is_deterministic():
    # No RNG, no wall-clock: identical inputs give identical break-even values.
    first = [(r.field, r.breakeven_value) for r in break_even(RFQ)]
    second = [(r.field, r.breakeven_value) for r in break_even(RFQ)]
    assert first == second


def test_break_even_unreachable_when_no_costs_to_overcome():
    # With no build or running cost, cutting volume/coverage only pushes the
    # net benefit down toward zero, never below it: no reachable break-even.
    proc = ProcessInput("Free to run", 10000, 10, 1, 30, 0.8, 0, 0)
    rows = {r.field: r for r in break_even(proc)}
    assert rows["coverage"].breakeven_value is None
    assert rows["coverage"].margin_pct is None


def test_cli_breakeven_report(capsys):
    code = main(["--breakeven", "RFQ email triage"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Break-even - RFQ email triage" in out
    assert "Manual min/task" in out
    assert "Headroom" in out
    assert "most fragile to" in out
    # Break-even mode replaces the backlog table.
    assert "Automation backlog" not in out


def test_cli_breakeven_unknown_process_fails_cleanly(capsys):
    code = main(["--breakeven", "No such process"])
    captured = capsys.readouterr()
    assert code == 2
    assert "unknown process 'No such process'" in captured.err
    assert "RFQ email triage" in captured.err  # lists the valid names
    assert "Traceback" not in captured.err


# --- phased rollout ("when does it really turn cash-positive") ----------------

def test_phased_cashflow_no_ramp_equals_instant_base_case():
    # ramp_months=1 = full benefit from month 1, so the ramped 3y net benefit and
    # NPV must exactly match the idealised base case, and the ramp costs nothing.
    base = compute(RFQ)
    roll = phased_cashflow(RFQ, ramp_months=1)
    assert roll.net_benefit_3y_ramped == pytest.approx(base.net_benefit_3y, abs=0.01)
    assert roll.npv_3y_ramped == pytest.approx(base.npv_3y, abs=0.01)
    assert roll.ramp_cost_3y == pytest.approx(0.0, abs=0.01)


def test_phased_cashflow_schedule_spans_the_full_horizon():
    roll = phased_cashflow(RFQ, ramp_months=6)
    assert len(roll.schedule) == 36           # 3 years, monthly
    assert roll.horizon_months == 36
    assert [m.month for m in roll.schedule] == list(range(1, 37))


def test_phased_cashflow_ramp_reaches_full_benefit_then_holds():
    ramp = 6
    roll = phased_cashflow(RFQ, ramp_months=ramp)
    for cf in roll.schedule:
        if cf.month < ramp:
            assert cf.realized_fraction < 1.0          # still ramping
        else:
            assert cf.realized_fraction == 1.0          # full from ramp end on
    # Linear: month k carries k/ramp of the benefit while ramping.
    assert roll.schedule[0].realized_fraction == pytest.approx(1 / ramp, abs=1e-6)


def test_phased_cashflow_cumulative_matches_hand_math():
    # RFQ, 6-month ramp: monthly gross 89,600/12 = 7,466.67, running 400/mo,
    # build 25,000. Month 1 realises 1/6 of the gross:
    #   844.44 net -> cumulative -24,155.56 ; full month is 7,066.67 net.
    roll = phased_cashflow(RFQ, ramp_months=6)
    m1 = roll.schedule[0]
    assert m1.realized_fraction == pytest.approx(1 / 6, abs=1e-6)
    assert m1.monthly_net == pytest.approx(844.44, abs=0.01)
    assert m1.cumulative_net == pytest.approx(-24155.56, abs=0.01)
    # The final cumulative is, by construction, the ramped 3-year net benefit.
    assert roll.schedule[-1].cumulative_net == pytest.approx(
        roll.net_benefit_3y_ramped, abs=0.01)


def test_phased_cashflow_ramp_delays_payback_and_costs_benefit():
    # A 6-month ramp pushes RFQ payback from ~3.5 (idealised) to month 7 and
    # trims 3-year net benefit by 18,666.67 (the gross forgone during the ramp;
    # running cost is paid in full either way).
    base = compute(RFQ)
    roll = phased_cashflow(RFQ, ramp_months=6)
    assert roll.ramp_payback_month == 7
    assert roll.instant_payback_months == base.payback_months
    assert roll.payback_slip_months == pytest.approx(7 - base.payback_months, abs=0.01)
    assert roll.ramp_cost_3y == pytest.approx(18666.67, abs=0.01)
    assert roll.net_benefit_3y_ramped == pytest.approx(210733.33, abs=0.01)


def test_phased_cashflow_ramp_payback_is_first_zero_crossing():
    roll = phased_cashflow(RFQ, ramp_months=6)
    pm = roll.ramp_payback_month
    assert pm is not None
    assert roll.schedule[pm - 1].cumulative_net >= 0        # crosses at pm
    assert roll.schedule[pm - 2].cumulative_net < 0         # still negative before


def test_phased_cashflow_never_beats_the_instant_case():
    # A ramp can only delay benefit, never bring it forward: the ramped figures
    # are always <= the idealised ones, across ramp lengths and seed processes.
    for proc in load_processes():
        for ramp in (1, 3, 6, 12):
            roll = phased_cashflow(proc, ramp_months=ramp)
            assert roll.net_benefit_3y_ramped <= roll.net_benefit_3y_instant + 1e-6
            assert roll.npv_3y_ramped <= roll.npv_3y_instant + 1e-6
            assert roll.ramp_cost_3y >= -1e-6
            if roll.ramp_payback_month is not None and roll.instant_payback_months:
                assert roll.ramp_payback_month >= roll.instant_payback_months - 1e-6


def test_phased_cashflow_no_payback_when_case_never_pays():
    # Running cost swamps the saving: the case never pays back with or without a
    # ramp, so both paybacks (and the slip) are undefined.
    loss = ProcessInput("Loss-making", 1000, 10, 1, 30, 1.0, 5000, 5000)
    roll = phased_cashflow(loss, ramp_months=6)
    assert roll.instant_payback_months is None
    assert roll.ramp_payback_month is None
    assert roll.payback_slip_months is None


def test_phased_cashflow_rejects_ramp_below_one():
    with pytest.raises(ValueError, match="ramp_months"):
        phased_cashflow(RFQ, ramp_months=0)


def test_phased_cashflow_is_deterministic():
    # No RNG, no wall-clock: identical inputs give identical schedules and totals.
    first = phased_cashflow(RFQ, ramp_months=6)
    second = phased_cashflow(RFQ, ramp_months=6)
    assert first.schedule == second.schedule
    assert first.net_benefit_3y_ramped == second.net_benefit_3y_ramped
    assert first.npv_3y_ramped == second.npv_3y_ramped


def test_cli_rollout_report(capsys):
    code = main(["--rollout", "Invoice matching (3-way)"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Phased rollout - Invoice matching (3-way)" in out
    assert "Ramp-adjusted payback" in out
    assert "Ramp cost over 3y" in out
    assert "pays back" in out
    assert "Cumulative" in out
    # Rollout mode replaces the backlog table.
    assert "Automation backlog" not in out


def test_cli_rollout_honors_ramp_months(capsys):
    code = main(["--rollout", "RFQ email triage", "--ramp-months", "12"])
    out = capsys.readouterr().out
    assert code == 0
    assert "over 12 months" in out


def test_cli_rollout_unknown_process_fails_cleanly(capsys):
    code = main(["--rollout", "No such process"])
    captured = capsys.readouterr()
    assert code == 2
    assert "unknown process 'No such process'" in captured.err
    assert "RFQ email triage" in captured.err  # lists the valid names
    assert "Traceback" not in captured.err


def test_cli_rejects_out_of_range_ramp_months(capsys):
    code = main(["--rollout", "RFQ email triage", "--ramp-months", "0"])
    captured = capsys.readouterr()
    assert code == 2
    assert "--ramp-months" in captured.err
    assert "Traceback" not in captured.err
