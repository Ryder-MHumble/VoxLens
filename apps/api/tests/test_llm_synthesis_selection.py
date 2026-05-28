from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from app.models import Comment, CoverageSummary, Source


def make_sources(count: int) -> list[Source]:
    platforms = ["bilibili", "douyin", "youtube", "xiaohongshu", "zhihu", "kuaishou", "weibo"]
    return [
        Source(
            id=idx,
            platform=platforms[(idx - 1) % len(platforms)],  # type: ignore[arg-type]
            title=f"source video {idx}",
            creator=f"creator-{idx}",
            url=f"https://example.com/video/{idx}",
            summary=f"summary for source {idx}",
            evidenceScore=idx,
            comments=[Comment(text=f"comment evidence {idx}")],
            transcriptPreview=f"transcript evidence {idx}",
        )
        for idx in range(1, count + 1)
    ]


class LlmSourceSelectionTests(unittest.TestCase):
    def test_selector_sends_all_candidates_and_returns_llm_order(self) -> None:
        from app.services.llm_synthesis import select_sources_with_llm

        sources = make_sources(20)
        captured_prompt: dict[str, object] = {}

        def fake_post_chat_completion(api_key: str, payload: dict[str, object]) -> str:
            self.assertEqual(api_key, "test-key")
            user_prompt = payload["messages"][1]["content"]  # type: ignore[index]
            captured_prompt.update(json.loads(str(user_prompt)))
            return json.dumps({"selectedSourceIds": [18, 3, 12], "warnings": ["selector note"]})

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "VOXLENS_ENABLE_LLM": "true"}, clear=False):
            with patch("app.services.llm_synthesis._post_chat_completion", fake_post_chat_completion):
                result = select_sources_with_llm(
                    need="need",
                    query="query",
                    lang="en",
                    sources=sources,
                    coverage=CoverageSummary(totalSources=len(sources)),
                    report_kind="general",
                    max_sources=8,
                )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual([candidate["id"] for candidate in captured_prompt["sourceCandidates"]], list(range(1, 21)))  # type: ignore[index]
        self.assertEqual(result.source_ids, [18, 3, 12])
        self.assertEqual([source.id for source in result.sources], [18, 3, 12])
        self.assertEqual(result.warnings, ["selector note"])

    def test_synthesis_uses_selected_sources_and_keeps_full_citation_lists(self) -> None:
        from app.services.llm_synthesis import synthesize_with_llm

        sources = make_sources(20)
        selected_ids = [18, 3, 12, 20, 7, 15, 9, 11]
        synthesis_prompt: dict[str, object] = {}

        def fake_post_chat_completion(api_key: str, payload: dict[str, object]) -> str:
            user_prompt = json.loads(str(payload["messages"][1]["content"]))  # type: ignore[index]
            if "sourceCandidates" in user_prompt:
                return json.dumps({"selectedSourceIds": selected_ids})
            synthesis_prompt.update(user_prompt)
            return json.dumps({
                "takeaways": [{"text": "selected sources support the answer", "citations": selected_ids}],
                "insights": [{
                    "id": "selected-signal",
                    "kind": "coverage",
                    "label": "Selected signal",
                    "summary": "Uses the selected sources.",
                    "confidence": 4,
                    "sourceIds": selected_ids,
                }],
                "sections": [{
                    "id": "selected-evidence",
                    "title": "Selected Evidence",
                    "kind": "answer",
                    "body": "The report cites all selected high-confidence sources.",
                    "sourceIds": selected_ids,
                    "bullets": [{"text": "All selected citations remain visible.", "citations": selected_ids}],
                }],
            })

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "VOXLENS_ENABLE_LLM": "true"}, clear=False):
            with patch("app.services.llm_synthesis._post_chat_completion", fake_post_chat_completion):
                result = synthesize_with_llm(
                    need="need",
                    query="query",
                    lang="en",
                    sources=sources,
                    coverage=CoverageSummary(totalSources=len(sources)),
                    report_kind="general",
                )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual([source["id"] for source in synthesis_prompt["sources"]], selected_ids)  # type: ignore[index]
        self.assertEqual(result.takeaways[0].citations, selected_ids)
        self.assertEqual(result.insights[0].sourceIds, selected_ids)
        self.assertEqual(result.sections[0].sourceIds, selected_ids)
        self.assertEqual(result.sections[0].bullets[0].citations, selected_ids)


if __name__ == "__main__":
    unittest.main()
