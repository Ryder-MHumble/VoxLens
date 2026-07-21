from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from app.agents.coverage_gate import CoverageReport
from app.agents.grounding_verifier import ClaimVerification
from app.models import (
    Artifact,
    Claim,
    ClaimEvidence,
    EvidenceQualityAssessment,
    EvidenceQualityLabel,
    EvidenceUnit,
    ResearchReport,
    RunLog,
    Source,
)


@dataclass(frozen=True)
class PlanSpec:
    """Immutable normalized contract produced by the planning stage."""

    query: str
    entities: tuple[str, ...]
    comparison_targets: tuple[str, ...]
    time_range: str
    evidence_intents: tuple[str, ...]
    platform_queries: Mapping[str, str]

    def __post_init__(self) -> None:
        """Freeze the platform-query mapping at construction time."""

        object.__setattr__(self, "platform_queries", MappingProxyType(dict(self.platform_queries)))


@dataclass(frozen=True)
class AcquisitionBatch:
    """Immutable acquisition output containing snapshots, artifacts, and run logs."""

    sources: tuple[Source, ...]
    raw_artifacts: tuple[Artifact, ...]
    collection_logs: tuple[RunLog, ...]


@dataclass(frozen=True)
class EvidenceBatch:
    """Immutable evidence output with unit-level quality assessments."""

    evidence_units: tuple[EvidenceUnit, ...]
    quality_assessments: tuple[EvidenceQualityAssessment, ...]
    source_scores: Mapping[int, EvidenceQualityLabel]

    def __post_init__(self) -> None:
        """Freeze the source-score mapping at construction time."""

        object.__setattr__(self, "source_scores", MappingProxyType(dict(self.source_scores)))


@dataclass(frozen=True)
class ClaimSet:
    """Immutable synthesis output retaining all claim-to-evidence relations."""

    claims: tuple[Claim, ...]
    claim_evidence_links: tuple[ClaimEvidence, ...]
    coverage_report: CoverageReport


@dataclass(frozen=True)
class VerifiedReport:
    """Immutable final-stage output pairing the API report with verification metadata."""

    report: ResearchReport
    verification_results: tuple[ClaimVerification, ...]
    coverage_gate_passed: bool
    budget_remaining: float
