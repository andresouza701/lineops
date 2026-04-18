from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID


class StructuredJSONFormatter(logging.Formatter):
    """Render log records as JSON while preserving extra contextual fields."""

    _reserved_keys = frozenset(logging.makeLogRecord({}).__dict__.keys()) | {
        "message",
        "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        payload.update(self._extract_extra_fields(record))

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False, default=self._default_serializer)

    @classmethod
    def _extract_extra_fields(cls, record: logging.LogRecord) -> dict[str, object]:
        extra: dict[str, object] = {}
        for key, value in record.__dict__.items():
            if key in cls._reserved_keys or key.startswith("_"):
                continue
            extra[key] = value
        return extra

    @staticmethod
    def _default_serializer(value: object) -> object:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (date, time)):
            return value.isoformat()
        if isinstance(value, (UUID, Decimal)):
            return str(value)
        if isinstance(value, set):
            return sorted(value)
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
            return list(value)
        return str(value)
