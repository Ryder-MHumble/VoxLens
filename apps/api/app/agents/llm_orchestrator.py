from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Callable

from app.agents.budget import ResearchBudget


@dataclass(frozen=True)
class LLMCallSpec:
    """Describe one named LLM stage and its execution policy."""

    name: str
    max_tokens: int
    max_retries: int = 2
    timeout_seconds: int = 90
    fallback: str = "deterministic"


class LLMOrchestrator:
    """Execute optional LLM calls with shared budgets, retries, and fallbacks."""

    def __init__(
        self,
        budget: ResearchBudget,
        llm_provider: Callable[[LLMCallSpec, dict[str, Any]], Any] | None = None,
    ):
        """Initialize the orchestrator with a shared mutable budget ledger."""

        self._budget = budget
        self._llm_provider = llm_provider
        self._call_count = budget.llm_calls_used
        self._total_tokens = budget.llm_tokens_used

    async def execute(
        self,
        spec: LLMCallSpec,
        inputs: dict[str, Any],
        fallback_fn: Callable[..., Any],
    ) -> Any:
        """Execute one provider call within budget, retry, timeout, and fallback limits."""

        if self._llm_provider is None or not self._can_execute(spec):
            return await _invoke_fallback(fallback_fn, inputs)

        for _ in range(spec.max_retries + 1):
            if not self._can_execute(spec):
                break
            self._call_count += 1
            self._budget.record_llm_call()
            try:
                result = self._llm_provider(spec, inputs)
                if inspect.isawaitable(result):
                    result = await asyncio.wait_for(result, timeout=spec.timeout_seconds)
                tokens = _token_usage(result) or spec.max_tokens
                self._total_tokens += tokens
                self._budget.llm_tokens_used += tokens
                if self._total_tokens > self._budget.max_llm_tokens:
                    break
                return result
            except Exception:  # noqa: BLE001, PERF203
                continue
        return await _invoke_fallback(fallback_fn, inputs)

    def remaining_budget(self) -> dict[str, int]:
        """Return remaining provider calls and tokens."""

        return {
            "llm_calls": max(0, self._budget.max_llm_calls - self._call_count),
            "llm_tokens": max(0, self._budget.max_llm_tokens - self._total_tokens),
        }

    def _can_execute(self, spec: LLMCallSpec) -> bool:
        """Return whether the next call can fit inside declared hard limits."""

        calls_left = self._budget.max_llm_calls - self._call_count
        tokens_left = self._budget.max_llm_tokens - self._total_tokens
        return calls_left > 0 and tokens_left >= spec.max_tokens and not self._budget.llm_exhausted


async def _invoke_fallback(fallback_fn: Callable[..., Any], inputs: dict[str, Any]) -> Any:
    """Invoke a deterministic fallback that may accept inputs or no arguments."""

    try:
        inspect.signature(fallback_fn).bind(inputs)
    except (TypeError, ValueError):
        result = fallback_fn()
    else:
        result = fallback_fn(inputs)
    if inspect.isawaitable(result):
        return await result
    return result


def _token_usage(result: Any) -> int:
    """Extract common token-usage shapes without coupling to one provider SDK."""

    if isinstance(result, dict):
        usage = result.get("usage", {})
        if isinstance(usage, dict):
            return int(usage.get("total_tokens") or usage.get("tokens") or 0)
        return int(result.get("total_tokens") or 0)
    usage = getattr(result, "usage", None)
    if usage is not None:
        return int(getattr(usage, "total_tokens", 0) or 0)
    return 0
