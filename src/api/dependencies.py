from typing import Optional
from codecarbon import EmissionsTracker

from src.storage.durable_queue import DurableQueue
from src.storage.google_auth import GoogleAuthStore
from src.energy.policy import EnergyPolicy
from src.api.state import durable_queue, google_auth_store, policy, tracker

def get_durable_queue() -> Optional[DurableQueue]:
    return durable_queue

def get_google_auth_store() -> Optional[GoogleAuthStore]:
    return google_auth_store

def get_energy_policy() -> EnergyPolicy:
    return policy

def get_emissions_tracker() -> EmissionsTracker:
    return tracker
