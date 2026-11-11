from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from nivaro_cart.domain.errors import CartInputError


@dataclass(frozen=True)
class Limits:
    variants: int = 50
    lines: int = 100
    units_per_variant: int = 20

    def __post_init__(self) -> None:
        if min(self.variants, self.lines, self.units_per_variant) < 1:
            raise ValueError("Cart limits must be positive")


DEFAULT_LIMITS = Limits()


def validate_quantities(lines: Iterable[tuple[UUID, int]], limits: Limits = DEFAULT_LIMITS) -> None:
    """Validate the entire proposed snapshot under the owner's cart lock."""
    totals: Counter[UUID] = Counter()
    count = 0
    for variant, quantity in lines:
        if type(quantity) is not int or quantity < 1:
            raise CartInputError("cart.invalid_quantity")
        totals[variant] += quantity
        count += 1
        if (
            count > limits.lines
            or len(totals) > limits.variants
            or totals[variant] > limits.units_per_variant
        ):
            raise CartInputError("cart.limit")
