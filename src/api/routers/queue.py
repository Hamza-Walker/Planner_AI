import os
import asyncio
import logging
from typing import Optional
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException
from api import state
from api.dependencies import get_durable_queue, get_energy_policy
from energy.policy import EnergyPolicy
from energy.price_signal import EnergyStatus, fetch_energy_status
from storage.durable_queue import DurableQueue

router = APIRouter()
logger = logging.getLogger(__name__)

# Config
ENERGY_STATUS_URL = os.getenv("ENERGY_STATUS_URL", "").strip()
USE_DURABLE_QUEUE = os.getenv("USE_DURABLE_QUEUE", "true").lower() in {
    "1",
    "true",
    "yes",
}


def _serialize_status(status: Optional[EnergyStatus]) -> Optional[dict]:
    return asdict(status) if status is not None else None


async def _get_energy_status() -> Optional[EnergyStatus]:
    if not ENERGY_STATUS_URL:
        return None
    return await asyncio.to_thread(fetch_energy_status, ENERGY_STATUS_URL, 1.0)


@router.get("")
async def queue_status(
    durable_queue: Optional[DurableQueue] = Depends(get_durable_queue),
    policy: EnergyPolicy = Depends(get_energy_policy),
) -> dict:
    """Get queue status and energy information."""
    status = await _get_energy_status()

    if USE_DURABLE_QUEUE and durable_queue is not None:
        try:
            stats = await durable_queue.get_stats()
            return {
                "queue_type": "durable",
                "queue_size": stats["by_status"].get("pending", {}).get("count", 0),
                "processing": stats["by_status"].get("processing", {}).get("count", 0),
                "completed": stats["by_status"].get("completed", {}).get("count", 0),
                "failed": stats["by_status"].get("failed", {}).get("count", 0),
                "dead": stats["by_status"].get("dead", {}).get("count", 0),
                "total": stats["total"],
                "process_now": policy.should_process_now(status),
                "llm_tier": policy.llm_tier(status),
                "energy": _serialize_status(status),
            }
        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")
            return {
                "queue_type": "durable",
                "error": str(e),
                "process_now": policy.should_process_now(status),
                "llm_tier": policy.llm_tier(status),
                "energy": _serialize_status(status),
            }
    else:
        return {
            "queue_type": "in-memory",
            "queue_size": state.notes_queue.qsize(),
            "process_now": policy.should_process_now(status),
            "llm_tier": policy.llm_tier(status),
            "energy": _serialize_status(status),
        }


@router.get("/items")
async def get_queue_items(
    limit: int = 20,
    status: Optional[str] = None,
    durable_queue: Optional[DurableQueue] = Depends(get_durable_queue),
) -> dict:
    """
    Get recent queue items.

    Args:
        limit: Maximum number of items to return (default 20)
        status: Filter by status (pending, processing, completed, failed, dead)
    """
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(
            status_code=400,
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true",
        )

    try:
        items = await durable_queue.get_recent_items(limit=limit, status=status)
        return {
            "items": [
                {
                    "id": item.id,
                    "notes": item.notes[:100] + "..."
                    if len(item.notes) > 100
                    else item.notes,
                    "status": item.status,
                    "attempts": item.attempts,
                    "max_attempts": item.max_attempts,
                    "last_error": item.last_error,
                    "created_at": item.created_at.isoformat()
                    if item.created_at
                    else None,
                    "completed_at": item.completed_at.isoformat()
                    if item.completed_at
                    else None,
                    "submitted_llm_tier": item.submitted_llm_tier,
                    "processed_llm_tier": item.processed_llm_tier,
                }
                for item in items
            ],
            "count": len(items),
        }
    except Exception as e:
        logger.error(f"Error getting queue items: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/items/{item_id}")
async def get_queue_item(
    item_id: str, durable_queue: Optional[DurableQueue] = Depends(get_durable_queue)
) -> dict:
    """Get details of a specific queue item."""
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(
            status_code=400,
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true",
        )

    try:
        item = await durable_queue.get_item(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Queue item not found")

        return {
            "id": item.id,
            "notes": item.notes,
            "status": item.status,
            "attempts": item.attempts,
            "max_attempts": item.max_attempts,
            "last_error": item.last_error,
            "submitted_energy_price_eur": item.submitted_energy_price_eur,
            "submitted_solar_available": item.submitted_solar_available,
            "submitted_llm_tier": item.submitted_llm_tier,
            "processed_energy_price_eur": item.processed_energy_price_eur,
            "processed_solar_available": item.processed_solar_available,
            "processed_llm_tier": item.processed_llm_tier,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "processing_started_at": item.processing_started_at.isoformat()
            if item.processing_started_at
            else None,
            "completed_at": item.completed_at.isoformat()
            if item.completed_at
            else None,
            "worker_id": item.worker_id,
            "result": item.result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting queue item: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dead")
async def get_dead_letter_items(
    limit: int = 50, durable_queue: Optional[DurableQueue] = Depends(get_durable_queue)
) -> dict:
    """Get items in the dead letter queue (failed after max retries)."""
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(
            status_code=400,
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true",
        )

    try:
        items = await durable_queue.get_dead_letter_items(limit=limit)
        return {
            "items": [
                {
                    "id": item.id,
                    "notes": item.notes[:100] + "..."
                    if len(item.notes) > 100
                    else item.notes,
                    "attempts": item.attempts,
                    "last_error": item.last_error,
                    "created_at": item.created_at.isoformat()
                    if item.created_at
                    else None,
                }
                for item in items
            ],
            "count": len(items),
        }
    except Exception as e:
        logger.error(f"Error getting dead letter items: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/items/{item_id}/retry")
async def retry_dead_item(
    item_id: str, durable_queue: Optional[DurableQueue] = Depends(get_durable_queue)
) -> dict:
    """Retry a dead letter item (reset to pending status)."""
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(
            status_code=400,
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true",
        )

    try:
        success = await durable_queue.retry_dead_item(item_id)
        if not success:
            raise HTTPException(
                status_code=400, detail="Item not found or not in dead status"
            )

        return {
            "status": "success",
            "message": f"Item {item_id} has been reset to pending",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying dead item: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/purge")
async def purge_completed_items(
    older_than_hours: int = 24,
    durable_queue: Optional[DurableQueue] = Depends(get_durable_queue),
) -> dict:
    """Purge completed items older than the specified hours."""
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(
            status_code=400,
            detail="Durable queue not enabled. Set USE_DURABLE_QUEUE=true",
        )

    try:
        count = await durable_queue.purge_completed(older_than_hours=older_than_hours)
        return {
            "status": "success",
            "purged_count": count,
            "older_than_hours": older_than_hours,
        }
    except Exception as e:
        logger.error(f"Error purging completed items: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/items/{item_id}")
async def delete_queue_item(
    item_id: str, durable_queue: Optional[DurableQueue] = Depends(get_durable_queue)
):
    """Permanently remove a queue item."""
    if not USE_DURABLE_QUEUE or durable_queue is None:
        raise HTTPException(status_code=400, detail="Durable Queue not enabled")

    deleted = await durable_queue.delete_item(item_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail="Item not found or could not be deleted"
        )

    return {"status": "deleted", "id": item_id}
