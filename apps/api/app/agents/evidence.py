from __future__ import annotations

import re
import time
from datetime import datetime

from app.models import AgentStep, Artifact, EvidenceQualityAssessment, EvidenceUnit, Source
from app.utils import text_excerpt

_DIMENSION_LABELS = (
    (0.8, "strong"),
    (0.6, "moderate"),
    (0.35, "weak"),
    (0.0, "insufficient"),
)
_QUALITY_RANK = {"Strong": 4, "Moderate": 3, "Weak": 2, "Insufficient": 1}


def prepare_evidence(sources: list[Source]) -> tuple[list[Source], AgentStep]:
    """Assess source evidence categorically and rank it without a pseudo-precise total."""

    started = time.perf_counter()
    for source in sources:
        channels = _evidence_channels(source)
        assessment = assess_evidence_quality(source)
        source.evidenceChannels = channels
        source.evidenceScore = 0
        source.metrics.pop("evidence_score", None)
        source.metrics["evidence_channels"] = channels
        source.metrics["evidence_quality_label"] = assessment.label
        source.metrics["evidence_quality_rank"] = _QUALITY_RANK[assessment.label]
        source.quality = assessment.model_dump()
        source.status = "weak" if assessment.label in {"Weak", "Insufficient"} else "ranked"
        if not source.summary:
            source.summary = text_excerpt(
                [source.title, source.transcriptPreview, *[comment.text for comment in source.comments[:3]]],
                300,
            )

    ranked = sorted(
        sources,
        key=lambda item: (
            int(item.metrics.get("evidence_quality_rank", 0)),
            int(item.metrics.get("relevance_score", item.relevanceScore)),
            bool(item.transcriptPreview),
        ),
        reverse=True,
    )
    label_counts = {
        label: sum(source.quality.get("label") == label for source in ranked)
        for label in _QUALITY_RANK
    }
    step = AgentStep(
        name="EvidenceStructuringAgent",
        role="Assesses relevance, directness, integrity, extraction confidence, credibility, independence and freshness.",
        status="ok" if ranked else "failed",
        message=f"Prepared {len(ranked)} sources with categorical evidence quality labels.",
        elapsedSec=round(time.perf_counter() - started, 3),
        metrics={
            "withComments": sum(1 for source in ranked if source.comments),
            "withTranscripts": sum(1 for source in ranked if source.transcriptPreview),
            "qualityLabels": label_counts,
        },
    )
    return ranked, step


def assess_evidence_quality(
    source: Source,
    *,
    claim_text: str = "",
    artifact: Artifact | None = None,
    evidence_unit: EvidenceUnit | None = None,
    research_start: datetime | None = None,
    research_end: datetime | None = None,
    independence_score: float | None = None,
) -> EvidenceQualityAssessment:
    """Assess evidence across seven auditable dimensions and return reasons plus a label."""

    dimensions = {
        "relevance": _relevance(source, claim_text, evidence_unit),
        "directness": _directness(source, evidence_unit),
        "integrity": _integrity(source, artifact, evidence_unit),
        "extraction_confidence": _extraction_confidence(source, evidence_unit),
        "source_credibility": _source_credibility(source),
        "independence": _independence(source, independence_score),
        "freshness": _freshness(source, research_start, research_end),
    }
    scores = {name: value[0] for name, value in dimensions.items()}
    average = sum(scores.values()) / len(scores)
    if scores["relevance"] < 0.35:
        label = "Insufficient"
    elif average >= 0.78 and min(scores["directness"], scores["integrity"]) >= 0.6:
        label = "Strong"
    elif average >= 0.58:
        label = "Moderate"
    elif average >= 0.38:
        label = "Weak"
    else:
        label = "Insufficient"

    reasons = [reason for _, reason in dimensions.values()]
    return EvidenceQualityAssessment(
        label=label,
        dimensions={name: _dimension_label(score) for name, score in scores.items()},
        reasons=reasons,
    )


def _evidence_channels(source: Source) -> list[str]:
    """Return the evidence modalities currently present on a legacy source object."""

    channels: list[str] = []
    if source.title:
        channels.append("title")
    if source.comments:
        channels.append("comments")
    if source.transcriptPreview or source.fullTranscript or source.transcriptText:
        channels.append("transcript")
    if source.url:
        channels.append("url")
    return channels


def _relevance(source: Source, claim_text: str, evidence_unit: EvidenceUnit | None) -> tuple[float, str]:
    """Estimate whether the available text directly addresses the claim."""

    if not claim_text:
        score = min(1.0, max(0.0, float(source.relevanceScore) / 100)) if source.relevanceScore else 0.65
        return score, "Relevance is based on retrieval ranking because no claim text was supplied."
    evidence_text = " ".join([
        source.title,
        source.summary,
        source.transcriptPreview,
        evidence_unit.text if evidence_unit else "",
    ])
    claim_terms = _terms(claim_text)
    evidence_terms = _terms(evidence_text)
    overlap = len(claim_terms & evidence_terms) / max(1, len(claim_terms))
    score = min(1.0, overlap * 1.5)
    return score, f"Relevance matched {len(claim_terms & evidence_terms)} of {len(claim_terms)} claim terms."


def _directness(source: Source, evidence_unit: EvidenceUnit | None) -> tuple[float, str]:
    """Prefer first-party speech, measured parameters and direct experience over retelling."""

    if evidence_unit and evidence_unit.modality in {"speech", "subtitle"}:
        return 0.9, "Directness is high because the unit is timestamped original speech or subtitle text."
    if evidence_unit and evidence_unit.modality == "ocr":
        return 0.8, "Directness is high because the unit captures on-screen information."
    if evidence_unit and evidence_unit.modality == "comment":
        return 0.55, "Directness is moderate because a comment may be first-hand but is not independently verified."
    if source.transcriptPreview or source.fullTranscript or source.transcriptText:
        return 0.75, "Directness is supported by source transcript content."
    if source.comments:
        return 0.45, "Directness is limited to sampled comments and source metadata."
    return 0.25, "Directness is weak because only title or summary metadata is available."


def _integrity(
    source: Source,
    artifact: Artifact | None,
    evidence_unit: EvidenceUnit | None,
) -> tuple[float, str]:
    """Assess whether immutable capture hashes and precise locations support auditability."""

    has_hash = bool(artifact and artifact.content_hash)
    has_location = bool(
        evidence_unit
        and (evidence_unit.start_ms is not None or evidence_unit.comment_id or evidence_unit.frame_index is not None)
    )
    if has_hash and has_location:
        return 0.95, "Integrity includes an immutable artifact hash and a precise evidence location."
    if has_hash:
        return 0.7, "Integrity includes an immutable artifact hash but no precise timestamp, comment, or frame location."
    if source.url:
        return 0.4, "Integrity has a source URL but no immutable artifact hash."
    return 0.15, "Integrity is insufficient because neither an artifact hash nor source URL is available."


def _extraction_confidence(source: Source, evidence_unit: EvidenceUnit | None) -> tuple[float, str]:
    """Assess confidence supplied by ASR, OCR, or deterministic text extraction."""

    if evidence_unit and evidence_unit.asr_confidence is not None:
        return evidence_unit.asr_confidence, f"Extraction confidence uses ASR confidence {evidence_unit.asr_confidence:.2f}."
    if evidence_unit and evidence_unit.ocr_confidence is not None:
        return evidence_unit.ocr_confidence, f"Extraction confidence uses OCR confidence {evidence_unit.ocr_confidence:.2f}."
    if evidence_unit and evidence_unit.modality in {"text", "comment", "metadata"}:
        return 0.85, "Extraction confidence is high for directly parsed text."
    if source.transcriptPreview:
        return 0.6, "Extraction confidence is moderate because transcript text has no segment-level confidence."
    return 0.5, "Extraction confidence is unknown because no extraction metadata is available."


def _source_credibility(source: Source) -> tuple[float, str]:
    """Assess creator identity signals and disclosed commercial-risk metadata."""

    sponsored = bool(source.metrics.get("sponsored") or source.metrics.get("commercial_risk"))
    verified = bool(source.metrics.get("creator_verified") or source.metrics.get("verified"))
    creator = source.creator or source.author
    if sponsored:
        return 0.35, "Source credibility is reduced by a sponsorship or commercial-risk signal."
    if verified:
        return 0.85, "Source credibility is strengthened by a verified creator identity signal."
    if creator:
        return 0.65, "Source credibility is moderate because the creator is named but not verified."
    return 0.35, "Source credibility is weak because the creator identity is absent."


def _independence(source: Source, explicit_score: float | None) -> tuple[float, str]:
    """Assess whether the source is independent from duplicate or coordinated content."""

    if explicit_score is not None:
        score = max(0.0, min(1.0, explicit_score))
        return score, f"Independence uses the supplied cluster assessment {score:.2f}."
    if source.metrics.get("duplicate_of") or source.metrics.get("repost"):
        return 0.2, "Independence is weak because the source is marked as a duplicate or repost."
    if source.metrics.get("independence_cluster"):
        return 0.7, "Independence is moderate because the source has been assigned to a provenance cluster."
    return 0.5, "Independence is unknown because cross-source provenance has not been assessed."


def _freshness(
    source: Source,
    research_start: datetime | None,
    research_end: datetime | None,
) -> tuple[float, str]:
    """Assess whether publication time falls inside the requested research window."""

    published = _parse_datetime(source.published)
    if not published:
        return 0.5, "Freshness is unknown because the publication date is missing or imprecise."
    if research_start and published < research_start:
        return 0.2, "Freshness is weak because the source predates the research window."
    if research_end and published > research_end:
        return 0.2, "Freshness is weak because the source falls after the research window."
    if research_start or research_end:
        return 0.9, "Freshness is strong because the source falls inside the research window."
    return 0.7, "Freshness is moderate because a publication date is available without an explicit window."


def _terms(text: str) -> set[str]:
    """Extract Latin tokens and Chinese bi-grams for lightweight relevance matching."""

    normalized = re.sub(r"\s+", " ", text.lower())
    terms = set(re.findall(r"[a-z0-9][a-z0-9+._-]*", normalized))
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    for run in chinese_runs:
        if len(run) == 1:
            terms.add(run)
        else:
            terms.update(run[index:index + 2] for index in range(len(run) - 1))
    return terms


def _parse_datetime(value: str) -> datetime | None:
    """Parse common ISO dates and standalone years without raising."""

    clean = value.strip()
    if not clean:
        return None
    try:
        return datetime.fromisoformat(clean.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        match = re.fullmatch(r"(20\d{2})", clean)
        return datetime(int(match.group(1)), 1, 1) if match else None


def _dimension_label(score: float) -> str:
    """Map an internal dimension value to a human-readable categorical label."""

    for threshold, label in _DIMENSION_LABELS:
        if score >= threshold:
            return label
    return "insufficient"
