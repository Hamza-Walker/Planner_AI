"""
Durable Queue module for Planner AI.

Provides a PostgreSQL-backed queue for energy-aware task processing.
Items are queued when energy is expensive and processed when conditions improve.
"""

import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List, Any

from storage import db

logger = logging.getLogger(__name__)


@dataclass
class QueueItem:
    """Represents an item in the durable queue."""
    id: str
    notes: str
    status: str
    attempts: int
    max_attempts: int
    last_error: Optional[str]
    submitted_energy_price_eur: Optional[float]
    submitted_solar_available: Optional[bool]
    submitted_llm_tier: Optional[str]
    processed_energy_price_eur: Optional[float]
    processed_solar_available: Optional[bool]
    processed_llm_tier: Optional[str]
    created_at: datetime
    updated_at: datetime
    processing_started_at: Optional[datetime]
    completed_at: Optional[datetime]
    worker_id: Optional[str]
    result: Optional[dict]

    @classmethod
    def from_record(cls, record) -> "QueueItem":
        """Create a QueueItem from a database record."""
        return cls(
            id=str(record["id"]),
            notes=record["notes"],
            status=record["status"],
            attempts=record["attempts"],
            max_attempts=record["max_attempts"],
            last_error=record["last_error"],
            submitted_energy_price_eur=float(record["submitted_energy_price_eur"]) if record["submitted_energy_price_eur"] else None,
            submitted_solar_available=record["submitted_solar_available"],
            submitted_llm_tier=record["submitted_llm_tier"],
            processed_energy_price_eur=float(record["processed_energy_price_eur"]) if record["processed_energy_price_eur"] else None,
            processed_solar_available=record["processed_solar_available"],
            processed_llm_tier=record["processed_llm_tier"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            processing_started_at=record["processing_started_at"],
            completed_at=record["completed_at"],
            worker_id=record["worker_id"],
            result=json.loads(record["result"]) if record["result"] else None,
        )


@dataclass
class DequeueResult:
    """Result from dequeuing an item."""
    id: str
    notes: str
    attempts: int
    submitted_llm_tier: Optional[str]


class DurableQueue:
    """
    PostgreSQL-backed durable queue for task processing.
    
    Features:
    - Persistent storage (survives pod restarts)
    - Atomic dequeue operations (safe for multiple workers)
    - Retry logic with configurable max attempts
    - Dead letter queue for failed items
    - Status tracking and monitoring
    """
    
    def __init__(self, worker_id: Optional[str] = None):
        """
        Initialize the durable queue.
        
        Args:
            worker_id: Unique identifier for this worker instance.
                      If not provided, a UUID will be generated.
        """
        self.worker_id = worker_id or str(uuid.uuid4())[:8]
        logger.info(f"DurableQueue initialized with worker_id: {self.worker_id}")
    
    async def enqueue(
        self,
        notes: str,
        energy_price_eur: Optional[float] = None,
        solar_available: Optional[bool] = None,
        llm_tier: Optional[str] = None,
        max_attempts: int = 3,
    ) -> str:
        """
        Add an item to the queue.
        
        Args:
            notes: The notes text to process
            energy_price_eur: Current energy price when submitted
            solar_available: Solar availability when submitted
            llm_tier: LLM tier determined at submission time
            max_attempts: Maximum retry attempts before moving to dead letter
        
        Returns:
            The UUID of the queued item
        """
        query = """
            INSERT INTO queue_items (
                notes,
                submitted_energy_price_eur,
                submitted_solar_available,
                submitted_llm_tier,
                max_attempts
            ) VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """
        
        item_id = await db.fetchval(
            query,
            notes,
            energy_price_eur,
            solar_available,
            llm_tier,
            max_attempts,
        )
        
        logger.info(f"Enqueued item {item_id} (notes: {notes[:30]}...)")
        return str(item_id)
    
    async def dequeue(self) -> Optional[DequeueResult]:
        """
        Atomically dequeue the next pending item.
        
        Uses PostgreSQL's SELECT FOR UPDATE SKIP LOCKED for safe
        concurrent access by multiple workers.
        
        Returns:
            DequeueResult if an item was available, None otherwise
        """
        query = "SELECT * FROM dequeue_item($1)"
        
        record = await db.fetchrow(query, self.worker_id)
        
        if record is None or record["item_id"] is None:
            return None
        
        result = DequeueResult(
            id=str(record["item_id"]),
            notes=record["item_notes"],
            attempts=record["item_attempts"],
            submitted_llm_tier=record["item_submitted_llm_tier"],
        )
        
        logger.info(f"Dequeued item {result.id} (attempt {result.attempts})")
        return result
    
    async def complete(
        self,
        item_id: str,
        result: dict,
        energy_price_eur: Optional[float] = None,
        solar_available: Optional[bool] = None,
        llm_tier: Optional[str] = None,
    ) -> bool:
        """
        Mark an item as successfully completed.
        
        Args:
            item_id: The UUID of the item
            result: The processing result (will be stored as JSON)
            energy_price_eur: Energy price at processing time
            solar_available: Solar availability at processing time
            llm_tier: LLM tier used for processing
        
        Returns:
            True if the item was marked as completed, False otherwise
        """
        query = "SELECT complete_item($1, $2, $3, $4, $5)"
        
        result_json = json.dumps(result)
        
        success = await db.fetchval(
            query,
            uuid.UUID(item_id),
            result_json,
            energy_price_eur,
            solar_available,
            llm_tier,
        )
        
        if success:
            logger.info(f"Completed item {item_id}")
        else:
            logger.warning(f"Failed to complete item {item_id} (not in processing state?)")
        
        return success
    
    async def fail(self, item_id: str, error: str) -> str:
        """
        Mark an item as failed.
        
        If the item has exceeded max_attempts, it will be moved to 'dead' status.
        Otherwise, it will be returned to 'pending' for retry.
        
        Args:
            item_id: The UUID of the item
            error: Error message describing the failure
        
        Returns:
            The new status ('pending' for retry, 'dead' if max attempts exceeded)
        """
        query = "SELECT fail_item($1, $2)"
        
        new_status = await db.fetchval(query, uuid.UUID(item_id), error)
        
        logger.warning(f"Failed item {item_id}: {error} (new status: {new_status})")
        return new_status
    
    async def recover_stale(self, timeout_minutes: int = 5) -> int:
        """
        Recover items stuck in 'processing' state.
        
        This handles cases where a worker crashed without completing or
        failing an item. Items older than timeout_minutes are returned
        to 'pending' (or 'dead' if max attempts exceeded).
        
        Args:
            timeout_minutes: Time after which processing items are considered stale
        
        Returns:
            Number of items recovered
        """
        query = "SELECT recover_stale_items($1)"
        
        count = await db.fetchval(query, timeout_minutes)
        
        if count > 0:
            logger.warning(f"Recovered {count} stale items")
        
        return count
    
    async def get_stats(self) -> dict:
        """
        Get queue statistics.
        
        Returns:
            Dictionary with counts by status and other metrics
        """
        query = "SELECT * FROM queue_stats"
        
        records = await db.fetch(query)
        
        stats = {
            "by_status": {},
            "total": 0,
        }
        
        for record in records:
            status = record["status"]
            count = record["count"]
            stats["by_status"][status] = {
                "count": count,
                "oldest_item": record["oldest_item"].isoformat() if record["oldest_item"] else None,
                "newest_item": record["newest_item"].isoformat() if record["newest_item"] else None,
                "avg_attempts": float(record["avg_attempts"]) if record["avg_attempts"] else 0,
            }
            stats["total"] += count
        
        return stats
    
    async def get_pending_count(self) -> int:
        """Get the number of pending items."""
        query = "SELECT COUNT(*) FROM queue_items WHERE status = 'pending'"
        return await db.fetchval(query)
    
    async def get_item(self, item_id: str) -> Optional[QueueItem]:
        """
        Get a specific item by ID.
        
        Args:
            item_id: The UUID of the item
        
        Returns:
            QueueItem if found, None otherwise
        """
        query = "SELECT * FROM queue_items WHERE id = $1"
        
        record = await db.fetchrow(query, uuid.UUID(item_id))
        
        if record is None:
            return None
        
        return QueueItem.from_record(record)
    
    async def get_recent_items(
        self,
        limit: int = 20,
        status: Optional[str] = None,
    ) -> List[QueueItem]:
        """
        Get recent queue items.
        
        Args:
            limit: Maximum number of items to return
            status: Filter by status (optional)
        
        Returns:
            List of QueueItem objects
        """
        if status:
            query = """
                SELECT * FROM queue_items 
                WHERE status = $1::queue_status
                ORDER BY created_at DESC 
                LIMIT $2
            """
            records = await db.fetch(query, status, limit)
        else:
            query = """
                SELECT * FROM queue_items 
                ORDER BY created_at DESC 
                LIMIT $1
            """
            records = await db.fetch(query, limit)
        
        return [QueueItem.from_record(r) for r in records]
    
    async def get_dead_letter_items(self, limit: int = 50) -> List[QueueItem]:
        """Get items in the dead letter queue."""
        return await self.get_recent_items(limit=limit, status="dead")
    
    async def retry_dead_item(self, item_id: str) -> bool:
        """
        Manually retry a dead letter item.
        
        Resets the item to 'pending' status with attempts reset to 0.
        
        Args:
            item_id: The UUID of the item
        
        Returns:
            True if successful, False otherwise
        """
        query = """
            UPDATE queue_items
            SET status = 'pending',
                attempts = 0,
                last_error = NULL,
                processing_started_at = NULL,
                worker_id = NULL
            WHERE id = $1 AND status = 'dead'
        """
        
        result = await db.execute(query, uuid.UUID(item_id))
        success = result == "UPDATE 1"
        
        if success:
            logger.info(f"Retried dead item {item_id}")
        
        return success
    
    async def purge_completed(self, older_than_hours: int = 24) -> int:
        """
        Purge completed items older than the specified time.
        
        Args:
            older_than_hours: Delete completed items older than this many hours
        
        Returns:
            Number of items deleted
        """
        query = """
            DELETE FROM queue_items
            WHERE status = 'completed'
              AND completed_at < NOW() - ($1 || ' hours')::INTERVAL
        """
        
        result = await db.execute(query, str(older_than_hours))
        
        # Parse "DELETE N" to get count
        try:
            count = int(result.split()[-1])
        except (ValueError, IndexError):
            count = 0
        
        if count > 0:
            logger.info(f"Purged {count} completed items older than {older_than_hours} hours")
        
        return count
    
    async def delete_item(self, item_id: str) -> bool:
        """Permanently remove an item from the queue."""
        pool = await db.get_pool()
        query = "DELETE FROM queue_items WHERE id = $1"
        try:
             result = await pool.execute(query, item_id)
             # execute returns e.g. "DELETE 1"
             return "DELETE 1" in result
        except Exception as e:
            logger.error(f"Failed to delete item {item_id}: {e}")
            return False
