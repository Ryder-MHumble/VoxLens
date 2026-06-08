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

    def test_selector_accepts_bare_json_array_from_llm(self) -> None:
        from app.services.llm_synthesis import select_sources_with_llm

        sources = make_sources(5)

        def fake_post_chat_completion(api_key: str, payload: dict[str, object]) -> str:
            return json.dumps([4, 2, 99])

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "VOXLENS_ENABLE_LLM": "true"}, clear=False):
            with patch("app.services.llm_synthesis._post_chat_completion", fake_post_chat_completion):
                result = select_sources_with_llm(
                    need="need",
                    query="query",
                    lang="en",
                    sources=sources,
                    coverage=CoverageSummary(totalSources=len(sources)),
                    report_kind="general",
                    max_sources=3,
                )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.source_ids, [4, 2])

    def test_synthesis_accepts_bare_section_array_from_llm(self) -> None:
        from app.services.llm_synthesis import synthesize_with_llm

        sources = make_sources(1)

        def fake_post_chat_completion(api_key: str, payload: dict[str, object]) -> str:
            user_prompt = json.loads(str(payload["messages"][1]["content"]))  # type: ignore[index]
            schema = user_prompt.get("outputSchema", {})
            if isinstance(schema, dict) and "evidence" in schema:
                return json.dumps([])
            if "sourceCandidates" in user_prompt:
                return json.dumps({"selectedSourceIds": [1], "warnings": []})
            return json.dumps([
                {
                    "id": "source-grounded-answer",
                    "title": "Source Grounded Answer",
                    "kind": "answer",
                    "body": "The selected source supports the answer.",
                    "sourceIds": [1],
                }
            ])

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
        self.assertEqual(len(result.sections), 1)
        self.assertEqual(result.sections[0].sourceIds, [1])

    def test_llm_message_content_accepts_text_parts(self) -> None:
        from app.services.llm_synthesis import _message_content_text

        self.assertEqual(
            _message_content_text([{"type": "text", "text": "{\"sections\": []}"}]),
            "{\"sections\": []}",
        )
        self.assertEqual(_message_content_text({"text": "{\"selectedSourceIds\": [1]}"}), "{\"selectedSourceIds\": [1]}")

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

    def test_decision_synthesis_extracts_attributes_conflicts_and_full_transcripts(self) -> None:
        from app.services.llm_synthesis import synthesize_with_llm

        source = Source(
            id=1,
            platform="youtube",
            title="Sony XM6 降噪耳机测评",
            creator="creator",
            url="https://example.com/1",
            summary="Sony XM6 review",
            comments=[Comment(text="降噪强但夏天佩戴热")],
            transcriptPreview="Sony XM6 降噪强。",
            fullTranscript="Sony XM6 降噪强。 " + ("middle " * 300) + "late transcript says airplane noise cancelling is excellent and wearing gets warm.",
            evidenceScore=40,
        )
        prompts: list[dict[str, object]] = []
        systems: list[str] = []

        def fake_post_chat_completion(api_key: str, payload: dict[str, object]) -> str:
            self.assertEqual(api_key, "test-key")
            systems.append(str(payload["messages"][0]["content"]))  # type: ignore[index]
            user_prompt = json.loads(str(payload["messages"][1]["content"]))  # type: ignore[index]
            prompts.append(user_prompt)
            schema = user_prompt.get("outputSchema", {})
            if isinstance(schema, dict) and "evidence" in schema:
                return json.dumps({"evidence": [], "warnings": []})
            if isinstance(schema, dict) and "products" in schema:
                return json.dumps({
                    "products": {
                        "Sony XM6": {
                            "降噪": [
                                {
                                    "conclusion": "飞机噪声压制优秀",
                                    "condition": "airplane",
                                    "sourceIds": [1],
                                }
                            ]
                        }
                    },
                    "warnings": [],
                })
            if isinstance(schema, dict) and "contradictions" in schema:
                return json.dumps({
                    "contradictions": {
                        "降噪": {
                            "isContradictory": False,
                            "contradictionDescription": "",
                            "possibleReason": "",
                        }
                    },
                    "warnings": [],
                })
            if "sourceCandidates" in user_prompt:
                return json.dumps({"selectedSourceIds": [1], "warnings": []})
            self.assertIn("decisionAttributeMatrix", user_prompt)
            self.assertIn("contradictionAnalysis", user_prompt)
            self.assertIn("fullTranscript", user_prompt["sources"][0])  # type: ignore[index]
            self.assertIn("late transcript says airplane noise cancelling", user_prompt["sources"][0]["fullTranscript"])  # type: ignore[index]
            return json.dumps({
                "takeaways": [{"text": "Sony XM6 is the clearest buy for noise cancelling.", "citations": [1]}],
                "sections": [
                    {"id": "needs", "title": "1. My Needs", "kind": "decision_needs", "body": "Need: noise cancelling headphones.", "sourceIds": [1]},
                    {"id": "candidates", "title": "2. Candidate Filtering", "kind": "candidate_map", "body": "Sony XM6 is supported.", "sourceIds": [1]},
                    {"id": "dimension-comparison", "title": "3. Dimension Matrix", "kind": "decision_matrix", "body": "Noise cancelling is strongest.", "sourceIds": [1]},
                    {"id": "final-recommendation", "title": "4. Final Recommendation", "kind": "final_recommendation", "body": "Buy Sony XM6 if ANC matters most.", "sourceIds": [1]},
                ],
                "warnings": [],
            })

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "VOXLENS_ENABLE_LLM": "true"}, clear=False):
            with patch("app.services.llm_synthesis._post_chat_completion", fake_post_chat_completion):
                result = synthesize_with_llm(
                    need="2000左右降噪耳机推荐",
                    query="2000左右降噪耳机推荐",
                    lang="zh",
                    sources=[source],
                    coverage=CoverageSummary(totalSources=1),
                    report_kind="decision",
                )

        self.assertIsNotNone(result)
        self.assertTrue(any("消费决策分析师" in system for system in systems))
        self.assertTrue(any("decisionAttributeMatrix" in prompt for prompt in prompts))

    def test_business_synthesis_uses_b2b_prompt_and_template(self) -> None:
        from app.services.llm_synthesis import synthesize_with_llm

        source = Source(
            id=1,
            platform="bilibili",
            title="扫地机器人品类机会与竞品格局",
            creator="creator",
            url="https://example.com/1",
            summary="Category research for robot vacuums.",
            comments=[Comment(text="用户关注避障、毛发处理和基站清洁")],
            transcriptPreview="品类机会集中在宠物家庭、低噪音和自动上下水。",
            evidenceScore=36,
        )
        systems: list[str] = []
        prompts: list[dict[str, object]] = []

        def fake_post_chat_completion(api_key: str, payload: dict[str, object]) -> str:
            systems.append(str(payload["messages"][0]["content"]))  # type: ignore[index]
            user_prompt = json.loads(str(payload["messages"][1]["content"]))  # type: ignore[index]
            prompts.append(user_prompt)
            schema = user_prompt.get("outputSchema", {})
            if isinstance(schema, dict) and "evidence" in schema:
                self.assertIn("品类/产品/竞品", str(user_prompt["task"]))
                return json.dumps({"evidence": [], "warnings": []})
            if "sourceCandidates" in user_prompt:
                self.assertEqual(user_prompt["reportKind"], "business")
                self.assertIn("B 端产品/品类研究", str(user_prompt["task"]))
                return json.dumps({"selectedSourceIds": [1], "warnings": []})

            self.assertIn("businessTemplate", user_prompt)
            self.assertEqual(user_prompt["businessTemplate"][0]["id"], "executive-summary")  # type: ignore[index]
            self.assertEqual(user_prompt["outputSchema"]["sections"][-1]["id"], "research-gaps")  # type: ignore[index]
            return json.dumps({
                "takeaways": [{"text": "品类机会集中在宠物家庭和基站体验。", "citations": [1]}],
                "sections": [
                    {"id": "executive-summary", "title": "1. 研究结论摘要", "kind": "business_summary", "body": "宠物家庭是可验证机会。", "sourceIds": [1]},
                    {"id": "category-scope", "title": "2. 品类/产品范围", "kind": "category_scope", "body": "范围是扫地机器人。", "sourceIds": [1]},
                    {"id": "competitive-landscape", "title": "3. 竞品与内容格局", "kind": "competitive_landscape", "body": "竞品围绕避障叙事。", "sourceIds": [1]},
                    {"id": "user-voice-signals", "title": "4. 用户声音与需求信号", "kind": "user_voice_signals", "body": "用户关注毛发处理。", "sourceIds": [1]},
                    {"id": "opportunity-risks", "title": "5. 机会、风险与分歧", "kind": "opportunity_risks", "body": "噪音是风险。", "sourceIds": [1]},
                    {"id": "research-gaps", "title": "6. 证据缺口与下一步研究", "kind": "research_gaps", "body": "市场规模待验证。", "sourceIds": [1]},
                ],
                "warnings": [],
            })

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "VOXLENS_ENABLE_LLM": "true"}, clear=False):
            with patch("app.services.llm_synthesis._post_chat_completion", fake_post_chat_completion):
                result = synthesize_with_llm(
                    need="帮品牌方做扫地机器人品类机会研究",
                    query="扫地机器人品类机会 竞品格局",
                    lang="zh",
                    sources=[source],
                    coverage=CoverageSummary(totalSources=1),
                    report_kind="business",
                )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(any("B 端产品/品类研究分析师" in system for system in systems))
        self.assertEqual([section.id for section in result.sections], ["executive-summary", "category-scope", "competitive-landscape", "user-voice-signals", "opportunity-risks", "research-gaps"])
        self.assertTrue(any(prompt.get("businessTemplate") for prompt in prompts))

    def test_consumer_synthesis_uses_shopper_prompt_without_b2b_template(self) -> None:
        from app.services.llm_synthesis import synthesize_with_llm

        source = Source(
            id=1,
            platform="xiaohongshu",
            title="家用咖啡机新手避坑",
            creator="creator",
            url="https://example.com/coffee",
            summary="Beginner coffee machine advice.",
            comments=[Comment(text="新手怕清洗麻烦，胶囊机更省心")],
            transcriptPreview="半自动需要练习，全自动价格高，胶囊机维护简单。",
            evidenceScore=35,
        )
        systems: list[str] = []
        prompts: list[dict[str, object]] = []

        def fake_post_chat_completion(api_key: str, payload: dict[str, object]) -> str:
            systems.append(str(payload["messages"][0]["content"]))  # type: ignore[index]
            user_prompt = json.loads(str(payload["messages"][1]["content"]))  # type: ignore[index]
            prompts.append(user_prompt)
            schema = user_prompt.get("outputSchema", {})
            if isinstance(schema, dict) and "evidence" in schema:
                return json.dumps({"evidence": [], "warnings": []})
            if isinstance(schema, dict) and "products" in schema:
                return json.dumps({"products": {"胶囊机": {"维护": [{"conclusion": "更省心", "sourceIds": [1]}]}}, "warnings": []})
            if isinstance(schema, dict) and "contradictions" in schema:
                return json.dumps({"contradictions": {}, "warnings": []})
            if "sourceCandidates" in user_prompt:
                self.assertEqual(user_prompt["reportKind"], "consumer")
                return json.dumps({"selectedSourceIds": [1], "warnings": []})

            self.assertEqual(user_prompt["businessTemplate"], [])
            self.assertEqual(user_prompt["outputSchema"]["sections"][0]["id"], "quick-answer")  # type: ignore[index]
            return json.dumps({
                "takeaways": [{"text": "新手优先考虑维护简单。", "citations": [1]}],
                "sections": [
                    {"id": "quick-answer", "title": "先说结论", "kind": "consumer_answer", "body": "新手先看胶囊机。", "sourceIds": [1]},
                    {"id": "why", "title": "为什么这么判断", "kind": "consumer_reasoning", "body": "维护简单是关键。", "sourceIds": [1]},
                    {"id": "caveats", "title": "避坑点", "kind": "consumer_caveats", "body": "不要忽略耗材成本。", "sourceIds": [1]},
                ],
                "warnings": [],
            })

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key", "VOXLENS_ENABLE_LLM": "true"}, clear=False):
            with patch("app.services.llm_synthesis._post_chat_completion", fake_post_chat_completion):
                result = synthesize_with_llm(
                    need="家用咖啡机新手想少维护、少踩坑，应该选哪种？",
                    query="家用咖啡机新手 少维护 避坑",
                    lang="zh",
                    sources=[source],
                    coverage=CoverageSummary(totalSources=1),
                    report_kind="consumer",
                )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(any("普通用户买前决策助手" in system for system in systems))
        self.assertEqual(result.sections[0].id, "quick-answer")


if __name__ == "__main__":
    unittest.main()
