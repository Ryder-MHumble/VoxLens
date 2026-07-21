from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.artifacts import AcquisitionBatch
    from app.models import RunLog


@dataclass
class ResearchBudget:
    """Track hard research limits and consumed acquisition or LLM resources."""

    max_sources: int = 50
    max_asr_minutes: int = 30
    max_llm_calls: int = 10
    max_llm_tokens: int = 50000
    max_elapsed_seconds: int = 300
    min_sources_for_synthesis: int = 3
    min_platforms_for_synthesis: int = 2
    sources_collected: int = 0
    asr_minutes_used: float = 0.0
    llm_calls_used: int = 0
    llm_tokens_used: int = 0
    _started_at: float = field(default_factory=time.monotonic, repr=False)

    @property
    def elapsed_seconds(self) -> float:
        """Return elapsed wall-clock time for the research run."""

        return max(0.0, time.monotonic() - self._started_at)

    @property
    def search_exhausted(self) -> bool:
        """Return whether source or elapsed-time limits prevent more acquisition."""

        return self.sources_collected >= self.max_sources or self.elapsed_seconds >= self.max_elapsed_seconds

    @property
    def llm_exhausted(self) -> bool:
        """Return whether call or token limits prevent another LLM call."""

        return self.llm_calls_used >= self.max_llm_calls or self.llm_tokens_used >= self.max_llm_tokens

    def set_sources_collected(self, count: int) -> None:
        """Record the current unique-source count without double counting retries."""

        self.sources_collected = max(0, min(count, self.max_sources))

    def record_llm_call(self, tokens: int = 0) -> None:
        """Record one completed provider attempt and its reported token usage."""

        self.llm_calls_used += 1
        self.llm_tokens_used += max(0, tokens)

    def remaining(self) -> float:
        """Return the most constrained remaining budget as a zero-to-one ratio."""

        ratios = (
            _ratio(self.max_sources - self.sources_collected, self.max_sources),
            _ratio(self.max_asr_minutes - self.asr_minutes_used, self.max_asr_minutes),
            _ratio(self.max_llm_calls - self.llm_calls_used, self.max_llm_calls),
            _ratio(self.max_llm_tokens - self.llm_tokens_used, self.max_llm_tokens),
            _ratio(self.max_elapsed_seconds - self.elapsed_seconds, self.max_elapsed_seconds),
        )
        return round(max(0.0, min(ratios)), 4)


class StopPolicy:
    """Make deterministic continue, stop, and platform-retry decisions."""

    def should_continue_search(self, batch: AcquisitionBatch, budget: ResearchBudget) -> bool:
        """Continue when coverage or evidence strength is low and search budget remains."""

        budget.set_sources_collected(len(batch.sources))
        if budget.search_exhausted:
            return False
        if len(batch.sources) < budget.min_sources_for_synthesis:
            return True
        platforms = {str(source.platform) for source in batch.sources}
        if len(platforms) < budget.min_platforms_for_synthesis:
            return True
        strong_or_moderate = sum(
            _source_quality(source) in {"Strong", "Moderate"}
            for source in batch.sources
        )
        return strong_or_moderate < min(2, budget.min_sources_for_synthesis)

    def should_stop_for_insufficient_evidence(self, batch: AcquisitionBatch) -> bool:
        """Stop when acquisition produced no usable evidence and no successful run."""

        if not batch.sources:
            return True
        usable = any(_source_quality(source) != "Insufficient" for source in batch.sources)
        successful_run = any(log.ok and log.count > 0 for log in batch.collection_logs)
        return not usable and not successful_run

    def should_retry_platform(self, platform: str, logs: list[RunLog]) -> bool:
        """Retry a platform once when it has not produced a successful non-empty run."""

        platform_logs = [log for log in logs if log.platform == platform]
        if not platform_logs or len(platform_logs) >= 2:
            return not platform_logs
        if any(log.ok and log.count > 0 for log in platform_logs):
            return False
        note = platform_logs[-1].note.lower()
        permanent_failure = any(term in note for term in ("unsupported", "permission denied", "invalid query"))
        return not permanent_failure


def _source_quality(source: object) -> str:
    """Read a categorical quality label from legacy Source fields."""

    quality = getattr(source, "quality", {}) or {}
    metrics = getattr(source, "metrics", {}) or {}
    return str(quality.get("label") or metrics.get("evidence_quality_label") or "Weak")


def _ratio(remaining: float, maximum: float) -> float:
    """Return a bounded remaining ratio, treating disabled limits as exhausted."""

    if maximum <= 0:
        return 0.0
    return max(0.0, min(1.0, remaining / maximum))
