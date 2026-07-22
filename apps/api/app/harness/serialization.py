from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel


def jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return jsonable(value.model_dump(mode="python"))
    if is_dataclass(value):
        return {
            field.name: jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = _mapping_key(key)
            if normalized_key in normalized:
                raise ValueError(f"Harness mapping key collision: {normalized_key!r}")
            normalized[normalized_key] = jsonable(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [jsonable(item) for item in value]
        return sorted(normalized, key=_canonical_json)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported harness value type: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _mapping_key(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    raise TypeError(f"Unsupported harness mapping key type: {type(value).__name__}")


def payload_hash(payload: Any) -> str:
    encoded = json.dumps(
        jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
