import asyncio
import logging
import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from api import state
from api.workers import _durable_queue_worker, _stale_recovery_worker, _queue_worker
from storage import db
from storage.durable_queue import DurableQueue
from storage.google_auth import GoogleAuthStore
from api.routers import auth, notes, queue, tasks, ops

# Logging configuration
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

# App Init
app = FastAPI(title="Planner AI", version="0.9.0")

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for dev/minikube environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
USE_DURABLE_QUEUE = os.getenv("USE_DURABLE_QUEUE", "true").lower() in {
    "1",
    "true",
    "yes",
}

# Include Routers
app.include_router(auth.router)
app.include_router(notes.router)
app.include_router(
    queue.router, prefix="/queue", tags=["queue"]
)  # Prefix only for generic queue items, /queue status is in router
app.include_router(tasks.router)
app.include_router(ops.router)


@app.on_event("startup")
async def startup() -> None:
    # Initialize DB connection
    await db.init_db_pool()
    await db.init_schema()

    # Initialize Durable Queue
    if USE_DURABLE_QUEUE:
        state.durable_queue = DurableQueue()
        # Start background workers...
        asyncio.create_task(_durable_queue_worker())
        asyncio.create_task(_stale_recovery_worker())
    else:
        # Start legacy in-memory worker
        asyncio.create_task(_queue_worker())

    # Initialize Google Auth Store
    state.google_auth_store = GoogleAuthStore()

    # Start CodeCarbon tracking if not already started
    try:
        state.tracker.start()
        logger.info("CodeCarbon tracker started")
    except Exception as e:
        logger.error(f"Failed to start CodeCarbon tracker: {e}")


@app.on_event("shutdown")
async def shutdown() -> None:
    """Graceful shutdown - close database connections."""
    logger.info("Shutting down...")

    # Stop CodeCarbon
    try:
        state.tracker.stop()
        time.sleep(5)  # Allow HTTP push to complete
        logger.info("CodeCarbon metrics pushed successfully")
    except Exception as e:
        logger.error(f"Error stopping CodeCarbon tracker: {e}")

    if USE_DURABLE_QUEUE:
        try:
            await db.close_db_pool()
            logger.info("Database pool closed")
        except Exception as e:
            logger.error(f"Error closing database pool: {e}")
