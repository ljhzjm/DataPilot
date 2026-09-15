import json
from typing import Any

from app.chat.runtime import RuntimeEvent


def encode_sse(event: RuntimeEvent, *, event_name: str | None = None) -> str:
    event_type = event_name or event.type.value
    return encode_sse_data(event_type, event.model_dump(mode="json"))


def encode_sse_data(
    event_name: str,
    payload: dict[str, Any],
    *,
    event_id: str | None = None,
) -> str:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    id_line = f"id: {event_id}\n" if event_id else ""
    return f"{id_line}event: {event_name}\ndata: {data}\n\n"
