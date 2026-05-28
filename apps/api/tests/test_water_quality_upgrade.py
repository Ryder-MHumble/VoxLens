from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from app.models import Comment, ComparisonRow, CoverageSummary, RunLog, Source
from app.providers.crawler_provider import _source_from_crawler_row
from app.providers.opencli_provider import _enrich_youtube
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

        self.assertIn("segment 29 battery detail", source.transcriptText)
        self.assertIn("segment 0 battery detail", source.transcriptPreview)
        self.assertLess(len(source.transcriptPreview), len(source.transcriptText))

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
                need="3000-5000元手机推荐，重点续航、拍照、性能、散热",
                query="3000-5000元手机推荐，重点续航、拍照、性能、散热",
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


if __name__ == "__main__":
    unittest.main()
