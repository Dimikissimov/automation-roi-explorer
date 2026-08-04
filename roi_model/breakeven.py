"""breakeven.py — how far each assumption can move before the case stops paying.

The tornado (:func:`roi_model.model.sensitivity`) answers *"which driver moves
the outcome most within +/-X%"*. This module answers the complementary question
a finance reviewer asks next: *"how wrong can each assumption be before
automating this process stops paying back over three years?"*

For every driver it solves for the value at which the 3-year net benefit crosses
zero, holding the other drivers at their base value, and reports the **margin of
safety** — how far the base assumption sits from that break-even point, in
absolute terms and as a percentage of the base. Drivers are ranked tightest
margin first: the assumption with the least headroom is the one the decision is
most fragile to.

No ROI math is re-derived here. The break-even is found by bisection on
:func:`roi_model.model.compute` — the single source of truth — so it stays
correct even if the underlying formula changes. The result is deterministic:
the same input always yields byte-identical output.

Honesty note: these are *tolerances on your own assumptions*, not probabilities.
"Coverage can fall to 40% before the case stops paying" says nothing about how
likely that is — only how much room the estimate has before the decision flips.

Usage:
    from roi_model.breakeven import break_even
    rows = break_even(proc)          # tightest margin first
    print(rows[0].field, rows[0].breakeven_value, rows[0].margin_pct)
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from roi_model.model import (
    _PESSIMISTIC_DIRECTION,
    DISCOUNT_RATE,
    HORIZON_YEARS,
    ProcessInput,
    compute,
)

# Bisection is deterministic: halving the bracket this many times drives it far
# below compute()'s 2-decimal rounding, so the crossing is pinned exactly.
_BISECTION_ITERS = 200

# Cost drivers ("high" direction) have no upper bound, so the search bracket is
# widened by doubling until the net benefit goes negative. This caps that search.
_MAX_EXPANSIONS = 100


@dataclass(frozen=True)
class BreakEvenRow:
    """The break-even point of one driver, holding every other driver at base.

    ``direction`` is the way this driver worsens the case ("low" = the case
    suffers when the value falls, e.g. volume/coverage/wage; "high" = it suffers
    when the value rises, e.g. build/running cost or residual minutes).

    ``breakeven_value`` is ``None`` when the case survives even at the driver's
    worst reachable end (a fall to zero, or a rise past the point where savings
    vanish): that assumption cannot break the case on its own.
    """

    field: str
    direction: str
    base_value: float
    breakeven_value: float | None
    base_net_3y: float

    @property
    def margin_abs(self) -> float | None:
        """How far the base sits from break-even, in the driver's own units."""
        if self.breakeven_value is None:
            return None
        return round(abs(self.base_value - self.breakeven_value), 6)

    @property
    def margin_pct(self) -> float | None:
        """The margin as a percentage of the base value (headroom).

        Smaller means more fragile. ``None`` when there is no reachable
        break-even, or when the base value is zero (no percentage is defined).
        """
        if self.breakeven_value is None or self.base_value == 0:
            return None
        return round(
            abs(self.base_value - self.breakeven_value) / abs(self.base_value) * 100, 2
        )


def _net_benefit_at(proc: ProcessInput, field: str, value: float,
                    horizon_years: int, discount_rate: float) -> float:
    """3-year net benefit with a single driver replaced by ``value``."""
    return compute(replace(proc, **{field: value}), horizon_years, discount_rate).net_benefit_3y


def _solve_low(proc: ProcessInput, field: str, base_value: float,
               horizon_years: int, discount_rate: float) -> float | None:
    """Break-even for a driver that worsens the case as it FALLS.

    Net benefit rises with the driver, so it is negative at the floor (0) and
    positive at the base. Returns ``None`` if the case still pays at the floor.
    """
    lo, hi = 0.0, base_value
    if _net_benefit_at(proc, field, lo, horizon_years, discount_rate) >= 0:
        return None  # survives even with this driver at zero
    for _ in range(_BISECTION_ITERS):
        mid = (lo + hi) / 2
        if _net_benefit_at(proc, field, mid, horizon_years, discount_rate) < 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 6)


def _solve_high(proc: ProcessInput, field: str, base_value: float,
                horizon_years: int, discount_rate: float) -> float | None:
    """Break-even for a driver that worsens the case as it RISES.

    Net benefit falls as the driver grows. The bracket is widened by doubling
    until the net benefit goes negative, then bisected. Returns ``None`` if no
    negative end is reached within the expansion cap.
    """
    lo = base_value
    step = max(abs(base_value), 1.0)
    hi = base_value + step
    expansions = 0
    while _net_benefit_at(proc, field, hi, horizon_years, discount_rate) >= 0:
        step *= 2
        hi = base_value + step
        expansions += 1
        if expansions > _MAX_EXPANSIONS:
            return None
    for _ in range(_BISECTION_ITERS):
        mid = (lo + hi) / 2
        if _net_benefit_at(proc, field, mid, horizon_years, discount_rate) > 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 6)


def break_even(proc: ProcessInput, horizon_years: int = HORIZON_YEARS,
               discount_rate: float = DISCOUNT_RATE) -> list[BreakEvenRow]:
    """Per-driver break-even of the 3-year net benefit, tightest margin first.

    For each driver, every other input stays at its base value while this one is
    moved in the direction that hurts the case until ``net_benefit_3y`` reaches
    zero. Rows come back sorted by ``margin_pct`` ascending (the most fragile
    assumption first); drivers with no reachable break-even sort last. Ties keep
    the field-definition order (stable sort).

    If the base case does not already pay back, no deterioration margin is
    defined, so every ``breakeven_value`` is ``None``.
    """
    base_net = compute(proc, horizon_years, discount_rate).net_benefit_3y
    rows: list[BreakEvenRow] = []
    for field, direction in _PESSIMISTIC_DIRECTION.items():
        base_value = float(getattr(proc, field))
        if base_net <= 0:
            breakeven = None
        elif direction == "low":
            breakeven = _solve_low(proc, field, base_value, horizon_years, discount_rate)
        else:
            breakeven = _solve_high(proc, field, base_value, horizon_years, discount_rate)
        rows.append(BreakEvenRow(
            field=field,
            direction=direction,
            base_value=base_value,
            breakeven_value=breakeven,
            base_net_3y=base_net,
        ))

    # Tightest headroom first; unreachable / undefined margins sink to the end.
    def sort_key(r: BreakEvenRow) -> float:
        return r.margin_pct if r.margin_pct is not None else float("inf")

    rows.sort(key=sort_key)
    return rows
