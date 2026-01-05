"""
Redis Safety Utilities

Purpose:
- Guarantee Redis-compatible data types
- Prevent runtime DataError crashes
- Enforce predictable serialization across the codebase

Redis accepts ONLY:
str | int | float | bytes

Anything else MUST be serialized explicitly.
"""

import json
from typing import Any, Dict


# ---------------------------
# Primitive Safety
# ---------------------------

def redis_safe(value: Any) -> str | int | float | bytes:
    """
    Convert arbitrary Python values into Redis-safe types.

    Rules:
    - None       -> empty string
    - str/int/float/bytes -> pass through
    - bool       -> "true" / "false"
    - dict/list/tuple -> JSON string
    - everything else -> str(value)
    """
    if value is None:
        return ""

    if isinstance(value, (str, int, float, bytes)):
        return value

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)

    return str(value)


# ---------------------------
# Mapping Safety
# ---------------------------

def redis_safe_mapping(data: Dict[str, Any]) -> Dict[str, str | int | float | bytes]:
    """
    Convert a dictionary into a Redis-safe mapping.

    Use this BEFORE hset(mapping=...).
    """
    return {k: redis_safe(v) for k, v in data.items()}


# ---------------------------
# List Safety
# ---------------------------

def redis_safe_list(values: list[Any]) -> list[str | int | float | bytes]:
    """
    Convert a list into Redis-safe values.
    Useful before rpush/lpush.
    """
    return [redis_safe(v) for v in values]
