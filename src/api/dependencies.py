import os
from typing import Optional
from storage.google_auth import GoogleAuthStore
from storage.durable_queue import DurableQueue
from energy.policy import EnergyPolicy
from api import state

# Configuration
ENERGY_PRICE_THRESHOLD_EUR = float(os.getenv("ENERGY_PRICE_THRESHOLD_EUR", "0.70"))
ENERGY_FAIL_OPEN = os.getenv("ENERGY_FAIL_OPEN", "true").lower() in {"1", "true", "yes"}

policy = EnergyPolicy(
    price_threshold_eur=ENERGY_PRICE_THRESHOLD_EUR,
    fail_open=ENERGY_FAIL_OPEN,
)


def get_google_auth_store() -> Optional[GoogleAuthStore]:
    return state.google_auth_store


def get_durable_queue() -> Optional[DurableQueue]:
    return state.durable_queue


def get_energy_policy() -> EnergyPolicy:
    return policy
