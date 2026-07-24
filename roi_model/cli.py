"""cli.py — command-line front end for the ROI model.

Prints a ranked automation backlog and, optionally, exports the full
results to CSV or JSON.

Usage:
    python -m roi_model                     # ranked table from the seed data
    python -m roi_model --csv data.csv      # rank a different input CSV
    python -m roi_model --sort payback_months
    python -m roi_model --export-json out.json
    python -m roi_model --export-csv out.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from roi_model.data_load import load_processes
from roi_model.model import ProcessResult, compute, rank

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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)

    processes = load_processes(args.csv)
    results = rank([compute(p) for p in processes], key=args.sort)

    print("Automation backlog — ranked by "
          f"{args.sort} ({len(results)} processes)\n")
    print(render_table(results))

    total_net = sum(r.annual_net_saving for r in results)
    total_hours = sum(r.annual_hours_saved for r in results)
    print(f"\nPortfolio total: {total_hours:,.0f} hours/yr, "
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
