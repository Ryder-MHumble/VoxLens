from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import patch

from app.agents.planner import build_research_plan
from app.models import Comment, ComparisonRow, CoverageSummary, ResearchRequest, RunLog, Source
from app.providers.crawler_provider import _source_from_crawler_row
from app.providers.opencli_provider import (
    _enrich_youtube,
    _enrich_youtube_transcript_with_api,
    _search_youtube_with_api,
    _search_youtube_with_ytdlp,
)
from app.services.report_builder import build_report


def make_source(source_id: int = 1, *, title: str = "3000-5000 phone review") -> Source:
    return Source(
        id=source_id,
        platform="youtube",
        title=title,
        creator="creator",
        url=f"https://example.com/video/{source_id}",
        summary=title,
        comments=[Comment(text="battery is strong but heat needs checking")],
        transcriptPreview="preview only",
        transcriptText="full battery transcript",
        fullTranscript="full battery transcript",
        evidenceScore=20,
    )


class WaterQualityUpgradeTests(unittest.TestCase):
    def test_opencli_youtube_enrichment_preserves_full_transcript_and_preview(self) -> None:
        source = Source(id=1, platform="youtube", title="phone review", creator="creator", url="https://youtube.com/watch?v=abc")
        transcript_rows = [{"text": f"segment {idx} battery detail with long scenario context"} for idx in range(30)]

        def fake_run_command(args: list[str], **_: object) -> tuple[int, str, str, float]:
            self.assertIn("transcript", args)
            return 0, json.dumps({"items": transcript_rows}), "", 0.01

        with patch("app.providers.opencli_provider.run_command", fake_run_command):
            _enrich_youtube(source, comments_limit=0, include_transcripts=True)

        self.assertIn("segment 29 battery detail", source.fullTranscript)
        self.assertIn("segment 29 battery detail", source.transcriptText)
        self.assertIn("segment 0 battery detail", source.transcriptPreview)
        self.assertLess(len(source.transcriptPreview), len(source.fullTranscript))

    def test_youtube_transcript_api_fallback_populates_transcript(self) -> None:
        source = Source(id=1, platform="youtube", title="phone review", creator="creator", url="https://youtube.com/watch?v=abc123")

        with patch(
            "app.providers.opencli_provider._fetch_transcript_with_python",
            return_value=[{"text": "first transcript line", "start": 0, "end": 1}],
        ):
            _enrich_youtube_transcript_with_api(source)

        self.assertEqual(source.transcriptText, "first transcript line")

    def test_youtube_api_search_returns_video_metadata_without_opencli(self) -> None:
        responses = {
            "search": {
                "items": [
                    {
                        "id": {"videoId": "abc123"},
                        "snippet": {
                            "title": "Long-form product review",
                            "channelTitle": "Creator",
                            "description": "Long term field notes",
                            "publishedAt": "2026-01-02T00:00:00Z",
                        },
                    }
                ]
            },
            "videos": {
                "items": [
                    {
                        "id": "abc123",
                        "snippet": {
                            "title": "Long-form product review",
                            "channelTitle": "Creator",
                            "description": "Detailed field notes",
                            "publishedAt": "2026-01-02T00:00:00Z",
                            "thumbnails": {"high": {"url": "https://img.example/high.jpg"}},
                        },
                        "contentDetails": {"duration": "PT12M3S"},
                        "statistics": {"viewCount": "1000", "commentCount": "12", "likeCount": "34"},
                    }
                ]
            },
        }

        class FakeResponse:
            def __init__(self, payload: dict[str, object]) -> None:
                self.payload = payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(self.payload).encode("utf-8")

        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            url = getattr(request, "full_url", "")
            if "/search?" in url:
                return FakeResponse(responses["search"])
            if "/videos?" in url:
                return FakeResponse(responses["videos"])
            raise AssertionError(url)

        with patch.dict(os.environ, {"YOUTUBE_API_KEY": "test-key"}, clear=False):
            with patch("app.providers.opencli_provider.urllib.request.urlopen", fake_urlopen):
                sources, note = _search_youtube_with_api("product review", 3)

        self.assertEqual(len(sources), 1)
        self.assertIn("YouTube Data API", note)
        self.assertEqual(sources[0].title, "Long-form product review")
        self.assertEqual(sources[0].creator, "Creator")
        self.assertEqual(sources[0].metrics["source_provider"], "youtube-api")

    def test_ytdlp_fallback_uses_current_python_executable(self) -> None:
        def fake_run_command(args: list[str], **_: object) -> tuple[int, str, str, float]:
            self.assertEqual(args[:3], [sys.executable, "-m", "yt_dlp"])
            return 0, json.dumps({"entries": [{"id": "abc123", "title": "Product review"}]}), "", 0.01

        with patch("app.providers.opencli_provider.run_command", fake_run_command):
            sources, _ = _search_youtube_with_ytdlp("product", 1)

        self.assertEqual(sources[0].url, "https://www.youtube.com/watch?v=abc123")

    def test_planner_uses_deeper_youtube_target_without_changing_other_platforms(self) -> None:
        request = ResearchRequest(
            need="product research",
            query="product research",
            platforms=["youtube", "zhihu"],
            limitPerPlatform=12,
            detailVideosPerPlatform=2,
            commentsPerVideo=8,
        )

        plan, _ = build_research_plan(request)
        targets = {target.platform: target for target in plan.targets if target.role == "primary"}

        self.assertEqual(targets["youtube"].limit, 20)
        self.assertEqual(targets["youtube"].detailLimit, 6)
        self.assertEqual(targets["zhihu"].limit, 12)
        self.assertEqual(targets["zhihu"].detailLimit, 2)

    def test_crawler_text_sources_preserve_full_text_as_transcript_context(self) -> None:
        full_text = " ".join([f"paragraph-{idx}" for idx in range(80)])
        source = _source_from_crawler_row(
            "zhihu",
            {
                "content_id": "z1",
                "title": "3000-5000 phone recommendation",
                "content_text": full_text,
                "content_url": "https://zhihu.com/question/1",
            },
            {},
            1,
            0,
        )

        self.assertEqual(source.fullTranscript, full_text)
        self.assertEqual(source.transcriptText, full_text)
        self.assertEqual(source.transcriptPreview, full_text[:420])

    def test_semantic_evidence_extraction_sends_chunked_full_transcript(self) -> None:
        from app.services.llm_synthesis import extract_semantic_evidence_with_llm

        source = make_source(1, title="Redmi K70 long term review")
        source.transcriptText = " ".join(
            [
                "opening overview",
                "battery endurance starts here",
                "performance and heat discussion",
                "late section says game full frame battery drops to 4 hours with clear heat warning",
            ]
        )
        captured_prompt: dict[str, object] = {}

        def fake_post_chat_completion(api_key: str, payload: dict[str, object]) -> str:
            self.assertEqual(api_key, "test-key")
            captured_prompt.update(json.loads(str(payload["messages"][1]["content"])))  # type: ignore[index]
            return json.dumps(
                {
                    "evidence": [
                        {
                            "candidate": "Redmi K70",
                            "dimension": "battery",
                            "conclusion": "Battery is weaker in full-frame gaming.",
                            "scenario": "game full frame",
                            "value": "4 hours",
                            "quote": "battery drops to 4 hours",
                            "sourceId": 1,
                            "confidence": 4,
                        }
                    ],
                    "warnings": [],
                }
            )

        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "test-key",
                "VOXLENS_ENABLE_LLM": "true",
                "VOXLENS_LLM_TRANSCRIPT_CHUNK_CHARS": "48",
            },
            clear=False,
        ):
            with patch("app.services.llm_synthesis._post_chat_completion", fake_post_chat_completion):
                result = extract_semantic_evidence_with_llm(
                    need="3000-5000 phone recommendation",
                    query="3000-5000 phone recommendation",
                    lang="en",
                    sources=[source],
                    report_kind="decision",
                )

        chunks = captured_prompt["sourceEvidencePacks"][0]["transcriptChunks"]  # type: ignore[index]
        self.assertGreater(len(chunks), 1)
        self.assertTrue(any("game full frame battery drops" in chunk["text"] for chunk in chunks))  # type: ignore[index]
        assert result is not None
        self.assertEqual(result.evidence[0].sourceId, 1)
        self.assertEqual(result.evidence[0].dimension, "battery")

    def test_source_selection_prompt_includes_semantic_evidence(self) -> None:
        from app.services.llm_synthesis import SemanticEvidenceExtraction, select_sources_with_llm

        source = make_source()
        semantic_evidence = [
            SemanticEvidenceExtraction(
                candidate="Redmi K70",
                dimension="battery",
                conclusion="Four hours under full-frame gaming.",
                scenario="game full frame",
                value="4 hours",
                quote="battery drops to 4 hours",
                sourceId=1,
                confidence=4,
            )
        ]
        captured_prompt: dict[str, object] = {}

        def fake_post_chat_completion(api_key: str, payload: dict[str, object]) -> str:
            self.assertEqual(api_key, "test-key")
            captured_prompt.update(json.loads(str(payload["messages"][1]["content"])))  # type: ignore[index]
            return json.dumps({"selectedSourceIds": [1], "warnings": []})

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "VOXLENS_ENABLE_LLM": "true"}, clear=False):
            with patch("app.services.llm_synthesis._post_chat_completion", fake_post_chat_completion):
                result = select_sources_with_llm(
                    need="3000-5000 phone recommendation",
                    query="3000-5000 phone recommendation",
                    lang="en",
                    sources=[source],
                    coverage=CoverageSummary(totalSources=1),
                    report_kind="decision",
                    semantic_evidence=semantic_evidence,
                    max_sources=1,
                )

        candidate = captured_prompt["sourceCandidates"][0]  # type: ignore[index]
        self.assertEqual(candidate["semanticEvidence"][0]["dimension"], "battery")  # type: ignore[index]
        assert result is not None
        self.assertEqual(result.source_ids, [1])

    def test_decision_phone_report_uses_purchase_decision_sections_without_llm(self) -> None:
        sources = [
            Source(
                id=1,
                platform="bilibili",
                title="Redmi K70 3000-5000 手机测评",
                creator="up",
                url="https://example.com/1",
                comments=[Comment(text="续航可以，游戏会发热")],
                transcriptPreview="Redmi K70 续航和性能强，游戏满帧会发热。",
                evidenceScore=30,
            ),
            Source(
                id=2,
                platform="youtube",
                title="OnePlus Ace review battery camera performance",
                creator="creator",
                url="https://example.com/2",
                comments=[Comment(text="camera is good in daylight")],
                transcriptPreview="OnePlus Ace has strong battery, daylight camera and stable performance.",
                evidenceScore=28,
            ),
        ]

        with patch.dict(os.environ, {"VOXLENS_ENABLE_LLM": "false"}, clear=False):
            report = build_report(
                need="5000以内拍照好的手机",
                query="5000以内拍照好的手机",
                lang="zh",
                sources=sources,
                run_logs=[RunLog(provider="test", platform="bilibili", ok=True, count=2)],
            )

        self.assertEqual([section.id for section in report.sections], ["needs", "candidates", "dimension-comparison", "final-recommendation"])
        self.assertIn("首选", report.sections[-1].body)
        self.assertIn("备选", report.sections[-1].body)
        self.assertIn("慎选", report.sections[-1].body)
        self.assertTrue(report.sections[2].table)
        self.assertTrue(report.sections[2].table[0].dimensions)

    def test_comparison_row_accepts_dynamic_dimensions_and_legacy_fields(self) -> None:
        dynamic = ComparisonRow(
            name="Redmi K70",
            dimensions=[
                {
                    "key": "battery",
                    "label": "续航",
                    "score": 4,
                    "summary": "多来源认为续航强，但游戏场景下降明显。",
                    "evidence": [1, 2],
                }
            ],
            evidence=[1, 2],
        )
        legacy = ComparisonRow(name="legacy", camera=3, lowLight=4, video=2, battery=5, price="verify", evidence=[1])

        self.assertEqual(dynamic.dimensions[0].key, "battery")
        self.assertEqual(dynamic.dimensions[0].evidence, [1, 2])
        self.assertEqual(legacy.camera, 3)
        self.assertEqual(legacy.battery, 5)

    def test_decision_report_uses_data_derived_dimensions_for_headphones(self) -> None:
        sources = [
            Source(
                id=1,
                platform="bilibili",
                title="Sony WH1000XM6 降噪耳机 2000 档横评",
                creator="up",
                url="https://example.com/1",
                comments=[Comment(text="Sony WH1000XM6 降噪很稳，佩戴久了不夹头")],
                fullTranscript="Sony WH1000XM6 降噪强，音质偏暖，佩戴舒适，通勤风噪控制好。",
                transcriptPreview="Sony WH1000XM6 降噪强，音质偏暖，佩戴舒适。",
                evidenceScore=34,
            ),
            Source(
                id=2,
                platform="youtube",
                title="Sony WH1000XM6 vs Bose QC Ultra noise cancelling review",
                creator="creator",
                url="https://example.com/2",
                comments=[Comment(text="Bose QC Ultra comfort wins but Sony noise cancelling is stronger")],
                fullTranscript="Sony WH1000XM6 noise cancelling is stronger. Bose QC Ultra comfort and wearing experience are better, sound quality is relaxed.",
                transcriptPreview="Sony noise cancelling is stronger; Bose comfort is better.",
                evidenceScore=32,
            ),
            Source(
                id=3,
                platform="xiaohongshu",
                title="Bose QC Ultra 2000 左右降噪耳机体验",
                creator="creator",
                url="https://example.com/3",
                comments=[Comment(text="Bose QC Ultra 佩戴舒适，音质耐听，降噪够用")],
                fullTranscript="Bose QC Ultra 佩戴舒适，音质耐听，降噪够用，办公室和飞机上都可以。",
                transcriptPreview="Bose QC Ultra 佩戴舒适，音质耐听，降噪够用。",
                evidenceScore=31,
            ),
            Source(
                id=4,
                platform="zhihu",
                title="AirPods Pro 3 降噪 音质 佩戴 体验",
                creator="writer",
                url="https://example.com/4",
                comments=[Comment(text="AirPods Pro 3 连接方便，降噪和佩戴都不错")],
                fullTranscript="AirPods Pro 3 降噪不错，音质清爽，佩戴轻，苹果生态连接方便。",
                transcriptPreview="AirPods Pro 3 降噪不错，音质清爽，佩戴轻。",
                evidenceScore=28,
            ),
        ]

        with patch.dict(os.environ, {"VOXLENS_ENABLE_LLM": "false"}, clear=False):
            report = build_report(
                need="2000左右降噪耳机推荐",
                query="2000左右降噪耳机推荐",
                lang="zh",
                sources=sources,
                run_logs=[RunLog(provider="test", platform="bilibili", ok=True, count=4)],
            )

        self.assertEqual([section.id for section in report.sections], ["needs", "candidates", "dimension-comparison", "final-recommendation"])
        candidates = report.sections[1].data["candidates"]
        comparisons = report.sections[2].data["comparisons"]
        dimension_names = [item["dimension"] for item in comparisons]
        self.assertGreaterEqual(len(candidates), 3)
        self.assertTrue({"降噪", "音质", "佩戴"}.intersection(dimension_names))
        self.assertNotIn("拍照", dimension_names)
        self.assertTrue(all(value["sourceIds"] for item in comparisons for value in item["values"]))
        self.assertIn("买", report.sections[-1].body)

    def test_non_decision_query_keeps_general_section_path(self) -> None:
        sources = [make_source(1, title="新能源汽车市场趋势分析")]

        with patch.dict(os.environ, {"VOXLENS_ENABLE_LLM": "false"}, clear=False):
            report = build_report(
                need="新能源汽车市场趋势如何",
                query="新能源汽车市场趋势如何",
                lang="zh",
                sources=sources,
                run_logs=[RunLog(provider="test", platform="youtube", ok=True, count=1)],
            )

        self.assertEqual(report.sections[0].id, "executive-summary")
        self.assertEqual(len(report.sections), 6)
        self.assertNotEqual(report.sections[0].kind, "decision_needs")


if __name__ == "__main__":
    unittest.main()
