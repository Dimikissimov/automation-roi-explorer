"""data_load.py — read seeded candidate processes from the bundled CSV.

Usage:
    from roi_model.data_load import load_processes
    procs = load_processes()            # bundled data/processes.csv
    procs = load_processes("my.csv")    # or your own file
"""

from __future__ import annotations

import csv
from pathlib import Path

from roi_model.model import ProcessInput

# The seed dataset ships next to this module in data/processes.csv.
DEFAULT_CSV = Path(__file__).with_name("data") / "processes.csv"

# Columns expected in the CSV, in the order ProcessInput takes them.
_NUMERIC_FIELDS = (
    "annual_volume", "minutes_manual", "minutes_auto",
    "hourly_wage", "coverage", "build_cost", "monthly_cost",
)


def load_processes(path: str | Path | None = None) -> list[ProcessInput]:
    """Load candidate processes from a CSV into :class:`ProcessInput` objects.

    The CSV must have a header row with columns: name plus every field in
    ``_NUMERIC_FIELDS``. Raises ``ValueError`` on missing columns so a
    malformed file fails loudly rather than silently mis-modelling.
    """
    csv_path = Path(path) if path is not None else DEFAULT_CSV
    procs: list[ProcessInput] = []

    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = {"name", *_NUMERIC_FIELDS} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{csv_path} is missing columns: {', '.join(sorted(missing))}"
            )
        for row in reader:
            procs.append(ProcessInput(
                name=row["name"].strip(),
                **{field: float(row[field]) for field in _NUMERIC_FIELDS},
            ))

    return procs
