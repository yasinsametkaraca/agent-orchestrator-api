from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def start_timer() -> float:
    return time.perf_counter()


def stop_timer(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def as_dict(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return dict(obj)
