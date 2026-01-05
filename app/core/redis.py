import redis
from veritas.config import Config

redis_client = redis.Redis(
    host="localhost",
    port=6379,
    decode_responses=True
)
