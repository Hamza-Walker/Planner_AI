from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from energy.price_signal import EnergyStatus


@dataclass(frozen=True)
class EnergyPolicy:
    """Simple policy layer mapping an energy signal to application behavior."""

    price_threshold_eur: float = 0.70
    fail_open: bool = True

    def should_process_now(self, status: Optional[EnergyStatus]) -> bool:
        """Whether to process a note immediately.

        Planner_AI is typically tolerant to delays, so when energy is expensive we can queue.
        """
        if status is None:
            return self.fail_open

        if status.solar_available is True:
            return True

        if status.electricity_price_eur is None:
            return self.fail_open

        return status.electricity_price_eur < self.price_threshold_eur

    def llm_tier(self, status: Optional[EnergyStatus]) -> str:
        """Return a coarse model tier: 'large' when energy is cheap, otherwise 'small'."""
        return "large" if self.should_process_now(status) else "small"
