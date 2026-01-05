def log_event(job_id: str, event: dict):
    """
    Stores ONLY agent-relevant events.
    """
    from .redis import redis_client

    redis_client.rpush(
        f"job:{job_id}:logs",
        event
    )
