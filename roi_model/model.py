"""model.py — pure ROI math for automating a single manual process.

This is the single source of truth for the calculation. The browser
dashboard (``web/index.html``) mirrors these exact formulas in JavaScript
so the two halves of the project always agree.

Usage:
    from roi_model.model import ProcessInput, compute

    proc = ProcessInput(
        name="RFQ email triage",
        annual_volume=48000,
        minutes_manual=6,
        minutes_auto=1,
        hourly_wage=32,
        coverage=0.70,
        build_cost=25000,
        monthly_cost=400,
    )
    result = compute(proc)
    print(result.annual_hours_saved)   # -> 2800.0
    print(result.payback_months)       # -> ~3.54
    print(result.roi_3y_pct)           # -> three-year return on investment, %
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

# --- Model-wide assumptions (mirrored verbatim in web/index.html) ------------
HORIZON_YEARS = 3          # planning horizon for ROI / NPV
DISCOUNT_RATE = 0.08       # annual discount rate used for NPV
MONTHS_PER_YEAR = 12
MINUTES_PER_HOUR = 60
FTE_HOURS_PER_YEAR = 1700  # productive hours per full-time employee (display only)


@dataclass(frozen=True)
class ProcessInput:
    """One candidate process and the business assumptions around automating it.

    Fields:
        name           Human-readable process name.
        annual_volume  Number of tasks handled per year.
        minutes_manual Minutes a person spends per task today.
        minutes_auto   Minutes per task after automation (residual handling).
        hourly_wage    Fully-loaded labour cost per hour, in currency units.
        coverage       Fraction of volume the automation can actually handle (0..1).
        build_cost     One-off cost to build/deploy the automation.
        monthly_cost   Recurring running cost per month (licences, compute, upkeep).
    """

    name: str
    annual_volume: float
    minutes_manual: float
    minutes_auto: float
    hourly_wage: float
    coverage: float
    build_cost: float
    monthly_cost: float


@dataclass(frozen=True)
class ProcessResult:
    """Computed business case for one process. All money is in currency units."""

    name: str
    automated_volume: float
    annual_hours_saved: float
    annual_gross_saving: float     # labour value freed up
    annual_running_cost: float     # monthly_cost * 12
    annual_net_saving: float       # gross saving minus running cost
    payback_months: float | None   # None == never pays back
    net_benefit_3y: float          # net_saving * horizon - build_cost
    roi_3y_pct: float              # net benefit as % of total cost
    npv_3y: float                  # discounted net present value

    def as_row(self) -> dict:
        """Flatten to a plain dict (handy for CSV/JSON export and tables)."""
        return asdict(self)


def compute(proc: ProcessInput, horizon_years: int = HORIZON_YEARS,
            discount_rate: float = DISCOUNT_RATE) -> ProcessResult:
    """Turn one :class:`ProcessInput` into a :class:`ProcessResult`.

    The math, step by step:

    * ``automated_volume``   = volume * coverage
    * ``minutes_saved/task`` = manual - automated (clamped at >= 0)
    * ``annual_hours_saved`` = automated_volume * minutes_saved / 60
    * ``gross_saving``       = hours_saved * hourly_wage
    * ``running_cost``       = monthly_cost * 12
    * ``net_saving``         = gross_saving - running_cost
    * ``payback_months``     = build_cost / (net_saving / 12), or None if net <= 0
    * ``net_benefit_3y``     = net_saving * horizon - build_cost
    * ``roi_3y_pct``         = net_benefit_3y / total_cost_3y * 100
    * ``npv_3y``             = -build_cost + Σ net_saving / (1+r)^t  for t in 1..horizon
    """
    automated_volume = proc.annual_volume * proc.coverage
    minutes_saved_per_task = max(proc.minutes_manual - proc.minutes_auto, 0.0)

    annual_minutes_saved = automated_volume * minutes_saved_per_task
    annual_hours_saved = annual_minutes_saved / MINUTES_PER_HOUR
    annual_gross_saving = annual_hours_saved * proc.hourly_wage

    annual_running_cost = proc.monthly_cost * MONTHS_PER_YEAR
    annual_net_saving = annual_gross_saving - annual_running_cost

    # Payback: how many months for the one-off build cost to be recovered
    # out of the *net* monthly saving. If we never save money, there is no payback.
    if annual_net_saving > 0:
        monthly_net_saving = annual_net_saving / MONTHS_PER_YEAR
        payback_months = proc.build_cost / monthly_net_saving
    else:
        payback_months = None

    net_benefit_3y = annual_net_saving * horizon_years - proc.build_cost

    total_cost_3y = proc.build_cost + annual_running_cost * horizon_years
    roi_3y_pct = (net_benefit_3y / total_cost_3y * 100) if total_cost_3y > 0 else 0.0

    # NPV: discount each year's net saving back to today, minus the up-front build.
    npv_3y = -proc.build_cost
    for year in range(1, horizon_years + 1):
        npv_3y += annual_net_saving / ((1 + discount_rate) ** year)

    return ProcessResult(
        name=proc.name,
        automated_volume=round(automated_volume, 2),
        annual_hours_saved=round(annual_hours_saved, 2),
        annual_gross_saving=round(annual_gross_saving, 2),
        annual_running_cost=round(annual_running_cost, 2),
        annual_net_saving=round(annual_net_saving, 2),
        payback_months=(round(payback_months, 2)
                        if payback_months is not None else None),
        net_benefit_3y=round(net_benefit_3y, 2),
        roi_3y_pct=round(roi_3y_pct, 2),
        npv_3y=round(npv_3y, 2),
    )


# --- Sensitivity: "what moves the number" ------------------------------------
SENSITIVITY_SWING = 0.20   # default one-at-a-time swing: +/-20% of each input

# Every input sensitivity() varies, mapped to the direction that makes the
# business case WORSE. "low" fields hurt when the base assumption was
# optimistic (less volume, less coverage, cheaper labour, a faster manual
# task than claimed); "high" fields hurt when costs or residual effort
# overrun. Insertion order is the tie-break order for equal swings.
_PESSIMISTIC_DIRECTION = {
    "annual_volume": "low",
    "minutes_manual": "low",
    "minutes_auto": "high",
    "hourly_wage": "low",
    "coverage": "low",
    "build_cost": "high",
    "monthly_cost": "high",
}


@dataclass(frozen=True)
class SensitivityRow:
    """Outcome range when ONE input moves +/-swing while the rest stay put.

    ``pessimistic_net_3y`` <= base <= ``optimistic_net_3y`` always holds:
    the model is monotone in every driver.
    """

    field: str
    pessimistic_input: float
    optimistic_input: float
    pessimistic_net_3y: float
    optimistic_net_3y: float

    @property
    def swing_eur(self) -> float:
        """Total width of the outcome range (the tornado bar length)."""
        return round(self.optimistic_net_3y - self.pessimistic_net_3y, 2)


def _shifted(proc: ProcessInput, field: str, factor: float) -> float:
    """One input scaled by ``factor``; coverage is a fraction, capped at 1."""
    value = getattr(proc, field) * factor
    if field == "coverage":
        value = min(value, 1.0)
    return round(value, 6)


def sensitivity(proc: ProcessInput, swing: float = SENSITIVITY_SWING,
                horizon_years: int = HORIZON_YEARS,
                discount_rate: float = DISCOUNT_RATE) -> list[SensitivityRow]:
    """One-way (tornado) sensitivity of the 3-year net benefit.

    Each driver in ``_PESSIMISTIC_DIRECTION`` is moved down and up by
    ``swing`` (a fraction of its current value, default 0.20 = +/-20%)
    while every other input keeps its value; the metric is
    ``net_benefit_3y``. Rows come back widest-swing first — the classic
    tornado ordering; ties keep the field-definition order (stable sort).

    These are stress bounds on the CURRENT assumptions, not statistical
    confidence intervals: the +/-swing is itself an assumption.
    """
    rows: list[SensitivityRow] = []
    for field, direction in _PESSIMISTIC_DIRECTION.items():
        pess_factor = 1 - swing if direction == "low" else 1 + swing
        opt_factor = 1 + swing if direction == "low" else 1 - swing
        pess_value = _shifted(proc, field, pess_factor)
        opt_value = _shifted(proc, field, opt_factor)
        pess = compute(replace(proc, **{field: pess_value}), horizon_years, discount_rate)
        opt = compute(replace(proc, **{field: opt_value}), horizon_years, discount_rate)
        rows.append(SensitivityRow(
            field=field,
            pessimistic_input=pess_value,
            optimistic_input=opt_value,
            pessimistic_net_3y=pess.net_benefit_3y,
            optimistic_net_3y=opt.net_benefit_3y,
        ))
    rows.sort(key=lambda r: abs(r.optimistic_net_3y - r.pessimistic_net_3y), reverse=True)
    return rows


def stress_band(proc: ProcessInput, swing: float = SENSITIVITY_SWING,
                horizon_years: int = HORIZON_YEARS,
                discount_rate: float = DISCOUNT_RATE,
                ) -> tuple[ProcessResult, ProcessResult]:
    """(worst, best) case with EVERY driver at its bad/good end at once.

    A deliberate stress test bracketing the one-way rows — the ends
    compound, so this is a bound, not a forecast.
    """
    worst_values = {}
    best_values = {}
    for field, direction in _PESSIMISTIC_DIRECTION.items():
        pess_factor = 1 - swing if direction == "low" else 1 + swing
        opt_factor = 1 + swing if direction == "low" else 1 - swing
        worst_values[field] = _shifted(proc, field, pess_factor)
        best_values[field] = _shifted(proc, field, opt_factor)
    worst = compute(replace(proc, **worst_values), horizon_years, discount_rate)
    best = compute(replace(proc, **best_values), horizon_years, discount_rate)
    return worst, best


def rank(results: list[ProcessResult],
         key: str = "net_benefit_3y") -> list[ProcessResult]:
    """Return results sorted best-first to form the automation backlog.

    Default key is three-year net benefit (most euros first). Any field name
    on :class:`ProcessResult` is accepted; ``None`` payback values sort last.
    Best-first means A->Z for ``name``, smallest-first for ``payback_months``,
    and largest-first for every numeric field.
    """
    if key == "name":
        return sorted(results, key=lambda r: r.name)

    def sort_value(r: ProcessResult):
        val = getattr(r, key)
        if val is None:
            # Never-pays-back items always sink to the bottom.
            return float("-inf") if key != "payback_months" else float("inf")
        return val

    reverse = key != "payback_months"  # for payback, smaller is better
    return sorted(results, key=sort_value, reverse=reverse)
