"""rollout.py — phased adoption ramp and the cumulative cashflow curve.

The base model (:func:`roi_model.model.compute`) reports payback as a single
idealised number — ``build_cost / (net_saving / 12)`` — which quietly assumes the
automation delivers its full steady-state benefit from month one. Real rollouts
do not: adoption climbs over a few months while the running cost is paid in full
from go-live. This module answers the question a delivery lead asks next:

    *"Once we allow for a realistic adoption ramp, when does this actually turn
    cash-positive, and how much 3-year benefit does the ramp cost us?"*

It lays the steady-state economics from ``compute()`` onto a month-by-month
timeline. Benefit ramps linearly from zero to full over ``ramp_months`` (then
holds flat); the running cost is charged in full every month from the start. The
result is a **cumulative cashflow curve**, a **ramp-adjusted payback month** (the
first month the curve crosses zero), and the **ramp cost** — the 3-year net
benefit forgone versus the idealised instant-benefit case.

No ROI math is re-derived here: the steady-state monthly gross saving and running
cost come straight from :func:`compute`, the single source of truth, so this view
can never drift from the CLI table. The result is deterministic — no RNG, no
wall-clock — so the same input yields byte-identical output.

Honesty note: the linear ramp is an *illustrative assumption*, not a measured
adoption curve. It shows how sensitive payback is to a slow start; it does not
predict how your rollout will actually ramp.

Usage:
    from roi_model.rollout import phased_cashflow
    roll = phased_cashflow(proc, ramp_months=6)
    print(roll.ramp_payback_month)     # e.g. 6  (vs the idealised ~2.8)
    print(roll.ramp_cost_3y)           # 3-year net benefit lost to the ramp
"""

from __future__ import annotations

from dataclasses import dataclass

from roi_model.model import (
    DISCOUNT_RATE,
    HORIZON_YEARS,
    MONTHS_PER_YEAR,
    ProcessInput,
    compute,
)

# Default linear adoption ramp: full steady-state benefit reached after 6 months.
DEFAULT_RAMP_MONTHS = 6


@dataclass(frozen=True)
class CashflowMonth:
    """One month on the rollout timeline.

    ``realized_fraction`` is the share of steady-state benefit live this month
    (0..1). ``monthly_net`` is that month's realised gross saving minus the full
    running cost. ``cumulative_net`` is the running cashflow including the
    up-front build cost, so it starts deep in the red and climbs.
    """

    month: int
    realized_fraction: float
    monthly_net: float
    cumulative_net: float


@dataclass(frozen=True)
class RolloutResult:
    """Phased-rollout cashflow for one process against its idealised base case.

    ``*_instant`` fields are the base model's numbers (full benefit from month
    one); ``*_ramped`` fields fold in the adoption ramp. The ramped figures are
    never better than the instant ones — a ramp can only delay benefit, never
    bring it forward.
    """

    name: str
    ramp_months: int
    horizon_months: int
    monthly_gross_full: float      # steady-state monthly gross saving
    monthly_running_cost: float
    build_cost: float
    schedule: tuple[CashflowMonth, ...]
    ramp_payback_month: int | None       # first month cumulative_net >= 0
    instant_payback_months: float | None  # compute(): build / (net / 12)
    net_benefit_3y_ramped: float
    net_benefit_3y_instant: float
    npv_3y_ramped: float
    npv_3y_instant: float

    @property
    def ramp_cost_3y(self) -> float:
        """3-year net benefit forgone by ramping vs. instant full benefit.

        Always >= 0: the running cost is identical either way, so the whole gap
        is the gross saving the slow start leaves on the table.
        """
        return round(self.net_benefit_3y_instant - self.net_benefit_3y_ramped, 2)

    @property
    def payback_slip_months(self) -> float | None:
        """Extra months to payback vs. the idealised instant payback.

        ``None`` when either payback is undefined (the case never pays back, with
        or without a ramp).
        """
        if self.ramp_payback_month is None or self.instant_payback_months is None:
            return None
        return round(self.ramp_payback_month - self.instant_payback_months, 2)


def _realized_fraction(month: int, ramp_months: int) -> float:
    """Linear adoption ramp: benefit climbs 0 -> full, reaching full at ramp_months.

    Month 1 already carries ``1 / ramp_months`` of the benefit; from
    ``ramp_months`` onward the automation runs at full steady-state coverage.
    ``ramp_months == 1`` means full benefit from month one (no ramp), so the
    model collapses back to the idealised instant-benefit case.
    """
    return min(month / ramp_months, 1.0)


def phased_cashflow(proc: ProcessInput, ramp_months: int = DEFAULT_RAMP_MONTHS,
                    horizon_years: int = HORIZON_YEARS,
                    discount_rate: float = DISCOUNT_RATE) -> RolloutResult:
    """Roll one process's steady-state economics onto a monthly rollout timeline.

    The steady-state monthly gross saving and running cost are taken from
    :func:`compute` (no ROI math is re-derived). Each month realises
    ``monthly_gross_full * realized_fraction`` of the gross saving while paying
    the running cost in full; the cumulative cashflow starts at ``-build_cost``
    and climbs. ``ramp_payback_month`` is the first month it reaches zero (or
    ``None`` if it never does within the horizon).

    Raises ``ValueError`` if ``ramp_months`` is below 1.
    """
    if ramp_months < 1:
        raise ValueError(f"ramp_months must be >= 1 (got {ramp_months}).")

    base = compute(proc, horizon_years, discount_rate)
    monthly_gross_full = base.annual_gross_saving / MONTHS_PER_YEAR
    monthly_running_cost = base.annual_running_cost / MONTHS_PER_YEAR
    horizon_months = horizon_years * MONTHS_PER_YEAR

    schedule: list[CashflowMonth] = []
    cumulative = -proc.build_cost
    ramp_payback_month: int | None = None
    yearly_net = [0.0] * horizon_years

    for month in range(1, horizon_months + 1):
        fraction = _realized_fraction(month, ramp_months)
        monthly_net = monthly_gross_full * fraction - monthly_running_cost
        cumulative += monthly_net
        if ramp_payback_month is None and cumulative >= 0:
            ramp_payback_month = month
        yearly_net[(month - 1) // MONTHS_PER_YEAR] += monthly_net
        schedule.append(CashflowMonth(
            month=month,
            realized_fraction=round(fraction, 6),
            monthly_net=round(monthly_net, 2),
            cumulative_net=round(cumulative, 2),
        ))

    net_benefit_3y_ramped = sum(yearly_net) - proc.build_cost
    npv_3y_ramped = -proc.build_cost
    for year in range(1, horizon_years + 1):
        npv_3y_ramped += yearly_net[year - 1] / ((1 + discount_rate) ** year)

    return RolloutResult(
        name=proc.name,
        ramp_months=ramp_months,
        horizon_months=horizon_months,
        monthly_gross_full=round(monthly_gross_full, 2),
        monthly_running_cost=round(monthly_running_cost, 2),
        build_cost=proc.build_cost,
        schedule=tuple(schedule),
        ramp_payback_month=ramp_payback_month,
        instant_payback_months=base.payback_months,
        net_benefit_3y_ramped=round(net_benefit_3y_ramped, 2),
        net_benefit_3y_instant=base.net_benefit_3y,
        npv_3y_ramped=round(npv_3y_ramped, 2),
        npv_3y_instant=base.npv_3y,
    )
