import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, (dict, list, tuple)):
        try:
            json.dumps(value)
        except TypeError:
            return str(value)
        return value
    return str(value)
