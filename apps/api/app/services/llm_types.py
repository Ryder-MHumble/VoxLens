from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models import CitationText, ReportInsight, ReportSection, Source


@dataclass
class LlmSynthesisResult:
    takeaways: list[CitationText] = field(default_factory=list)
    insights: list[ReportInsight] = field(default_factory=list)
    sections: list[ReportSection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model: str = ""


@dataclass
class SourceSelectionResult:
    sources: list[Source] = field(default_factory=list)
    source_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model: str = ""


@dataclass
class SemanticEvidenceExtraction:
    candidate: str
    dimension: str
    conclusion: str
    scenario: str = ""
    value: str = ""
    quote: str = ""
    sourceId: int = 0
    confidence: int = 3


@dataclass
class SemanticEvidenceExtractionResult:
    evidence: list[SemanticEvidenceExtraction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model: str = ""


@dataclass
class DecisionAttributeExtractionResult:
    products: dict[str, dict[str, list[dict[str, Any]]]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    model: str = ""


@dataclass
class DecisionContradictionResult:
    contradictions: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    model: str = ""
