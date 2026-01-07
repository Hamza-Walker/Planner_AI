from collections import deque
import asyncio
from typing import Optional, Deque, Dict, Any
from codecarbon import EmissionsTracker
from storage.durable_queue import DurableQueue
from storage.google_auth import GoogleAuthStore
import os

# In-memory storage for recent tasks (for display purposes)
recent_tasks: Deque[Dict[str, Any]] = deque(maxlen=100)

# In-memory storage for recent schedules (keyed by date string)
recent_schedules: Dict[str, Dict[str, Any]] = {}

# Legacy in-memory queue (used when USE_DURABLE_QUEUE=false)
notes_queue: asyncio.Queue[str] = asyncio.Queue()

# Global instances initialized at startup
durable_queue: Optional[DurableQueue] = None
google_auth_store: Optional[GoogleAuthStore] = None

# CodeCarbon tracker configuration
PROMETHEUS_PUSH_URL = os.getenv("PROMETHEUS_PUSH_URL", "")
tracker = EmissionsTracker(
    project_name="planner-ai-backend",
    save_to_prometheus=bool(PROMETHEUS_PUSH_URL),
    prometheus_url=PROMETHEUS_PUSH_URL or "http://localhost:9091",
    log_level="error",
)
