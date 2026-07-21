from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.artifacts import AcquisitionBatch, PlanSpec
    from app.agents.budget import ResearchBudget


_COUNTEREVIDENCE_TERMS = (
    "缺点",
    "问题",
    "不足",
    "风险",
    "投诉",
    "吐槽",
    "避坑",
    "反对",
    "不推荐",
    "差",
    "issue",
    "problem",
    "risk",
    "complaint",
    "downside",
    "negative",
    "not recommend",
)


@dataclass(frozen=True)
class CoverageReport:
    """Describe plan coverage and whether counterevidence survived acquisition."""

    platforms_covered: tuple[str, ...]
    entities_covered: tuple[str, ...]
    evidence_modalities_found: tuple[str, ...]
    missing_platforms: tuple[str, ...]
    missing_entities: tuple[str, ...]
    counterevidence_found: bool
    counterevidence_sources: tuple[int, ...]

    @property
    def is_sufficient(self) -> bool:
        """Return whether all explicitly planned dimensions are covered."""

        return not self.missing_platforms and not self.missing_entities


class CoverageGate:
    """Evaluate source coverage before source selection or report synthesis."""

    def evaluate(self, batch: AcquisitionBatch, plan: PlanSpec) -> CoverageReport:
        """Evaluate entity, platform, evidence-type, and counterevidence coverage."""

        platforms = tuple(sorted({str(source.platform) for source in batch.sources}))
        searchable = {
            source.id: _source_text(source)
            for source in batch.sources
        }
        entities = tuple(
            entity
            for entity in plan.entities
            if any(_contains(text, entity) for text in searchable.values())
        )
        evidence_modalities = tuple(sorted({
            modality
            for source in batch.sources
            for modality in _source_evidence_modalities(source)
        }))
        counterevidence_sources = tuple(sorted(
            source_id
            for source_id, text in searchable.items()
            if any(term in text for term in _COUNTEREVIDENCE_TERMS)
        ))
        planned_platforms = tuple(plan.platform_queries)
        return CoverageReport(
            platforms_covered=platforms,
            entities_covered=entities,
            evidence_modalities_found=evidence_modalities,
            missing_platforms=tuple(platform for platform in planned_platforms if platform not in platforms),
            missing_entities=tuple(entity for entity in plan.entities if entity not in entities),
            counterevidence_found=bool(counterevidence_sources),
            counterevidence_sources=counterevidence_sources,
        )

    def should_block_synthesis(self, report: CoverageReport, budget: ResearchBudget) -> bool:
        """Block synthesis only when a severe gap remains and search budget exists."""

        if budget.search_exhausted:
            return False
        if len(report.platforms_covered) < budget.min_platforms_for_synthesis:
            return True
        if report.missing_entities and not report.entities_covered:
            return True
        return not report.evidence_modalities_found

    def identify_gaps(self, report: CoverageReport, plan: PlanSpec) -> list[str]:
        """Return concrete acquisition gaps suitable for retry planning."""

        gaps = [f"platform:{platform}" for platform in report.missing_platforms]
        gaps.extend(f"entity:{entity}" for entity in report.missing_entities)
        missing_intents = [
            intent
            for intent in plan.evidence_intents
            if not _intent_is_covered(intent, report.evidence_modalities_found)
        ]
        gaps.extend(f"evidence_intent:{intent}" for intent in missing_intents)
        if not report.counterevidence_found:
            gaps.append("counterevidence")
        return gaps


def _source_text(source: object) -> str:
    """Build normalized searchable text from a Source-like object."""

    comments = getattr(source, "comments", [])
    parts = [
        getattr(source, "title", ""),
        getattr(source, "summary", ""),
        getattr(source, "transcriptPreview", ""),
        getattr(source, "fullTranscript", ""),
        *[getattr(comment, "text", "") for comment in comments],
    ]
    return " ".join(str(part).strip().lower() for part in parts if str(part).strip())


def _contains(text: str, value: str) -> bool:
    """Match an entity case-insensitively without tokenization dependencies."""

    return value.strip().lower() in text if value.strip() else False


def _source_evidence_modalities(source: object) -> set[str]:
    """Infer available evidence modalities from a Source-like object."""

    evidence_types = set(getattr(source, "evidenceChannels", []) or [])
    if getattr(source, "title", "") or getattr(source, "summary", ""):
        evidence_types.add("text")
    if getattr(source, "transcriptPreview", "") or getattr(source, "fullTranscript", ""):
        evidence_types.add("speech")
    if getattr(source, "comments", []):
        evidence_types.add("comment")
    metrics = getattr(source, "metrics", {}) or {}
    if metrics.get("ocr_text") or metrics.get("ocr_confidence"):
        evidence_types.add("ocr")
    return evidence_types


def _intent_is_covered(intent: str, modalities: tuple[str, ...]) -> bool:
    """Map search intent to the evidence modalities that can satisfy it."""

    expected = {
        "review": {"speech", "subtitle", "text", "ocr"},
        "complaint": {"comment", "speech", "subtitle", "text"},
        "recommendation": {"speech", "subtitle", "text", "comment"},
        "comparison": {"speech", "subtitle", "text", "ocr"},
    }.get(intent, {intent})
    return bool(expected & set(modalities))
