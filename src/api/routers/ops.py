import os
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from api.metrics import QUEUE_DEPTH

from api import state
from api.dependencies import get_durable_queue
from storage import db
from storage.durable_queue import DurableQueue

router = APIRouter()
logger = logging.getLogger(__name__)

# Config
USE_DURABLE_QUEUE = os.getenv("USE_DURABLE_QUEUE", "true").lower() in {
    "1",
    "true",
    "yes",
}


@router.get("/health")
async def health_check(
    durable_queue: Optional[DurableQueue] = Depends(get_durable_queue),
) -> dict:
    """Health check endpoint for container orchestration."""
    health = {
        "status": "healthy",
        "profile": os.getenv("DEPLOYMENT_PROFILE", "unknown"),
        "queue_type": "durable" if USE_DURABLE_QUEUE and durable_queue else "in-memory",
    }

    if USE_DURABLE_QUEUE and durable_queue is not None:
        try:
            db_health = await db.health_check()
            health["database"] = db_health
            health["queue_size"] = await durable_queue.get_pending_count()
            if db_health["status"] != "healthy":
                health["status"] = "degraded"
        except Exception as e:
            health["status"] = "degraded"
            health["database"] = {"status": "error", "error": str(e)}
            health["queue_size"] = 0
    else:
        health["queue_size"] = state.notes_queue.qsize()

    return health


@router.get("/metrics")
async def metrics(
    durable_queue: Optional[DurableQueue] = Depends(get_durable_queue),
) -> Response:
    """
    Prometheus scrape endpoint.
    """
    try:
        if USE_DURABLE_QUEUE and durable_queue is not None:
            # Gauge.set is synchronous but get_pending_count is async.
            # We must await it first.
            count = await durable_queue.get_pending_count()
            QUEUE_DEPTH.set(count)
        else:
            QUEUE_DEPTH.set(state.notes_queue.qsize())
    except Exception:
        pass

    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@router.get("/metrics/carbon")
async def get_carbon_metrics() -> dict:
    """Get carbon emissions metrics from CodeCarbon."""
    try:
        emissions = 0.0
        energy = 0.0
        duration = 0.0

        tracker = state.tracker

        # Get energy consumption (available while tracking)
        if hasattr(tracker, "_total_energy") and tracker._total_energy is not None:
            if hasattr(tracker._total_energy, "kWh"):
                energy = float(tracker._total_energy.kWh)

        # Calculate duration using monotonic time (CodeCarbon uses time.monotonic for _start_time)
        if hasattr(tracker, "_start_time") and tracker._start_time is not None:
            import time as time_module

            duration = time_module.monotonic() - tracker._start_time

        # Estimate emissions from energy
        # Use average carbon intensity of ~0.4 kg CO2/kWh (global average)
        # This is a reasonable estimate when real-time data isn't available
        if energy > 0:
            emissions = energy * 0.4

        return {
            "emissions_kg": emissions,
            "emissions_g": emissions * 1000,
            "energy_kwh": energy,
            "duration_seconds": duration,
            "project_name": "planner-ai-backend",
        }
    except Exception as e:
        logger.warning(f"Could not retrieve carbon metrics: {e}")
        return {
            "emissions_kg": 0.0,
            "emissions_g": 0.0,
            "energy_kwh": 0.0,
            "duration_seconds": 0.0,
            "project_name": "planner-ai-backend",
            "error": str(e),
        }
