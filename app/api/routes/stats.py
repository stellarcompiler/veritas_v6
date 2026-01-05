from fastapi import APIRouter
from app.core.redis import redis_client

router = APIRouter(prefix="/stats", tags=["stats"])

@router.get("/")
def stats():
    return redis_client.hgetall("stats:global")
