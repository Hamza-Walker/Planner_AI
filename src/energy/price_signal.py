import logging
import time
import os
from dataclasses import dataclass
from typing import Optional

import requests
from energy.electricity_maps import ElectricityMapsConfig, fetch_from_electricity_maps

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnergyStatus:
    electricity_price_eur: Optional[float]
    solar_available: Optional[bool]
    fetched_at_unix_s: float
    source: str = "simulator"  # "simulator" or "electricity_maps"


def fetch_energy_status(
    status_url: str, timeout_s: float = 1.0
) -> Optional[EnergyStatus]:
    """Fetch energy status from configured sources.

    Prioritizes Electricity Maps if configured, falls back to local simulator.
    """
    # 1. Try Electricity Maps first if configured
    em_api_key = os.getenv("ELECTRICITY_MAPS_API_KEY")
    if em_api_key:
        em_config = ElectricityMapsConfig(api_key=em_api_key)
        em_data = fetch_from_electricity_maps(em_config)

        if em_data:
            # Map Carbon Intensity to Price for compatibility with existing logic
            # Heuristic:
            # < 150g = Cheap (Low Carbon) -> €0.20
            # > 400g = Expensive (High Carbon) -> €0.80
            # Linear interpolation in between
            carbon = em_data.get("carbon_intensity")
            if carbon is None:
                carbon = 300  # Default fallback

            # Simple mapping: 0-600g -> €0.10 - €0.90
            simulated_price = 0.10 + (min(carbon, 600) / 600) * 0.80

            return EnergyStatus(
                electricity_price_eur=simulated_price,
                solar_available=em_data.get("solar_available"),
                fetched_at_unix_s=time.time(),
                source="electricity_maps",
            )

    # 2. Fallback to local simulator
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
            source="simulator",
        )
    except Exception as e:
        logger.warning("Energy status unavailable from simulator: %s", e)
        return None
