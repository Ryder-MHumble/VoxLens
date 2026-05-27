from __future__ import annotations

from typing import Protocol

from app.models import CrawlTarget, ResearchRequest, RunLog, Source


class ProviderAdapter(Protocol):
    """Boundary for local/dev crawlers and production provider replacements."""

    name: str

    def available(self) -> bool:
        ...

    def search(self, request: ResearchRequest, target: CrawlTarget) -> tuple[list[Source], RunLog]:
        ...
