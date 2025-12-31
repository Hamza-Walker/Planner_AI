import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass(frozen=True)
class EnergyStatus:
    electricity_price_eur: Optional[float]
    solar_available: Optional[bool]
    fetched_at_unix_s: float


def fetch_energy_status(status_url: str, timeout_s: float = 1.0) -> Optional[EnergyStatus]:
    """Fetch energy status from an in-cluster service (e.g., price simulator).

    Expected JSON shape (exercise 10):
      {"electricity_price_eur": <float>, "solar_available": <0|1>}

    Returns None on failure (callers should decide their fallback behavior).
    """
    try:
        resp = requests.get(status_url, timeout=timeout_s)
        resp.raise_for_status()
        payload = resp.json()

        price = payload.get("electricity_price_eur")
        solar_raw = payload.get("solar_available")

        solar: Optional[bool]
        if solar_raw is None:
            solar = None
        else:
            solar = bool(int(solar_raw))

        return EnergyStatus(
            electricity_price_eur=float(price) if price is not None else None,
            solar_available=solar,
            fetched_at_unix_s=time.time(),
        )
    except Exception as e:
        logging.getLogger(__name__).warning("Energy status unavailable: %s", e)
        return None
