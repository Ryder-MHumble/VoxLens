"""Search result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchItem:
    platform: str
    title: str
    url: str
    provider: str
    author: str = ""
    published: str = ""
    duration: str = ""
    summary_text: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def compact_metrics(self) -> str:
        parts: list[str] = []
        for key, value in self.metrics.items():
            if value not in (None, "", [], {}):
                parts.append(f"{key}: {value}")
        return "; ".join(parts)


@dataclass(slots=True)
class ProviderRun:
    provider: str
    platform: str
    query: str
    command: list[str] = field(default_factory=list)
    ok: bool = False
    items: list[SearchItem] = field(default_factory=list)
    elapsed_sec: float = 0.0
    stderr: str = ""
    note: str = ""

    @property
    def count(self) -> int:
        return len(self.items)
