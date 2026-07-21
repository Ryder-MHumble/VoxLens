from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.agents.evidence import assess_evidence_quality  # noqa: E402
from app.agents.planner import analyze_research_question, build_research_plan  # noqa: E402
from app.models import Artifact, Claim, ClaimEvidence, EvidenceUnit, ResearchRequest, Source  # noqa: E402
from app.services.asr_pipeline import (  # noqa: E402
    ASRPipeline,
    ASRSegment,
    AudioAsset,
    InMemoryASRCache,
    MediaInput,
    PermissionDecision,
    SpeechRegion,
)
from app.services.citation import (  # noqa: E402
    build_citation_link,
    format_citation,
    parse_citation,
    resolve_evidence_unit,
)


class MockPermissionChecker:
    """Record and approve permission checks for offline orchestration tests."""

    def __init__(self, calls: list[str]) -> None:
        """Store the shared call trace."""

        self.calls = calls

    def check(self, media: MediaInput) -> PermissionDecision:
        """Approve the mock media input without network access."""

        self.calls.append("permission")
        return PermissionDecision(True, "mock approved")


class MockAudioExtractor:
    """Record audio extraction without invoking ffmpeg."""

    def __init__(self, calls: list[str]) -> None:
        """Store the shared call trace."""

        self.calls = calls

    def extract(self, media: MediaInput) -> AudioAsset:
        """Return a synthetic audio asset."""

        self.calls.append("extract")
        return AudioAsset(path="/tmp/mock.wav", source_media=media.value, command=("ffmpeg",))


class MockVADProvider:
    """Record VAD and return two deterministic speech regions."""

    def __init__(self, calls: list[str]) -> None:
        """Store the shared call trace."""

        self.calls = calls

    def detect(self, audio: AudioAsset) -> list[SpeechRegion]:
        """Return deterministic regions without reading audio bytes."""

        self.calls.append("vad")
        return [SpeechRegion(802_000, 810_000), SpeechRegion(810_000, 819_000)]


class MockASRProvider:
    """Record ASR and return one strong and one low-confidence segment."""

    name = "mock-asr"

    def __init__(self, calls: list[str]) -> None:
        """Store the shared call trace."""

        self.calls = calls

    def transcribe(self, audio: AudioAsset, regions: list[SpeechRegion]) -> list[ASRSegment]:
        """Return timestamped mock transcript segments."""

        self.calls.append("asr")
        assert len(regions) == 2
        return [
            ASRSegment("Battery lasts a full workday.", 802_000, 810_000, 0.94, language="en"),
            ASRSegment("Heat rises during gaming.", 810_000, 819_000, 0.54, language="en"),
        ]


def test_evidence_models_complete_flow() -> None:
    """Verify Source → Artifact → EvidenceUnit → Claim → ClaimEvidence construction."""

    source = _source()
    artifact = Artifact(
        id="artifact-1",
        source_id=source.id,
        artifact_type="subtitle",
        content_hash="sha256:artifact",
        captured_at="2026-07-17T10:00:00",
        collector_name="mock-asr",
        collector_version="1.0.0",
        raw_data={"provider": "mock"},
        full_transcript="Battery lasts a full workday.",
    )
    unit = EvidenceUnit(
        id="evidence-1",
        text="Battery lasts a full workday.",
        modality="speech",
        source_id=source.id,
        artifact_id=artifact.id,
        start_ms=802_000,
        end_ms=819_000,
        asr_confidence=0.94,
        extraction_method="mock-asr",
    )
    claim = Claim(
        id="claim-1",
        claim_text="The battery lasts a full workday.",
        claim_type="product_performance",
        confidence_label="Strong",
        source_ids=[source.id],
        evidence_unit_ids=[unit.id],
    )
    relation = ClaimEvidence(
        claim_id=claim.id,
        evidence_unit_id=unit.id,
        relation="support",
        relevance_score=0.95,
        directness_score=0.9,
    )

    assert artifact.model_dump()["full_transcript"] == "Battery lasts a full workday."
    assert unit.citation_ref("bilibili", "BVxxxx") == "[BILIBILI:BVxxxx@13:22-13:39]"
    assert claim.evidence_unit_ids == (unit.id,)
    assert relation.relation == "support"


def test_asr_pipeline_interface_chain_and_cache() -> None:
    """Verify the ASR orchestration order, low-confidence marking, Top-N and cache reuse."""

    calls: list[str] = []
    cache = InMemoryASRCache()
    pipeline = ASRPipeline(
        permission_checker=MockPermissionChecker(calls),
        audio_extractor=MockAudioExtractor(calls),
        vad_provider=MockVADProvider(calls),
        asr_provider=MockASRProvider(calls),
        cache=cache,
        top_n=2,
        low_confidence_threshold=0.65,
    )
    media = MediaInput("mock://video/BVxxxx", source_id=1, candidate_rank=1, rights_basis="test fixture")

    result = pipeline.run(media)
    assert calls == ["permission", "extract", "vad", "asr"]
    assert result.status == "low_confidence"
    assert result.artifact is not None
    assert len(result.evidence_units) == 2
    assert result.evidence_units[1].review_status == "low_confidence"

    cached = pipeline.run(media)
    assert cached.cache_hit is True
    assert calls == ["permission", "extract", "vad", "asr", "permission"]

    skipped = pipeline.run(MediaInput("mock://video/third", source_id=3, candidate_rank=3))
    assert skipped.status == "skipped"


def test_multidimensional_quality_labels_and_reasons() -> None:
    """Verify quality uses dimensions and categorical labels rather than comment-count totals."""

    source = _source()
    artifact = Artifact(
        id="artifact-1",
        source_id=source.id,
        artifact_type="subtitle",
        content_hash="sha256:artifact",
        captured_at="2026-07-17T10:00:00",
        collector_version="1.0.0",
        full_transcript="Battery lasts a full workday during office use.",
    )
    unit = EvidenceUnit(
        id="evidence-1",
        text="Battery lasts a full workday during office use.",
        modality="speech",
        source_id=source.id,
        artifact_id=artifact.id,
        start_ms=802_000,
        end_ms=819_000,
        asr_confidence=0.94,
    )
    assessment = assess_evidence_quality(
        source,
        claim_text="battery lasts full workday office use",
        artifact=artifact,
        evidence_unit=unit,
        research_start=datetime(2026, 7, 1),
        research_end=datetime(2026, 7, 17, 23, 59),
        independence_score=0.9,
    )

    assert assessment.label == "Strong"
    assert set(assessment.dimensions) == {
        "relevance",
        "directness",
        "integrity",
        "extraction_confidence",
        "source_credibility",
        "independence",
        "freshness",
    }
    assert len(assessment.reasons) == 7


def test_citation_parse_link_and_evidence_resolution() -> None:
    """Verify timestamp and comment references parse, link, and resolve to evidence units."""

    timestamp = parse_citation("[BILIBILI:BVxxxx@13:22-13:39]")
    assert timestamp.start_ms == 802_000
    assert timestamp.end_ms == 819_000
    assert build_citation_link(timestamp).endswith("?t=802")

    comment = parse_citation("[DOUYIN:7340000000000000000/comment/123456]")
    assert comment.comment_id == "123456"
    assert "comment_id=123456" in build_citation_link(comment)

    timestamp_unit = EvidenceUnit(
        id="evidence-time",
        text="Battery lasts a full workday.",
        modality="speech",
        source_id=1,
        artifact_id="artifact-1",
        start_ms=802_000,
        end_ms=819_000,
    )
    comment_unit = EvidenceUnit(
        id="evidence-comment",
        text="The battery is reliable.",
        modality="comment",
        source_id=2,
        artifact_id="artifact-2",
        comment_id="123456",
    )
    assert resolve_evidence_unit(timestamp, [timestamp_unit], source_id=1) == timestamp_unit
    assert resolve_evidence_unit(comment, [comment_unit], source_id=2) == comment_unit
    assert format_citation(timestamp_unit, platform="bilibili", platform_object_id="BVxxxx") == timestamp.raw


def test_planner_structured_decomposition_and_platform_queries() -> None:
    """Verify entities, time scope, comparisons, evidence types, and platform-specific queries."""

    query = "小米 14 和华为 Pura 70 最近3个月评测对比与吐槽"
    analysis = analyze_research_question(query, "zh")
    assert analysis.time_range == "最近3个月"
    assert "comparison" in analysis.evidence_types
    assert "complaint" in analysis.evidence_types
    assert len(analysis.comparison_objects) == 2

    request = ResearchRequest(
        need=query,
        query=query,
        platforms=["bilibili", "douyin", "youtube"],
        useCrawlerRuntime=False,
    )
    plan, _ = build_research_plan(request)
    queries = {target.platform: target.query for target in plan.targets}
    assert "深度评测" in queries["bilibili"]
    assert "吐槽" in queries["douyin"]
    assert "review comparison" in queries["youtube"]


def _source() -> Source:
    """Build a stable source fixture shared by offline verification tests."""

    return Source(
        id=1,
        platform="bilibili",
        title="Battery endurance field review",
        creator="Verified Reviewer",
        url="https://www.bilibili.com/video/BVxxxx",
        published="2026-07-10",
        summary="Battery lasts a full workday during office use.",
        transcriptPreview="Battery lasts a full workday during office use.",
        relevanceScore=90,
        metrics={"creator_verified": True, "independence_cluster": "original-review"},
    )


def main() -> None:
    """Run the same offline checks without requiring pytest collection."""

    tests = [
        test_evidence_models_complete_flow,
        test_asr_pipeline_interface_chain_and_cache,
        test_multidimensional_quality_labels_and_reasons,
        test_citation_parse_link_and_evidence_resolution,
        test_planner_structured_decomposition_and_platform_queries,
    ]
    for test in tests:
        test()
    print(f"offline evidence verification passed: {len(tests)} checks")


if __name__ == "__main__":
    main()
