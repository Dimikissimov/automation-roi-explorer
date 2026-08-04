"""cli.py — command-line front end for the ROI model.

Prints a ranked automation backlog and, optionally, exports the full
results to CSV or JSON.

Usage:
    python -m roi_model                     # ranked table from the seed data
    python -m roi_model --csv data.csv      # rank a different input CSV
    python -m roi_model --sort payback_months
    python -m roi_model --export-json out.json
    python -m roi_model --export-csv out.csv
    python -m roi_model --sensitivity "RFQ email triage"            # tornado, +/-20%
    python -m roi_model --sensitivity "RFQ email triage" --swing 30
    python -m roi_model --breakeven "RFQ email triage"             # margin of safety
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import fields as dataclass_fields
from pathlib import Path

from roi_model.breakeven import break_even
from roi_model.data_load import load_processes
from roi_model.model import (
    FTE_HOURS_PER_YEAR,
    ProcessInput,
    ProcessResult,
    compute,
    rank,
    sensitivity,
    stress_band,
)

# Fields the --sort flag accepts (every column on ProcessResult).
VALID_SORT_FIELDS = tuple(f.name for f in dataclass_fields(ProcessResult))

# Human-readable driver names for the sensitivity report.
_DRIVER_LABELS = {
    "annual_volume": "Annual volume",
    "minutes_manual": "Manual min/task",
    "minutes_auto": "Automated min/task",
    "hourly_wage": "Hourly wage",
    "coverage": "Coverage",
    "build_cost": "Build cost",
    "monthly_cost": "Monthly cost",
}

# Columns shown in the printed backlog and their display headers.
_TABLE_COLUMNS = (
    ("name", "Process", 26, "<"),
    ("annual_hours_saved", "Hrs/yr", 10, ">"),
    ("annual_net_saving", "Net EUR/yr", 12, ">"),
    ("payback_months", "Payback mo", 11, ">"),
    ("roi_3y_pct", "3y ROI %", 10, ">"),
    ("npv_3y", "NPV 3y", 12, ">"),
)


def _fmt(value, field: str) -> str:
    """Format a single cell for the text table."""
    if value is None:
        return "never"
    if field in ("annual_net_saving", "npv_3y"):
        return f"{value:,.0f}"
    if field == "annual_hours_saved":
        return f"{value:,.0f}"
    if isinstance(value, float):
        return f"{value:,.1f}"
    return str(value)


def render_table(results: list[ProcessResult]) -> str:
    """Render ranked results as a fixed-width text table."""
    lines: list[str] = []

    header = "  ".join(
        f"{title:{align}{width}}" for _, title, width, align in _TABLE_COLUMNS
    )
    lines.append(header)
    lines.append("-" * len(header))

    for r in results:
        row = r.as_row()
        cells = []
        for field, _title, width, align in _TABLE_COLUMNS:
            text = _fmt(row[field], field)
            cells.append(f"{text:{align}{width}}")
        lines.append("  ".join(cells))

    return "\n".join(lines)


def export_json(results: list[ProcessResult], path: Path) -> None:
    """Write results as a JSON array of objects."""
    path.write_text(
        json.dumps([r.as_row() for r in results], indent=2),
        encoding="utf-8",
    )


def export_csv(results: list[ProcessResult], path: Path) -> None:
    """Write results as CSV with one row per process."""
    rows = [r.as_row() for r in results]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _fmt_input(field: str, value: float) -> str:
    """Format a driver value for the sensitivity table (coverage as %)."""
    if field == "coverage":
        return f"{value * 100:,.0f}%"
    text = f"{value:,.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _fmt_payback(months: float | None) -> str:
    """Payback with its unit, or 'never'."""
    return "never" if months is None else f"{months:,.1f} mo"


def render_sensitivity_report(proc: ProcessInput, swing: float) -> str:
    """Render the one-way tornado + stress band for one process (ASCII only)."""
    base = compute(proc)
    rows = sensitivity(proc, swing)
    worst, best = stress_band(proc, swing)
    pct = f"{swing * 100:,.0f}"

    lines: list[str] = []
    lines.append(f"Sensitivity - {proc.name} (one driver at a time, +/-{pct}%)")
    lines.append(f"Base: 3y net benefit {base.net_benefit_3y:,.0f} EUR, "
                 f"payback {_fmt_payback(base.payback_months)}\n")

    header = (f"{'Driver':<20}  {'Pessimistic':>12}  {'Optimistic':>12}  "
              f"{'3y net benefit range (EUR)':>28}  {'Swing':>12}")
    lines.append(header)
    lines.append("-" * len(header))
    for row in rows:
        span = f"{row.pessimistic_net_3y:,.0f} .. {row.optimistic_net_3y:,.0f}"
        lines.append(
            f"{_DRIVER_LABELS[row.field]:<20}  "
            f"{_fmt_input(row.field, row.pessimistic_input):>12}  "
            f"{_fmt_input(row.field, row.optimistic_input):>12}  "
            f"{span:>28}  {row.swing_eur:>12,.0f}"
        )

    lines.append("\nStress band - every driver at its bad/good end at once "
                 "(bounds, not a forecast):")
    lines.append(f"3y net benefit {worst.net_benefit_3y:,.0f} .. "
                 f"{best.net_benefit_3y:,.0f} EUR - "
                 f"payback {_fmt_payback(worst.payback_months)} .. "
                 f"{_fmt_payback(best.payback_months)}")
    return "\n".join(lines)


def render_breakeven_report(proc: ProcessInput) -> str:
    """Render the per-driver break-even / margin-of-safety table (ASCII only).

    Shows, for each driver, how far it can move from the base assumption before
    the 3-year net benefit hits zero, ranked tightest headroom first, and ends
    with the one-line read of which assumption the case is most fragile to.
    """
    base = compute(proc)
    rows = break_even(proc)

    lines: list[str] = []
    lines.append(f"Break-even - {proc.name} "
                 "(how far each assumption can move before the 3y case stops paying)")
    lines.append(f"Base: 3y net benefit {base.net_benefit_3y:,.0f} EUR, "
                 f"payback {_fmt_payback(base.payback_months)}\n")

    header = (f"{'Driver':<20}  {'Base':>12}  {'Break-even':>12}  "
              f"{'Can move':>10}  {'Headroom':>16}")
    lines.append(header)
    lines.append("-" * len(header))
    for row in rows:
        base_txt = _fmt_input(row.field, row.base_value)
        if row.breakeven_value is None:
            lines.append(
                f"{_DRIVER_LABELS[row.field]:<20}  {base_txt:>12}  "
                f"{'none':>12}  {'--':>10}  {'no break-even':>16}"
            )
            continue
        be_txt = _fmt_input(row.field, row.breakeven_value)
        move = "down to" if row.direction == "low" else "up to"
        verb = "drop" if row.direction == "low" else "rise"
        headroom = f"{row.margin_pct:,.0f}% {verb}"
        lines.append(
            f"{_DRIVER_LABELS[row.field]:<20}  {base_txt:>12}  "
            f"{be_txt:>12}  {move:>10}  {headroom:>16}"
        )

    reachable = [r for r in rows if r.breakeven_value is not None]
    lines.append("")
    if base.net_benefit_3y <= 0:
        lines.append("Read: the base case does not pay back, so there is no "
                     "deterioration margin to report.")
    elif reachable:
        tightest = reachable[0]
        move = "falls to" if tightest.direction == "low" else "rises to"
        verb = "drop" if tightest.direction == "low" else "rise"
        be_val = _fmt_input(tightest.field, tightest.breakeven_value)
        base_val = _fmt_input(tightest.field, tightest.base_value)
        lines.append(
            f"Read: most fragile to {_DRIVER_LABELS[tightest.field]} - the 3y case "
            f"breaks even when it {move} {be_val} "
            f"(a {tightest.margin_pct:,.0f}% {verb} from {base_val}). "
            "Beyond that the automation stops paying back over 3 years."
        )
    lines.append("Margins are tolerances on your own assumptions, not "
                 "probabilities - they show how much room the estimate has, "
                 "not how likely a shortfall is.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser (kept separate so tests can reuse it)."""
    parser = argparse.ArgumentParser(
        prog="python -m roi_model",
        description="Rank back-office processes by the value of automating them.",
    )
    parser.add_argument("--csv", type=Path, default=None,
                        help="Input CSV of candidate processes (defaults to seed data).")
    parser.add_argument("--sort", default="net_benefit_3y",
                        help="Field to rank by (default: net_benefit_3y).")
    parser.add_argument("--export-json", type=Path, default=None,
                        help="Also write full results to this JSON file.")
    parser.add_argument("--export-csv", type=Path, default=None,
                        help="Also write full results to this CSV file.")
    parser.add_argument("--sensitivity", metavar="PROCESS", default=None,
                        help="Print a one-way (tornado) sensitivity report for the "
                             "named process instead of the backlog table.")
    parser.add_argument("--swing", type=float, default=20.0,
                        help="Sensitivity swing per driver, in percent (default: 20).")
    parser.add_argument("--breakeven", metavar="PROCESS", default=None,
                        help="Print a break-even / margin-of-safety report for the "
                             "named process: how far each assumption can move before "
                             "the 3-year case stops paying.")
    return parser


def _find_process(processes: list[ProcessInput], name: str) -> ProcessInput | None:
    """Return the process with this exact name, or None if there isn't one."""
    return next((p for p in processes if p.name == name), None)


def _unknown_process_error(processes: list[ProcessInput], name: str) -> int:
    """Print a clean 'unknown process' message listing valid names; return 2."""
    names = ", ".join(f"'{p.name}'" for p in processes)
    print(f"error: unknown process '{name}'. Valid names: {names}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    """Program entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)

    if args.sort not in VALID_SORT_FIELDS:
        print(f"error: unknown sort field '{args.sort}'. "
              f"Valid fields: {', '.join(VALID_SORT_FIELDS)}", file=sys.stderr)
        return 2

    if not 0 < args.swing < 100:
        print(f"error: --swing must be between 0 and 100 (got {args.swing:g}).",
              file=sys.stderr)
        return 2

    try:
        processes = load_processes(args.csv)
    except FileNotFoundError:
        print(f"error: input CSV not found: {args.csv}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.sensitivity is not None:
        match = _find_process(processes, args.sensitivity)
        if match is None:
            return _unknown_process_error(processes, args.sensitivity)
        print(render_sensitivity_report(match, args.swing / 100))
        return 0

    if args.breakeven is not None:
        match = _find_process(processes, args.breakeven)
        if match is None:
            return _unknown_process_error(processes, args.breakeven)
        print(render_breakeven_report(match))
        return 0

    results = rank([compute(p) for p in processes], key=args.sort)

    print("Automation backlog - ranked by "
          f"{args.sort} ({len(results)} processes)\n")
    print(render_table(results))

    total_net = sum(r.annual_net_saving for r in results)
    total_hours = sum(r.annual_hours_saved for r in results)
    total_fte = total_hours / FTE_HOURS_PER_YEAR
    print(f"\nPortfolio total: {total_hours:,.0f} hours/yr "
          f"(~{total_fte:,.1f} FTE at {FTE_HOURS_PER_YEAR:,} productive h/yr), "
          f"{total_net:,.0f} EUR/yr net saving")

    if args.export_json:
        export_json(results, args.export_json)
        print(f"Wrote JSON -> {args.export_json}")
    if args.export_csv:
        export_csv(results, args.export_csv)
        print(f"Wrote CSV  -> {args.export_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
