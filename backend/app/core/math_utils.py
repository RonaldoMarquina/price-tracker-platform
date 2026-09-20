"""Mathematical and statistical utilities for analytical calculations."""

from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any, TypeVar

T = TypeVar("T")

CENTS = Decimal("0.01")
HUNDRED = Decimal("100.00")
ZERO = Decimal("0.00")


def distribute_percentages(items: list[tuple[T, Decimal]]) -> dict[T, Decimal]:
    """Distribute percentages across items so that their rounded sum equals exactly 100.00%.

    Uses the Largest Remainder Method (Hare-Niemeyer) with deterministic tie-breaking:
    1. Calculate exact percentage: p_i = (val_i / total) * 100
    2. Truncate to two decimals with ROUND_FLOOR.
    3. Calculate remainder: r_i = p_i - floor_i
    4. Distribute +0.01 to the items with highest remainders.
       Tie-breaker: highest original value, then str(key) ASC.
    """
    if not items:
        return {}

    total_val = sum((v for _, v in items), ZERO)
    if total_val <= ZERO:
        return {k: ZERO for k, _ in items}

    exact_p: list[dict] = []
    base_sum = ZERO

    for k, v in items:
        exact = (v / total_val) * Decimal("100")
        floor_val = exact.quantize(CENTS, rounding=ROUND_FLOOR)
        remainder = exact - floor_val
        base_sum += floor_val
        exact_p.append(
            {
                "key": k,
                "val": v,
                "base": floor_val,
                "remainder": remainder,
            }
        )

    discrepancy = HUNDRED - base_sum
    units_to_distribute = int((discrepancy / CENTS).to_integral_value(rounding=ROUND_HALF_UP))

    # Sort descending by remainder, then descending by original value,
    # then ascending by key representation
    def _sort_key(item: dict[str, Any]) -> tuple[Decimal, Decimal, int]:
        char_val = -ord(str(item["key"])[0]) if str(item["key"]) else 0
        return (item["remainder"], item["val"], char_val)

    exact_p.sort(key=_sort_key, reverse=True)

    result: dict[T, Decimal] = {}
    for i, item in enumerate(exact_p):
        added = CENTS if i < units_to_distribute else ZERO
        result[item["key"]] = item["base"] + added

    return result


def quantize_currency(value: Decimal | None) -> str:
    """Format monetary decimal to 2 decimal places as string, never using float."""
    if value is None:
        return "0.00"
    return str(value.quantize(CENTS, rounding=ROUND_HALF_UP))


def quantize_percentage(value: Decimal | None) -> Decimal:
    """Round percentage to 2 decimal places using Decimal."""
    if value is None:
        return ZERO
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)
