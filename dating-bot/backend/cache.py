"""
cache.py - Управление кэшем анкет в Redis
"""
import redis
import json
from typing import List, Dict, Any, Optional
from config import REDIS_URL

r = redis.from_url(REDIS_URL, decode_responses=True)
QUEUE_PREFIX = "dating:queue:"

def get_queue_key(user_id: int) -> str:
    return f"{QUEUE_PREFIX}{user_id}"

def push_profiles_to_queue(user_id: int, profiles_data: List[Dict[str, Any]]):
    key = get_queue_key(user_id)
    r.delete(key)
    if profiles_data:
        serialized = [json.dumps(p) for p in profiles_data]
        r.rpush(key, *serialized)
        r.expire(key, 3600)

def pop_next_profile(user_id: int) -> Optional[Dict[str, Any]]:
    key = get_queue_key(user_id)
    data = r.lpop(key)
    return json.loads(data) if data else None

def clear_queue(user_id: int):
    r.delete(get_queue_key(user_id))

def clear_all_queues():
    """Очищает все очереди (вызывается при создании новой анкеты)"""
    try:
        keys = r.keys(f"{QUEUE_PREFIX}*")
        if keys:
            r.delete(*keys)
            print(f"🗑️ Очищено {len(keys)} очередей в Redis")
    except redis.RedisError:
        # Если Redis временно недоступен, просто продолжаем без кэша.
        return

def get_queue_stats(user_id: int) -> Dict[str, Any]:
    key = get_queue_key(user_id)
    return {"queue_length": r.llen(key), "ttl_seconds": r.ttl(key), "is_empty": r.llen(key) == 0}