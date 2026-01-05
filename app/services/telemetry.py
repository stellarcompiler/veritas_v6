"""
Telemetry & Metrics Aggregation Layer for Veritas

Responsibilities:
- Maintain global system statistics
- Provide atomic, Redis-backed counters
- Stay write-only from execution path (no blocking reads)
- Be safe under concurrent FastAPI workers
"""
import json
from typing import Dict
from datetime import datetime
from app.core.redis import redis_client
from veritas.config import logger
from app.core.redis_utils import redis_safe

# ----------- Redis Keys (Centralized) -----------

GLOBAL_STATS_KEY = "stats:global"


# ----------- Initialization -----------

def init_telemetry() -> None:
    """
    Initialize telemetry counters if they don't exist.
    Safe to call multiple times.
    """
    try:
        if not redis_client.exists(GLOBAL_STATS_KEY):
            redis_client.hset(
                GLOBAL_STATS_KEY,
                mapping={
                    "claims_analyzed": 0,
                    "jobs_completed": 0,
                    "jobs_failed": 0,
                    "urls_scraped": 0,
                    "last_updated": datetime.utcnow().isoformat()
                }
            )
            logger.info("Telemetry initialized")
    except Exception as e:
        logger.error(f"Telemetry init failed: {e}")


# ----------- Increment Helpers -----------

def increment_claims(count: int = 1) -> None:
    _safe_incr("claims_analyzed", count)


def increment_jobs_completed() -> None:
    _safe_incr("jobs_completed", 1)


def increment_jobs_failed() -> None:
    _safe_incr("jobs_failed", 1)


def increment_urls_scraped(count: int) -> None:
    _safe_incr("urls_scraped", count)


def _safe_incr(field: str, value: int) -> None:
    """
    Atomic Redis increment with timestamp update.
    Never raises to caller.
    """
    try:
        redis_client.hincrby(GLOBAL_STATS_KEY, field, value)
        redis_client.hset(
            GLOBAL_STATS_KEY,
            "last_updated",
            datetime.utcnow().isoformat()
        )
    except Exception as e:
        logger.error(f"Telemetry increment failed [{field}]: {e}")


# ----------- Read API -----------

def get_global_stats() -> Dict[str, str]:
    """
    Returns system-wide telemetry snapshot.
    Used by /stats endpoint.
    """
    try:
        return redis_client.hgetall(GLOBAL_STATS_KEY)
    except Exception as e:
        logger.error(f"Failed to fetch telemetry: {e}")
        return {
            "error": "Telemetry unavailable"
        }


def log_event(
    job_id: str,
    source: str,
    event_type: str,
    message: str,
    meta: dict | None = None
):
    payload = {
        "ts": datetime.utcnow().isoformat(),
        "source": source,          # agent / tool name
        "type": event_type,        # START, END, TOOL_CALL, ERROR
        "message": message,
        "meta": meta or {}
    }

    redis_client.rpush(
        f"job:{job_id}:logs",
        redis_safe(json.dumps(payload))
    )