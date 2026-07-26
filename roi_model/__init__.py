"""roi_model — quantify the business case for automating manual processes.

Public API:
    ProcessInput, ProcessResult, compute, rank    (from roi_model.model)
    SensitivityRow, sensitivity, stress_band      (from roi_model.model)
    load_processes                                (from roi_model.data_load)

Example:
    from roi_model import load_processes, compute, rank
    results = [compute(p) for p in load_processes()]
    for r in rank(results):
        print(r.name, r.net_benefit_3y)
"""

from roi_model.data_load import load_processes
from roi_model.model import (
    ProcessInput,
    ProcessResult,
    SensitivityRow,
    compute,
    rank,
    sensitivity,
    stress_band,
)

__all__ = [
    "ProcessInput",
    "ProcessResult",
    "SensitivityRow",
    "compute",
    "rank",
    "sensitivity",
    "stress_band",
    "load_processes",
]

__version__ = "1.0.0"
