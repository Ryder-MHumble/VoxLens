from __future__ import annotations

import time

from app.models import AgentStep, Source
from app.utils import text_excerpt


def prepare_evidence(sources: list[Source]) -> tuple[list[Source], AgentStep]:
    started = time.perf_counter()
    for source in sources:
        channels = []
        if source.title:
            channels.append("title")
        if source.comments:
            channels.append("comments")
        if source.transcriptPreview:
            channels.append("transcript")
        if source.url:
            channels.append("url")
        evidence_score = len(source.comments) * 2 + (8 if source.transcriptPreview else 0) + (3 if source.url else 0)
        source.evidenceScore = min(100, evidence_score)
        source.evidenceChannels = channels
        source.metrics["evidence_score"] = evidence_score
        source.metrics["evidence_channels"] = channels
        source.quality = {
            "evidenceScore": source.evidenceScore,
            "hasComments": bool(source.comments),
            "hasTranscript": bool(source.transcriptPreview),
            "channelCount": len(channels),
        }
        source.status = "weak" if source.evidenceScore < 5 else "ranked"
        if not source.summary:
            source.summary = text_excerpt([source.title, source.transcriptPreview, *[c.text for c in source.comments[:3]]], 300)

    ranked = sorted(
        sources,
        key=lambda item: (item.metrics.get("evidence_score", 0), len(item.comments), bool(item.transcriptPreview)),
        reverse=True,
    )
    step = AgentStep(
        name="EvidenceStructuringAgent",
        role="Scores each source by comments, transcript availability and citation readiness.",
        status="ok" if ranked else "failed",
        message=f"Prepared {len(ranked)} sources for report synthesis.",
        elapsedSec=round(time.perf_counter() - started, 3),
        metrics={
            "withComments": sum(1 for s in ranked if s.comments),
            "withTranscripts": sum(1 for s in ranked if s.transcriptPreview),
        },
    )
    return ranked, step
