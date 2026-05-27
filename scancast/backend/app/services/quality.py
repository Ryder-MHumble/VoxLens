from __future__ import annotations

from collections import Counter

from app.models import QualityEvaluation, QualityMetric, ResearchReport


def evaluate_report_quality(report: ResearchReport) -> QualityEvaluation:
    source_ids = {source.id for source in report.sources}
    cited_ids = _all_citations(report)
    valid_citations = [source_id for source_id in cited_ids if source_id in source_ids]
    invalid_count = len(cited_ids) - len(valid_citations)
    uncited_claim_blocks = _uncited_claim_blocks(report)

    coverage_score = _coverage_score(report)
    citation_score = max(0, min(100, round((len(valid_citations) / max(1, len(cited_ids))) * 100) - uncited_claim_blocks * 8 - invalid_count * 15))
    evidence_score = _evidence_strength_score(report, valid_citations)
    conclusion_safety_score = _conclusion_safety_score(report, evidence_score, coverage_score, citation_score)
    overall = round((coverage_score + citation_score + evidence_score + conclusion_safety_score) / 4)

    warnings: list[str] = []
    if report.coverage.platformCount < 2:
        warnings.append("Only one platform has evidence; cross-platform consensus is weak.")
    if report.coverage.withComments + report.coverage.withTranscripts == 0:
        warnings.append("Most evidence is title/metadata only; conclusions should stay conservative.")
    if invalid_count:
        warnings.append(f"{invalid_count} citation reference(s) do not resolve to a source.")
    if uncited_claim_blocks:
        warnings.append(f"{uncited_claim_blocks} conclusion block(s) have no citation.")

    return QualityEvaluation(
        coverage=QualityMetric(
            score=coverage_score,
            label=_score_label(coverage_score),
            rationale=f"{report.coverage.totalSources} sources, {report.coverage.platformCount} platform(s), {report.coverage.totalComments} sampled comments.",
            sourceIds=sorted(set(valid_citations))[:8],
        ),
        citationAccuracy=QualityMetric(
            score=citation_score,
            label=_score_label(citation_score),
            rationale=f"{len(valid_citations)}/{max(1, len(cited_ids))} citations resolve to collected sources; {uncited_claim_blocks} claim blocks are uncited.",
            sourceIds=sorted(set(valid_citations))[:8],
        ),
        evidenceStrength=QualityMetric(
            score=evidence_score,
            label=_score_label(evidence_score),
            rationale=f"{report.coverage.withComments} source(s) include comments and {report.coverage.withTranscripts} include transcript/text evidence.",
            sourceIds=_top_evidence_sources(report),
        ),
        conclusionRisk=QualityMetric(
            score=conclusion_safety_score,
            label=_risk_label(conclusion_safety_score),
            rationale="Higher score means lower conclusion risk; penalizes sparse coverage, weak evidence and uncited claims.",
            sourceIds=sorted(set(valid_citations))[:8],
        ),
        overall=overall,
        warnings=warnings,
    )


def _coverage_score(report: ResearchReport) -> int:
    source_component = min(35, report.coverage.totalSources * 4)
    platform_component = min(25, report.coverage.platformCount * 8)
    comments_component = min(20, report.coverage.totalComments)
    transcript_component = min(20, report.coverage.withTranscripts * 8)
    return min(100, source_component + platform_component + comments_component + transcript_component)


def _evidence_strength_score(report: ResearchReport, valid_citations: list[int]) -> int:
    if not report.sources:
        return 0
    cited = {source_id for source_id in valid_citations}
    scored_sources = [source for source in report.sources if not cited or source.id in cited]
    avg_evidence = sum(source.evidenceScore for source in scored_sources) / max(1, len(scored_sources))
    channels = sum(1 for source in scored_sources if source.comments) + sum(1 for source in scored_sources if source.transcriptPreview)
    return min(100, round(avg_evidence * 1.6 + channels * 8 + min(20, len(scored_sources) * 2)))


def _conclusion_safety_score(report: ResearchReport, evidence_score: int, coverage_score: int, citation_score: int) -> int:
    base = round(evidence_score * 0.35 + coverage_score * 0.25 + citation_score * 0.4)
    if report.confidence in {"low", "insufficient"}:
        base -= 10
    if report.status in {"partial", "failed"}:
        base -= 8
    return max(0, min(100, base))


def _all_citations(report: ResearchReport) -> list[int]:
    citations: list[int] = []
    for item in report.takeaways:
        citations.extend(item.citations)
    for insight in report.insights:
        citations.extend(insight.sourceIds)
    for section in report.sections:
        citations.extend(section.sourceIds)
        for bullet in section.bullets:
            citations.extend(bullet.citations)
        for row in section.table:
            citations.extend(row.evidence)
        if section.quote:
            citations.append(section.quote.sourceId)
    return citations


def _uncited_claim_blocks(report: ResearchReport) -> int:
    count = sum(1 for item in report.takeaways if item.text and not item.citations)
    for section in report.sections:
        if section.kind in {"answer", "narrative", "consensus_disagreement"} and section.body and not section.sourceIds and not any(b.citations for b in section.bullets):
            count += 1
        count += sum(1 for bullet in section.bullets if bullet.text and not bullet.citations)
    return count


def _top_evidence_sources(report: ResearchReport) -> list[int]:
    return [
        source.id
        for source in sorted(report.sources, key=lambda item: (item.evidenceScore, item.citationCount), reverse=True)[:8]
    ]


def _score_label(score: int) -> str:
    if score >= 80:
        return "strong"
    if score >= 55:
        return "medium"
    if score >= 30:
        return "weak"
    return "insufficient"


def _risk_label(score: int) -> str:
    if score >= 80:
        return "low risk"
    if score >= 55:
        return "medium risk"
    if score >= 30:
        return "high risk"
    return "very high risk"
