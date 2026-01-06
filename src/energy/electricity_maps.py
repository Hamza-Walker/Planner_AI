import logging
import time
from dataclasses import dataclass
from typing import Optional
import os
import requests

logger = logging.getLogger(__name__)


@dataclass
class ElectricityMapsConfig:
    api_key: str
    zone: str = "DE"  # Default to Germany
    base_url: str = "https://api.electricitymap.org/v3"


def fetch_from_electricity_maps(config: ElectricityMapsConfig) -> Optional[dict]:
    """
    Fetch live carbon intensity and power breakdown from Electricity Maps.

    Returns a dict with:
    - carbon_intensity (gCO2eq/kWh)
    - renewable_percentage (%)
    - price (if available, else None)
    """
    if not config.api_key:
        logger.warning("Electricity Maps API key not configured")
        return None

    try:
        # Fetch power breakdown to get renewable percentage
        url = f"{config.base_url}/power-breakdown/latest"
        headers = {"auth-token": config.api_key}
        params = {"zone": config.zone}

        response = requests.get(url, headers=headers, params=params, timeout=5.0)
        response.raise_for_status()
        data = response.json()

        carbon_intensity = data.get("carbonIntensity")
        
        # If carbon intensity is missing from breakdown, try specific endpoint
        if carbon_intensity is None:
            try:
                url_carbon = f"{config.base_url}/carbon-intensity/latest"
                resp_carbon = requests.get(url_carbon, headers=headers, params=params, timeout=5.0)
                if resp_carbon.ok:
                    carbon_data = resp_carbon.json()
                    carbon_intensity = carbon_data.get("carbonIntensity")
                    logger.info(f"Fetched carbon intensity from dedicated endpoint: {carbon_intensity}")
            except Exception as e_carbon:
                logger.warning(f"Failed to fetch fallback carbon intensity: {e_carbon}")

        renewable_percentage = data.get("renewablePercentage")

        # Determine if solar is active (this is a heuristic)
        # In a real app, we might check specifically for solar generation > threshold
        generation = data.get("powerProductionBreakdown", {})
        solar_gen = generation.get("solar", 0)
        is_solar_available = solar_gen > 0

        return {
            "carbon_intensity": carbon_intensity,
            "renewable_percentage": renewable_percentage,
            "solar_available": is_solar_available,
            # Electricity Maps free tier might not give price directly in this endpoint,
            # but we can use carbon intensity as a proxy for "cost" in our logic if needed.
            # For now, let's map carbon intensity to our "price" concept for compatibility.
            # Low carbon = "cheap/good", High carbon = "expensive/bad"
        }

    except Exception as e:
        logger.error(f"Error fetching from Electricity Maps: {e}")
        return None
