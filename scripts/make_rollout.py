"""make_rollout.py — build the phased-rollout cumulative cashflow deliverable.

Writes two files for the top-ranked process (the one the model says to build
first), both drawn straight from the real ROI model so they can never drift from
the CLI:

    deliverables/rollout_cashflow.csv   month-by-month cumulative cashflow
    deliverables/rollout_cashflow.svg   hand-drawn cumulative cashflow curve

The curve lays the steady-state economics from `roi_model.compute` onto a monthly
timeline with a linear adoption ramp (`roi_model.rollout.phased_cashflow`), and
plots the ramped cashflow against the idealised (full-benefit-from-month-1) line
so the gap between them — the cost of a slow start — is visible at a glance.

The SVG is built by string templating — NO plotting library, no third-party
runtime dependency, matching the rest of the project (the browser charts are
hand-drawn too). Output is deterministic: fixed seed data, no timestamps, no
RNG, so re-running produces byte-identical files.

Run:
    python scripts/make_rollout.py

Honesty note: the linear ramp is an illustrative assumption, not a measured
adoption curve. It shows how sensitive payback is to a slow start; it does not
predict how a real rollout will ramp.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # so `roi_model` imports when run as a script

from roi_model import compute, load_processes, phased_cashflow, rank  # noqa: E402
from roi_model.rollout import DEFAULT_RAMP_MONTHS, RolloutResult  # noqa: E402

CSV_OUT = REPO / "deliverables" / "rollout_cashflow.csv"
SVG_OUT = REPO / "deliverables" / "rollout_cashflow.svg"

RAMP_MONTHS = DEFAULT_RAMP_MONTHS  # the deliverable illustrates the 6-month ramp

# Repo palette (shared with the other deliverables).
INK = "#1a2332"
ACCENT = "#1f6feb"       # ramped (realistic) curve
GOOD = "#1a7f4b"         # idealised (full-benefit) reference
MUTED = "#5b6672"
RULE = "#d0d7de"
SURFACE = "#ffffff"
RAMP_FILL = "#eef4fd"    # light shade over the ramp-up window
ATTENTION = "#b45309"    # the ramp-adjusted payback marker

# Chart geometry (px).
W = 940
PLOT_X0 = 96
PLOT_X1 = 828
PLOT_Y0 = 150
PLOT_H = 300
PLOT_Y1 = PLOT_Y0 + PLOT_H
HEIGHT = 560


def _top_process():
    """The process the model ranks first (highest 3-year net benefit)."""
    procs = load_processes()
    top_name = rank([compute(p) for p in procs], key="net_benefit_3y")[0].name
    return next(p for p in procs if p.name == top_name)


def _esc(text: str) -> str:
    """Escape the three characters that matter for SVG text content."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_csv(roll: RolloutResult, monthly_net_instant: float) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")  # byte-identical across OSes
        writer.writerow([
            "process", "ramp_months", "month", "realized_fraction",
            "monthly_net_ramped", "cumulative_net_ramped", "cumulative_net_instant",
        ])
        for cf in roll.schedule:
            cum_instant = round(-roll.build_cost + monthly_net_instant * cf.month, 2)
            writer.writerow([
                roll.name, roll.ramp_months, cf.month, f"{cf.realized_fraction:.6g}",
                f"{cf.monthly_net:.2f}", f"{cf.cumulative_net:.2f}", f"{cum_instant:.2f}",
            ])


def _nice_step(span: float) -> float:
    """A 1-2-5 'nice' tick step covering ~6 ticks across the value span."""
    raw = span / 6 if span > 0 else 1.0
    power = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 5, 10):
        if mult * power >= raw:
            return mult * power
    return 10 * power


def _fmt_k(value: float) -> str:
    """Money label in thousands of euros, e.g. 401457 -> '402k'."""
    return f"{value / 1000:,.0f}k"


def write_svg(roll: RolloutResult, monthly_net_instant: float) -> None:
    horizon = roll.horizon_months
    ramped = [-roll.build_cost] + [cf.cumulative_net for cf in roll.schedule]
    instant = [round(-roll.build_cost + monthly_net_instant * m, 2)
               for m in range(0, horizon + 1)]

    y_min = min(min(ramped), min(instant), 0.0)
    y_max = max(max(ramped), max(instant), 0.0)
    step = _nice_step(y_max - y_min)
    tick_lo = math.floor(y_min / step) * step
    tick_hi = math.ceil(y_max / step) * step
    lo, hi = tick_lo, tick_hi

    def x_of(month: float) -> float:
        return PLOT_X0 + month / horizon * (PLOT_X1 - PLOT_X0)

    def y_of(value: float) -> float:
        return PLOT_Y1 - (value - lo) / (hi - lo) * PLOT_H

    p: list[str] = []
    p.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{HEIGHT}" '
        f'viewBox="0 0 {W} {HEIGHT}" font-family="Segoe UI, Helvetica, Arial, sans-serif">'
    )
    p.append(f'<rect width="{W}" height="{HEIGHT}" fill="{SURFACE}"/>')

    # Header.
    p.append(f'<text x="28" y="44" font-size="21" font-weight="700" fill="{INK}">'
             f'Phased-rollout cumulative cashflow &#8212; {_esc(roll.name)}</text>')
    p.append(f'<text x="28" y="70" font-size="12.5" fill="{MUTED}">'
             f'Cumulative euros over {horizon} months with a linear {roll.ramp_months}-month '
             'adoption ramp, against the idealised full-benefit line.</text>')
    p.append(f'<text x="28" y="88" font-size="12.5" fill="{MUTED}">'
             'The automation pays the running cost in full from month 1 but earns the '
             'saving only as adoption climbs &#8212; so it turns cash-positive later.</text>')

    # Shade the ramp-up window (months 0..ramp_months).
    ramp_x = x_of(roll.ramp_months)
    p.append(f'<rect x="{PLOT_X0:.1f}" y="{PLOT_Y0}" width="{ramp_x - PLOT_X0:.1f}" '
             f'height="{PLOT_H}" fill="{RAMP_FILL}"/>')
    p.append(f'<text x="{(PLOT_X0 + ramp_x) / 2:.1f}" y="{PLOT_Y0 - 8}" font-size="10.5" '
             f'fill="{MUTED}" text-anchor="middle">ramp-up ({roll.ramp_months} mo)</text>')

    # Y gridlines + labels.
    ticks = []
    t = lo
    while t <= hi + 1e-6:
        ticks.append(t)
        t += step
    for tick in ticks:
        y = y_of(tick)
        p.append(f'<line x1="{PLOT_X0}" y1="{y:.1f}" x2="{PLOT_X1}" y2="{y:.1f}" '
                 f'stroke="{RULE}" stroke-width="1"/>')
        p.append(f'<text x="{PLOT_X0 - 8}" y="{y + 3.5:.1f}" font-size="10.5" '
                 f'fill="{MUTED}" text-anchor="end">{_fmt_k(tick)}</text>')

    # Zero (break-even) reference line, drawn a touch stronger.
    y_zero = y_of(0.0)
    p.append(f'<line x1="{PLOT_X0}" y1="{y_zero:.1f}" x2="{PLOT_X1}" y2="{y_zero:.1f}" '
             f'stroke="{INK}" stroke-width="1.3" stroke-dasharray="2 3"/>')
    p.append(f'<text x="{PLOT_X1 + 4}" y="{y_zero + 3.5:.1f}" font-size="10" '
             f'fill="{INK}">break-even</text>')

    # X axis ticks at each year end.
    for month in range(0, horizon + 1, 6):
        x = x_of(month)
        p.append(f'<line x1="{x:.1f}" y1="{PLOT_Y1}" x2="{x:.1f}" y2="{PLOT_Y1 + 5}" '
                 f'stroke="{MUTED}" stroke-width="1"/>')
        p.append(f'<text x="{x:.1f}" y="{PLOT_Y1 + 19}" font-size="10.5" fill="{MUTED}" '
                 f'text-anchor="middle">{month}</text>')
    p.append(f'<text x="{(PLOT_X0 + PLOT_X1) / 2:.1f}" y="{PLOT_Y1 + 38}" font-size="10.5" '
             f'fill="{MUTED}" text-anchor="middle" font-style="italic">month</text>')

    # Idealised (full-benefit) reference line.
    pts_instant = " ".join(f"{x_of(m):.1f},{y_of(instant[m]):.1f}" for m in range(horizon + 1))
    p.append(f'<polyline points="{pts_instant}" fill="none" stroke="{GOOD}" '
             'stroke-width="1.8" stroke-dasharray="5 4"/>')

    # Ramped (realistic) curve.
    pts_ramped = " ".join(f"{x_of(m):.1f},{y_of(ramped[m]):.1f}" for m in range(horizon + 1))
    p.append(f'<polyline points="{pts_ramped}" fill="none" stroke="{ACCENT}" '
             'stroke-width="2.4"/>')

    # Payback markers: idealised (fractional month) and ramp-adjusted (integer).
    if roll.instant_payback_months is not None:
        xi = x_of(min(roll.instant_payback_months, horizon))
        p.append(f'<circle cx="{xi:.1f}" cy="{y_zero:.1f}" r="3.5" fill="{GOOD}"/>')
        p.append(f'<text x="{xi:.1f}" y="{y_zero + 20:.1f}" font-size="10" fill="{GOOD}" '
                 f'text-anchor="middle">idealised {roll.instant_payback_months:.1f} mo</text>')
    if roll.ramp_payback_month is not None:
        xr = x_of(roll.ramp_payback_month)
        p.append(f'<line x1="{xr:.1f}" y1="{PLOT_Y0}" x2="{xr:.1f}" y2="{PLOT_Y1}" '
                 f'stroke="{ATTENTION}" stroke-width="1.2" stroke-dasharray="3 3"/>')
        p.append(f'<circle cx="{xr:.1f}" cy="{y_zero:.1f}" r="4" fill="{ATTENTION}"/>')
        p.append(f'<text x="{xr + 6:.1f}" y="{PLOT_Y0 + 14:.1f}" font-size="11" '
                 f'font-weight="700" fill="{ATTENTION}">pays back month '
                 f'{roll.ramp_payback_month}</text>')

    # Legend.
    ly = PLOT_Y0 + 6
    p.append(f'<line x1="{PLOT_X1 - 168}" y1="{ly}" x2="{PLOT_X1 - 140}" y2="{ly}" '
             f'stroke="{ACCENT}" stroke-width="2.4"/>')
    p.append(f'<text x="{PLOT_X1 - 134}" y="{ly + 4}" font-size="10.5" fill="{INK}">'
             'ramped (with ramp)</text>')
    p.append(f'<line x1="{PLOT_X1 - 168}" y1="{ly + 18}" x2="{PLOT_X1 - 140}" y2="{ly + 18}" '
             f'stroke="{GOOD}" stroke-width="1.8" stroke-dasharray="5 4"/>')
    p.append(f'<text x="{PLOT_X1 - 134}" y="{ly + 22}" font-size="10.5" fill="{INK}">'
             'idealised (instant)</text>')

    # Footer: the read + the honesty caveat.
    slip = "" if roll.payback_slip_months is None else f"{roll.payback_slip_months:,.1f}"
    read = (f"Read: a {roll.ramp_months}-month adoption ramp pushes payback to month "
            f"{roll.ramp_payback_month} (+{slip} mo vs the idealised "
            f"{roll.instant_payback_months:.1f}) and costs "
            f"{roll.ramp_cost_3y:,.0f} EUR of 3-year net benefit "
            f"({roll.net_benefit_3y_ramped:,.0f} ramped vs {roll.net_benefit_3y_instant:,.0f}).")
    p.append(f'<text x="28" y="{PLOT_Y1 + 66}" font-size="11.5" font-weight="600" '
             f'fill="{INK}">{_esc(read)}</text>')
    p.append(f'<text x="28" y="{PLOT_Y1 + 86}" font-size="10.5" fill="{MUTED}">'
             'The linear ramp is an illustrative assumption on synthetic data, not a measured '
             'adoption curve. Generated by the real ROI model &#8212; reproduce with '
             '`python -m roi_model --rollout`.</text>')

    p.append('</svg>')
    SVG_OUT.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" pins LF on every OS so the committed file is byte-identical.
    SVG_OUT.write_text("\n".join(p) + "\n", encoding="utf-8", newline="\n")


def build() -> None:
    proc = _top_process()
    base = compute(proc)
    monthly_net_instant = base.annual_net_saving / 12
    roll = phased_cashflow(proc, RAMP_MONTHS)
    write_csv(roll, monthly_net_instant)
    write_svg(roll, monthly_net_instant)
    print(f"Wrote {CSV_OUT.relative_to(REPO)}")
    print(f"Wrote {SVG_OUT.relative_to(REPO)}")


if __name__ == "__main__":
    build()
