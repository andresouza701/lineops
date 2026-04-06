from __future__ import annotations

import json
import logging
import uuid
from typing import Any


LOGGER = logging.getLogger("whatsapp.integration")


def ensure_correlation_id(raw_value: str | None = None) -> str:
    value = (raw_value or "").strip()
    if value:
        return value[:64]
    return uuid.uuid4().hex


def emit_integration_log(
    event: str,
    *,
    correlation_id: str,
    **payload: Any,
) -> None:
    LOGGER.info(
        json.dumps(
            {
                "event": event,
                "correlation_id": correlation_id,
                **payload,
            },
            ensure_ascii=True,
            default=str,
            sort_keys=True,
        )
    )
