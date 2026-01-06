"""
Database connection module for Planner AI.

Provides async PostgreSQL connection pool using asyncpg.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# Database configuration from environment variables
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://planner:planner_secret_2026@postgres:5432/planner_ai"
)

# Connection pool singleton
_pool: Optional[asyncpg.Pool] = None


async def init_db_pool(
    min_size: int = 2,
    max_size: int = 10,
    command_timeout: float = 60.0,
) -> asyncpg.Pool:
    """
    Initialize the database connection pool.
    
    Should be called once at application startup.
    """
    global _pool
    
    if _pool is not None:
        logger.warning("Database pool already initialized")
        return _pool
    
    logger.info(f"Initializing database pool (min={min_size}, max={max_size})")
    
    try:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
        )
        logger.info("Database pool initialized successfully")
        return _pool
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise


async def close_db_pool() -> None:
    """
    Close the database connection pool.
    
    Should be called at application shutdown.
    """
    global _pool
    
    if _pool is None:
        logger.warning("Database pool not initialized, nothing to close")
        return
    
    logger.info("Closing database pool")
    await _pool.close()
    _pool = None
    logger.info("Database pool closed")


def get_pool() -> asyncpg.Pool:
    """
    Get the database connection pool.
    
    Raises RuntimeError if pool is not initialized.
    """
    if _pool is None:
        raise RuntimeError(
            "Database pool not initialized. Call init_db_pool() first."
        )
    return _pool


@asynccontextmanager
async def get_connection():
    """
    Async context manager to acquire a connection from the pool.
    
    Usage:
        async with get_connection() as conn:
            result = await conn.fetch("SELECT * FROM queue_items")
    """
    pool = get_pool()
    async with pool.acquire() as connection:
        yield connection


async def execute(query: str, *args) -> str:
    """Execute a query and return the status."""
    async with get_connection() as conn:
        return await conn.execute(query, *args)


async def fetch(query: str, *args) -> list:
    """Execute a query and return all results."""
    async with get_connection() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args):
    """Execute a query and return the first row."""
    async with get_connection() as conn:
        return await conn.fetchrow(query, *args)


async def fetchval(query: str, *args):
    """Execute a query and return the first column of the first row."""
    async with get_connection() as conn:
        return await conn.fetchval(query, *args)


async def init_schema() -> None:
    """
    Initialize the database schema.
    
    Reads and executes the schema.sql file.
    """
    import pathlib
    
    schema_path = pathlib.Path(__file__).parent / "schema.sql"
    
    if not schema_path.exists():
        logger.error(f"Schema file not found: {schema_path}")
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    logger.info(f"Initializing database schema from {schema_path}")
    
    schema_sql = schema_path.read_text()
    
    async with get_connection() as conn:
        await conn.execute(schema_sql)
    
    logger.info("Database schema initialized successfully")


async def health_check() -> dict:
    """
    Check database connectivity and return health status.
    """
    try:
        result = await fetchval("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected",
            "pool_size": _pool.get_size() if _pool else 0,
            "pool_free": _pool.get_idle_size() if _pool else 0,
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }
