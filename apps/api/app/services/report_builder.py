from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import urlparse

from app.models import (
    CitationText,
    ComparisonDimension,
    ComparisonRow,
    CoverageSummary,
    DecisionCandidate,
    DimensionComparison,
    DimensionComparisonValue,
    OutlineItem,
    PlatformSummary,
    ReportInsight,
    ReportSection,
    ReportUIState,
    ResearchReport,
    ResearchStage,
    RunLog,
    Source,
    SourceGroup,
    VideoQuote,
)
from app.platform_catalog import PLATFORM_ORDER, platform_meta_for_report

PLATFORM_META = platform_meta_for_report()

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "review",
    "comparison",
    "long",
    "term",
    "experience",
    "what",
    "which",
    "how",
    "why",
    "is",
    "are",
    "一个",
    "这个",
    "那个",
    "如何",
    "怎么",
    "是否",
    "可以",
    "视频",
    "测评",
    "评测",
    "体验",
    "对比",
    "真实",
}

POSITIVE_TERMS = {
    "推荐",
    "值得",
    "稳定",
    "好用",
    "优势",
    "提升",
    "优秀",
    "划算",
    "best",
    "worth",
    "good",
    "great",
    "recommend",
    "impressive",
}

RISK_TERMS = {
    "不值得",
    "缺点",
    "问题",
    "翻车",
    "发热",
    "续航",
    "售后",
    "贵",
    "差",
    "坑",
    "降级",
    "avoid",
    "bad",
    "problem",
    "issue",
    "overpriced",
    "worse",
    "risk",
}


def build_report(
    need: str,
    query: str,
    lang: str,
    sources: list[Source],
    run_logs: list[RunLog],
    is_demo: bool = False,
    generated_at: datetime | None = None,
    run_id: str | None = None,
) -> ResearchReport:
    generated_at = generated_at or datetime.now()
    run_id = run_id or f"run-{generated_at.strftime('%Y%m%d%H%M%S')}"
    zh = lang == "zh"

    for idx, source in enumerate(sources, start=1):
        source.id = idx
        _decorate_source(source, query, generated_at)

    total_comments = sum(len(s.comments) for s in sources)
    ranked_terms = _keywords(sources, query)
    risk_terms = _risk_terms(sources)
    citations = [s.id for s in sources[:4] if s.id]
    confidence = _confidence(sources, run_logs)
    warnings = _warnings(sources, run_logs, is_demo, zh)
    status = _report_status(sources, warnings, is_demo)
    coverage = _coverage(sources, run_logs)
    report_kind = _infer_report_kind(need or query)

    takeaways = _takeaways(
        query=query,
        zh=zh,
        sources=sources,
        total_comments=total_comments,
        terms=ranked_terms,
        risks=risk_terms,
        citations=citations,
        confidence=confidence,
    )

    quote = _quote_card(sources[0], zh) if sources else None
    sections = _sections(
        query=query,
        need=need,
        zh=zh,
        sources=sources,
        run_logs=run_logs,
        terms=ranked_terms,
        risks=risk_terms,
        takeaways=takeaways,
        quote=quote,
        confidence=confidence,
        coverage=coverage,
        report_kind=report_kind,
    )
    llm_model = ""
    llm_insights: list[ReportInsight] = []
    if sources and not is_demo:
        try:
            from app.services.llm_synthesis import synthesize_with_llm

            llm_result = synthesize_with_llm(
                need=need,
                query=query,
                lang=lang,
                sources=sources,
                coverage=coverage,
                report_kind=report_kind,
            )
            if llm_result and llm_result.sections:
                takeaways = llm_result.takeaways or takeaways
                sections = llm_result.sections
                llm_insights = llm_result.insights
                sections[0].metrics["llmGenerated"] = True
                warnings.extend(llm_result.warnings)
                llm_model = llm_result.model
        except Exception as exc:  # noqa: BLE001
            warnings.append(("LLM synthesis failed; used deterministic fallback report." if not zh else "LLM 生成失败，已使用确定性兜底报告。") + f" {str(exc)[:120]}")

    _apply_citation_counts(sources, takeaways, sections)
    coverage.citedSources = sum(1 for source in sources if source.citationCount > 0)
    for section in sections:
        if section.kind == "coverage":
            section.metrics.update(coverage.model_dump())
        if "coverage" in section.data:
            section.data["coverage"] = coverage.model_dump()
    outline = _outline_from_sections(sections, sources, zh)
    platforms = _platform_summaries(sources, run_logs, is_demo)
    ui = _ui_state(status, platforms, sources, warnings, zh)
    insights = _insights(
        query=query,
        zh=zh,
        sources=sources,
        terms=ranked_terms,
        risks=risk_terms,
        citations=citations,
        confidence=confidence,
        coverage=coverage,
    )
    if llm_insights:
        insights = llm_insights
    if llm_model:
        for section in sections:
            section.metrics.setdefault("synthesisProvider", "openrouter")
            section.metrics.setdefault("synthesisModel", llm_model)

    report = ResearchReport(
        runId=run_id,
        slogan="视频证据，可信研究" if zh else "Citable social-video research",
        title=_title_from_query(query, zh),
        query=query,
        need=need,
        lang=lang,  # type: ignore[arg-type]
        status=status,
        confidence=confidence,
        generatedAt=generated_at.isoformat(timespec="seconds"),
        totalVideos=len(sources),
        totalComments=total_comments,
        platforms=platforms,
        outline=outline,
        takeaways=takeaways,
        insights=insights,
        coverage=coverage,
        sections=sections,
        sources=sources,
        warnings=warnings,
        methodology=_methodology(zh),
        ui=ui,
        runLogs=run_logs,
        isDemoFallback=is_demo,
    )
    if llm_model:
        report.methodology.append(f"LLM synthesis: OpenRouter / {llm_model}; citations are restricted to collected source IDs.")
    from app.services.quality import evaluate_report_quality

    report.quality = evaluate_report_quality(report)
    if report.quality.warnings:
        report.warnings.extend([warning for warning in report.quality.warnings if warning not in report.warnings])
    return report


def _takeaways(
    query: str,
    zh: bool,
    sources: list[Source],
    total_comments: int,
    terms: list[str],
    risks: list[str],
    citations: list[int],
    confidence: str,
) -> list[CitationText]:
    if not sources:
        text = (
            f"暂未抓到可引用来源，不能对「{query}」给出证据型结论；请检查平台登录、Cookie 或降低平台范围。"
            if zh
            else f"No citable sources were collected for '{query}', so VoxLens cannot make evidence-backed claims yet."
        )
        return [CitationText(text=text, citations=[])]

    platform_count = len({s.platform for s in sources})
    term_text = "、".join(terms[:5]) if zh else ", ".join(terms[:5])
    risk_text = "、".join(risks[:4]) if zh else ", ".join(risks[:4])
    return [
        CitationText(
            text=(
                f"本轮抓取 {len(sources)} 条来源、覆盖 {platform_count} 个平台、抽样 {total_comments} 条评论；高频信号集中在：{term_text or query}。"
                if zh
                else f"This run collected {len(sources)} sources across {platform_count} platform(s) and {total_comments} sampled comments; repeated signals cluster around: {term_text or query}."
            ),
            citations=citations[:3],
        ),
        CitationText(
            text=(
                "优先参考同时具备标题、评论或字幕的来源；单条爆款只作为线索，不能直接当结论。"
                if zh
                else "Prioritize sources with title, comment or transcript evidence; a single viral video is a lead, not a conclusion."
            ),
            citations=citations[:4],
        ),
        CitationText(
            text=(
                f"需要重点复核的分歧/风险：{risk_text or '评论区反例、发布时间、创作者立场和样本场景'}。"
                if zh
                else f"Key disagreements/risks to verify: {risk_text or 'comment counterexamples, publish dates, creator stance and test context'}."
            ),
            citations=citations[1:4] or citations[:2],
        ),
        CitationText(
            text=(
                f"当前置信度为 {confidence}；点击引用编号可以定位右侧来源并打开原视频复核语境。"
                if zh
                else f"Current confidence is {confidence}; hover or click citation IDs to inspect the source and verify context."
            ),
            citations=citations[:2],
        ),
    ]


def _sections(
    query: str,
    need: str,
    zh: bool,
    sources: list[Source],
    run_logs: list[RunLog],
    terms: list[str],
    risks: list[str],
    takeaways: list[CitationText],
    quote: VideoQuote | None,
    confidence: str,
    coverage: CoverageSummary,
    report_kind: str,
) -> list[ReportSection]:
    source_ids = [s.id for s in sources[:6] if s.id]
    platform_sentence = _platform_sentence(sources, zh)
    evidence_sentence = _evidence_sentence(sources, zh)
    risk_sentence = _risk_sentence(risks, zh)
    kind_label = _report_kind_label(report_kind, zh)

    if not sources:
        return [
            ReportSection(
                id="executive-summary",
                title="1. 执行摘要" if zh else "1. Executive Summary",
                kind="answer",
                body=(
                    f"这次任务没有拿到可引用来源，因此报告只保留研究计划与失败原因，不生成未经证实的结论。原始问题是「{need or query}」。"
                    if zh
                    else f"This run did not collect citable sources, so VoxLens keeps the plan and failure reasons instead of inventing conclusions. Original need: {need or query}."
                ),
                bullets=takeaways,
                metrics={"confidence": confidence, "reportKind": report_kind},
            ),
            ReportSection(
                id="coverage",
                title="2. 数据获取状态" if zh else "2. Retrieval Status",
                kind="coverage",
                body=_run_log_summary(run_logs, zh),
                table=_signal_rows(sources, terms, zh),
                metrics=coverage.model_dump(),
                data={"runLogs": [log.model_dump() for log in run_logs]},
            ),
            ReportSection(
                id="next-actions",
                title="3. 下一步" if zh else "3. Next Steps",
                kind="next_actions",
                body=(
                    "建议先确认 VoxLens crawler runtime/CDP 是否可用；如涉及 Bilibili、Douyin、小红书或知乎，请配置 Cookie 或使用已有浏览器登录态后重试。"
                    if zh
                    else "Check OpenCLI/VoxLens crawler runtime availability first; for Bilibili, Douyin, Xiaohongshu or Zhihu, configure cookies or reuse a logged-in browser/CDP session, then retry."
                ),
            ),
        ]

    if report_kind == "decision":
        return _decision_sections(
            query=query,
            need=need,
            zh=zh,
            sources=sources,
            terms=terms,
            risks=risks,
            confidence=confidence,
            coverage=coverage,
        )

    return [
        ReportSection(
            id="executive-summary",
            title="1. 执行摘要" if zh else "1. Executive Summary",
            kind="answer",
            body=(
                f"VoxLens 将「{query}」识别为「{kind_label}」任务，并拆成平台搜索、来源去重、评论/字幕抽样和证据评分四步。{platform_sentence}{evidence_sentence} 因此，本轮报告适合做初筛：先看多来源反复出现的信号，再打开引用来源确认上下文。"
                if zh
                else f"VoxLens classified '{query}' as a {kind_label} task and decomposed it into platform search, deduplication, comment/transcript sampling and evidence scoring. {platform_sentence}{evidence_sentence} This report is best used for first-pass research: read repeated signals, then open cited sources to verify context."
            ),
            bullets=takeaways[:2],
            sourceIds=source_ids[:4],
            metrics={"confidence": confidence, "reportKind": report_kind},
            data={"coverage": coverage.model_dump()},
        ),
        ReportSection(
            id="answer",
            title="2. 初步回答" if zh else "2. Initial Answer",
            kind="answer",
            body=(
                f"针对「{need or query}」，当前证据不直接替你做单一判断，而是给出可复核的决策框架：把「{', '.join(terms[:3]) or query}」作为主要观察维度，把「{risk_sentence}」作为反证检查项。若多个平台的高质量来源都指向同一结论，可信度会显著提高。"
                if zh
                else f"For '{need or query}', the evidence does not justify a one-word answer yet. Use '{', '.join(terms[:3]) or query}' as the primary decision dimensions and '{risk_sentence}' as counter-evidence checks. Confidence rises when high-quality sources across platforms converge."
            ),
            bullets=takeaways,
            sourceIds=source_ids[:4],
            metrics={"confidence": confidence, "primarySignals": terms[:5]},
        ),
        ReportSection(
            id="evidence-map",
            title="3. 证据地图" if zh else "3. Evidence Map",
            kind="evidence_map",
            body=(
                "下面按来源质量而非热度排序：评论和字幕越完整，越适合支撑结论；只有标题的来源只作为发现线索。"
                if zh
                else "Sources are ranked by evidence quality rather than popularity: comments and transcripts carry more weight than title-only matches."
            ),
            quote=quote,
            bullets=[CitationText(text=_source_signal(s, zh), citations=[s.id]) for s in sources[:6]],
            sourceIds=source_ids,
            metrics={"topEvidenceScore": max((s.evidenceScore for s in sources), default=0)},
            data={"channels": _channel_counts(sources)},
        ),
        ReportSection(
            id="consensus-disagreement",
            title="4. 共识、分歧与风险" if zh else "4. Consensus, Disagreement & Risks",
            kind="consensus_disagreement",
            body=(
                f"DeepResearch 需要主动找反例。当前最值得复核的是：{risk_sentence}。如果这些词只出现在单个来源中，应视为提示；如果在多个平台重复出现，应提高优先级。"
                if zh
                else f"DeepResearch should actively look for counterexamples. The strongest checks right now are: {risk_sentence}. Treat one-off mentions as prompts, and repeated cross-platform mentions as higher priority."
            ),
            bullets=_risk_bullets(sources, risks, zh),
            sourceIds=source_ids,
            metrics={"riskTerms": risks[:8], "consensusTerms": terms[:8]},
        ),
        ReportSection(
            id="coverage",
            title="5. 来源质量与覆盖" if zh else "5. Source Quality & Coverage",
            kind="coverage",
            body=(
                f"当前置信度：{confidence}。{_run_log_summary(run_logs, zh)}"
                if zh
                else f"Current confidence: {confidence}. {_run_log_summary(run_logs, zh)}"
            ),
            table=_signal_rows(sources, terms, zh),
            sourceIds=source_ids,
            metrics=coverage.model_dump(),
            data={"runLogs": [log.model_dump() for log in run_logs]},
        ),
        ReportSection(
            id="next-actions",
            title="6. 建议动作" if zh else "6. Recommended Next Actions",
            kind="next_actions",
            body=(
                "建议先打开右侧被多次引用的来源，核对发布时间、测试场景、评论反例和创作者是否有赞助/立场；之后再基于你的预算、场景或偏好追加追问。"
                if zh
                else "Open repeatedly cited sources first, verify publish date, test context, comment counterexamples and creator incentives, then ask a narrower follow-up based on budget, scenario or preference."
            ),
            bullets=[
                CitationText(
                    text=("先复核证据分最高的 3 条来源，再看评论区是否支持同一结论。" if zh else "Verify the top 3 evidence-scored sources, then check whether comments support the same conclusion."),
                    citations=source_ids[:3],
                ),
                CitationText(
                    text=("把低证据来源作为搜索线索，不把它们直接写入最终判断。" if zh else "Use low-evidence sources as search leads, not as direct support for the final judgment."),
                    citations=source_ids[3:6] or source_ids[:2],
                ),
            ],
            sourceIds=source_ids[:6],
            metrics={"recommendedSourceCount": min(3, len(source_ids))},
        ),
    ]


DECISION_GENERIC_STOPWORDS = STOPWORDS | {
    "手机",
    "耳机",
    "笔记本",
    "平板",
    "相机",
    "产品",
    "推荐",
    "左右",
    "以内",
    "预算",
    "测评",
    "评测",
    "体验",
    "横评",
    "对比",
    "来源",
    "视频",
    "博主",
    "用户",
    "使用",
    "noise",
    "cancelling",
    "headphone",
    "headphones",
    "phone",
    "laptop",
    "tablet",
    "camera",
    "buy",
    "best",
    "recommend",
    "recommendation",
    "review",
    "reviews",
    "versus",
    "source",
    "video",
    "use",
    "user",
}

DECISION_NEGATIVE_TERMS = {
    "差",
    "弱",
    "短板",
    "不行",
    "一般",
    "夹头",
    "闷",
    "热",
    "发热",
    "断连",
    "延迟",
    "贵",
    "problem",
    "weak",
    "worse",
    "bad",
    "hot",
    "warm",
    "expensive",
    "latency",
    "disconnect",
}

DECISION_POSITIVE_TERMS = POSITIVE_TERMS | {
    "强",
    "稳",
    "舒服",
    "舒适",
    "耐听",
    "清晰",
    "优秀",
    "够用",
    "strong",
    "stable",
    "comfortable",
    "excellent",
    "clear",
    "better",
}

DECISION_SCENARIO_TERMS = {
    "通勤",
    "飞机",
    "办公室",
    "游戏",
    "夜景",
    "户外",
    "夏天",
    "长时间",
    "会议",
    "airplane",
    "flight",
    "commute",
    "office",
    "gaming",
    "outdoor",
    "summer",
    "long",
}


def _decision_sections(
    *,
    query: str,
    need: str,
    zh: bool,
    sources: list[Source],
    terms: list[str],
    risks: list[str],
    confidence: str,
    coverage: CoverageSummary,
) -> list[ReportSection]:
    source_ids = [s.id for s in sources[:8] if s.id]
    need_text = need or query
    candidates = _decision_candidates(sources, need_text, zh)
    dimensions = _decision_dimensions(sources, candidates, need_text, zh)
    comparisons = _dimension_comparisons(dimensions, candidates, sources, zh)
    rows = _decision_matrix_rows(candidates, comparisons, zh)
    recommendation = _decision_recommendation(candidates, comparisons, risks, zh)

    candidate_payload = [candidate.model_dump() for candidate in candidates]
    comparison_payload = [comparison.model_dump() for comparison in comparisons]
    comparison_source_ids = _ids_from_comparisons(comparisons) or source_ids
    candidate_source_ids = sorted({source_id for candidate in candidates for source_id in candidate.sourceIds}) or source_ids

    return [
        ReportSection(
            id="needs",
            title="1. 我的需求" if zh else "1. My Needs",
            kind="decision_needs",
            body=_decision_need_summary(need_text, dimensions, confidence, zh),
            bullets=[
                CitationText(
                    text=("预算、场景和偏好来自你的输入；候选与维度来自本轮来源中的高频证据。" if zh else "Budget, scenario and preference come from your input; candidates and dimensions come from repeated source evidence."),
                    citations=source_ids[:4],
                )
            ],
            sourceIds=source_ids[:4],
            metrics={"confidence": confidence, "reportKind": "decision", "primarySignals": terms[:6]},
            data={"coverage": coverage.model_dump(), "extractedDimensions": dimensions},
        ),
        ReportSection(
            id="candidates",
            title="2. 候选筛选" if zh else "2. Candidate Filtering",
            kind="candidate_map",
            body=(
                "候选优先选择被多个来源或多个证据通道反复提到的产品；单源产品会保留为备选线索，但不会成为高置信首推。"
                if zh
                else "Candidates prioritize products repeated across sources or evidence channels; single-source products stay as leads but are not high-confidence top picks."
            ),
            bullets=[
                CitationText(text=candidate.matchReason, citations=candidate.sourceIds[:4])
                for candidate in candidates
            ],
            sourceIds=candidate_source_ids,
            metrics={"candidateCount": len(candidates)},
            data={"candidates": candidate_payload},
        ),
        ReportSection(
            id="dimension-comparison",
            title="3. 维度对比矩阵" if zh else "3. Dimension Comparison Matrix",
            kind="decision_matrix",
            body=(
                "矩阵维度从标题、评论和字幕/正文的高频属性词中提取；每个维度至少有 2 个来源提及。绿色代表 3 个以上来源一致，黄色代表有分歧但能归因，灰色代表单源或证据较薄。"
                if zh
                else "Matrix dimensions are extracted from repeated attribute terms in titles, comments and transcripts/content. Each dimension is mentioned by at least 2 sources. Green means 3+ sources align, yellow means attributable disagreement, and gray means single-source or thin evidence."
            ),
            table=rows,
            sourceIds=comparison_source_ids,
            metrics={"dimensions": dimensions, "confidenceLegend": {"green": "3+ consistent sources", "yellow": "attributable disagreement", "gray": "single/thin evidence"}},
            data={"candidates": candidate_payload, "comparisons": comparison_payload},
        ),
        ReportSection(
            id="final-recommendation",
            title="4. 最终推荐" if zh else "4. Final Recommendation",
            kind="final_recommendation",
            body=recommendation["body"],
            bullets=[
                CitationText(text=text, citations=ids)
                for text, ids in recommendation["bullets"]
            ],
            sourceIds=recommendation["sourceIds"] or comparison_source_ids,
            metrics={"riskTerms": risks[:6], "confidence": confidence},
            data={"recommendation": recommendation["data"]},
        ),
    ]


def _decision_candidates(sources: list[Source], need: str, zh: bool) -> list[DecisionCandidate]:
    mentions: dict[str, dict[str, object]] = {}
    for source in sources:
        names = _candidate_names_from_source(source)
        if not names:
            names = [_fallback_candidate_name(source)]
        for name in names[:5]:
            key = _candidate_key(name)
            if not key:
                continue
            item = mentions.setdefault(key, {"name": name, "sourceIds": set(), "score": 0})
            item["sourceIds"].add(source.id)  # type: ignore[union-attr]
            item["score"] = int(item["score"]) + _candidate_occurrences(source, name) + max(1, source.evidenceScore // 20)

    ordered = sorted(
        mentions.values(),
        key=lambda item: (len(item["sourceIds"]), int(item["score"]), str(item["name"])),
        reverse=True,
    )
    selected = ordered[:5]
    candidates: list[DecisionCandidate] = []
    for item in selected:
        source_ids = sorted(int(source_id) for source_id in item["sourceIds"])  # type: ignore[arg-type]
        name = str(item["name"]).strip()
        reason = (
            f"{name} 进入候选：{len(source_ids)} 个来源提到，且与「{need}」的约束/场景相关。"
            if zh
            else f"{name} is a candidate: mentioned by {len(source_ids)} source(s) and relevant to the constraints/scenario in '{need}'."
        )
        candidates.append(DecisionCandidate(name=name, matchReason=reason, sourceIds=source_ids))
    return candidates


def _candidate_names_from_source(source: Source) -> list[str]:
    text = " ".join([source.title, source.summary, source.transcriptPreview, getattr(source, "fullTranscript", "")[:1200]])
    names: list[str] = []

    for pattern in [
        r"\b(?:iPhone|iPad|MacBook|AirPods|Galaxy|Pixel|Redmi|OnePlus|Xiaomi|Huawei|Honor|OPPO|vivo|Sony|Bose|Sennheiser|JBL|Beats|Canon|Nikon|DJI)\b[\w+\- ]{0,36}",
        r"\b[A-Z][A-Za-z]+(?:\s+[A-Z0-9][A-Za-z0-9+\-]*){1,4}\b",
        r"(?:小米|红米|荣耀|华为|索尼|森海塞尔|佳能|尼康|大疆)\s*[\w\u4e00-\u9fff+\- ]{1,18}",
    ]:
        for match in re.finditer(pattern, text):
            name = _clean_candidate_name(match.group(0))
            if name and name not in names:
                names.append(name)
    return names[:8]


def _clean_candidate_name(value: str) -> str:
    name = re.sub(r"\s+", " ", value).strip(" -_/|，,。:：；;()（）[]【】")
    name = re.split(r"\b(?:vs|versus|review|recommendation|experience|long|term)\b|[，,。:：；;【】\[\]()（）]", name, maxsplit=1, flags=re.IGNORECASE)[0]
    name = re.sub(r"(测评|评测|体验|横评|对比|推荐|耳机|手机|笔记本|平板|相机).*$", "", name).strip()
    words = name.split()
    kept: list[str] = []
    for word in words:
        if kept and word.islower() and not any(ch.isdigit() for ch in word):
            break
        kept.append(word)
        if len(kept) >= 5:
            break
    name = " ".join(kept).strip()
    if len(name) < 2 or name.lower() in DECISION_GENERIC_STOPWORDS:
        return ""
    return name[:80]


def _fallback_candidate_name(source: Source) -> str:
    title = re.split(r"[，,。:：；;【】\[\]()（）]|测评|评测|体验|横评|对比|推荐", source.title, maxsplit=1)[0].strip()
    return title[:42] or source.creator or f"{source.platform} source"


def _candidate_key(name: str) -> str:
    key = re.sub(r"[\s_\-]+", "", name.lower())
    key = re.sub(r"[^\w\u4e00-\u9fff]+", "", key)
    return key


def _candidate_occurrences(source: Source, name: str) -> int:
    text = _source_text(source).lower()
    compact = text.replace(" ", "")
    return max(text.count(name.lower()), compact.count(name.lower().replace(" ", "")), 1)


def _decision_dimensions(sources: list[Source], candidates: list[DecisionCandidate], need: str, zh: bool) -> list[str]:
    source_mentions: dict[str, set[int]] = defaultdict(set)
    occurrences: Counter[str] = Counter()
    candidate_names = [candidate.name for candidate in candidates]
    for source in sources:
        terms = _dimension_terms_from_text(_source_text(source), candidate_names)
        for term in terms:
            source_mentions[term].add(source.id)
            occurrences[term] += _term_count(_source_text(source), term)

    ranked = []
    for term, ids in source_mentions.items():
        if len(ids) < 2:
            continue
        if not _valid_dimension_term(term, candidate_names):
            continue
        need_boost = 12 if term.lower() in need.lower() else 0
        ranked.append((len(ids) * 20 + min(occurrences[term], 12) + need_boost, term))
    ranked.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    dimensions = [term for _, term in ranked[:6]]

    if not dimensions:
        fallback_terms = [term for term in terms if _valid_dimension_term(term, candidate_names)]
        dimensions = fallback_terms[:4]
    return dimensions


def _dimension_terms_from_text(text: str, candidate_names: list[str]) -> list[str]:
    terms: list[str] = []
    lower = text.lower()
    for seq in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for size in (2, 3):
            for idx in range(0, max(0, len(seq) - size + 1)):
                term = seq[idx : idx + size]
                if _valid_dimension_term(term, candidate_names):
                    terms.append(term)
    words = [word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9+\-]*", lower)]
    for idx, word in enumerate(words):
        if _valid_dimension_term(word, candidate_names):
            terms.append(word)
        if idx + 1 < len(words):
            phrase = f"{word} {words[idx + 1]}"
            if _valid_dimension_term(phrase, candidate_names):
                terms.append(phrase)
    return list(dict.fromkeys(terms))


def _valid_dimension_term(term: str, candidate_names: list[str]) -> bool:
    normalized = term.strip().lower()
    if len(normalized) < 2 or normalized.isdigit():
        return False
    if normalized in DECISION_GENERIC_STOPWORDS or normalized in DECISION_POSITIVE_TERMS or normalized in DECISION_NEGATIVE_TERMS:
        return False
    if re.search(r"^\d+[a-z]*$", normalized):
        return False
    if any(normalized in _candidate_key(name) or _candidate_key(name) in normalized for name in candidate_names if _candidate_key(name)):
        return False
    compact = re.sub(r"[\s_\-]+", "", normalized)
    if any(compact in _candidate_key(name) or _candidate_key(name) in compact for name in candidate_names if _candidate_key(name)):
        return False
    if re.search(r"(很好|不错|优秀|一般|更好|很强|很稳|左右|以内|推荐|测评|体验)$", normalized):
        return False
    return True


def _term_count(text: str, term: str) -> int:
    return max(text.lower().count(term.lower()), text.replace(" ", "").lower().count(term.replace(" ", "").lower()))


def _dimension_comparisons(
    dimensions: list[str],
    candidates: list[DecisionCandidate],
    sources: list[Source],
    zh: bool,
) -> list[DimensionComparison]:
    source_by_id = {source.id: source for source in sources}
    comparisons: list[DimensionComparison] = []
    for dimension in dimensions:
        dim_sources = [source for source in sources if dimension.lower() in _source_text(source).lower()]
        is_contradictory, reason = _dimension_contradiction(dimension, dim_sources, zh)
        values: list[DimensionComparisonValue] = []
        for candidate in candidates:
            candidate_sources = [source_by_id[source_id] for source_id in candidate.sourceIds if source_id in source_by_id]
            evidence_sources = [
                source
                for source in candidate_sources
                if dimension.lower() in _source_text(source).lower()
            ]
            if not evidence_sources:
                evidence_sources = candidate_sources[:1]
            evidence_ids = [source.id for source in evidence_sources if source.id] or candidate.sourceIds[:1]
            conclusion = _dimension_value_conclusion(candidate.name, dimension, evidence_sources, zh)
            condition = _dimension_condition(evidence_sources, zh)
            color = _confidence_color(len(evidence_ids), is_contradictory)
            values.append(DimensionComparisonValue(
                candidate=candidate.name,
                conclusion=conclusion,
                condition=condition,
                confidence=color,
                sourceIds=evidence_ids,
            ))
        comparisons.append(DimensionComparison(
            dimension=dimension,
            values=values,
            isContradictory=is_contradictory,
            contradictionReason=reason,
        ))
    return comparisons


def _dimension_contradiction(dimension: str, sources: list[Source], zh: bool) -> tuple[bool, str]:
    snippets = [_dimension_snippet(_source_text(source), dimension) for source in sources]
    joined = " ".join(snippets).lower()
    positive = any(term.lower() in joined for term in DECISION_POSITIVE_TERMS)
    negative = any(term.lower() in joined for term in DECISION_NEGATIVE_TERMS)
    if positive and negative:
        conditions = _conditions_from_text(joined, zh)
        reason = (
            f"同一维度既有正向也有负向描述，可能来自{conditions or '测试条件、使用场景或评价标准不同'}。"
            if zh
            else f"Both positive and negative descriptions appear for this dimension, likely due to {conditions or 'different test conditions, scenarios or standards'}."
        )
        return True, reason
    return False, ""


def _dimension_value_conclusion(candidate: str, dimension: str, sources: list[Source], zh: bool) -> str:
    snippets = [_dimension_snippet(_source_text(source), dimension, candidate) for source in sources]
    snippets = [snippet for snippet in snippets if snippet]
    if snippets:
        evidence = snippets[0]
        return (
            f"{candidate} 在「{dimension}」上的证据：{evidence[:120]}"
            if zh
            else f"{candidate} evidence on '{dimension}': {evidence[:140]}"
        )
    return (
        f"{candidate} 的「{dimension}」直接证据不足，先按弱证据处理。"
        if zh
        else f"Direct evidence for {candidate} on '{dimension}' is thin; treat as weak evidence."
    )


def _dimension_snippet(text: str, dimension: str, candidate: str = "") -> str:
    sentences = re.split(r"(?<=[。！？.!?])\s*|[\n\r]+", text)
    candidate_key = _candidate_key(candidate)
    for sentence in sentences:
        lowered = sentence.lower()
        if dimension.lower() not in lowered:
            continue
        if candidate_key and candidate_key not in _candidate_key(sentence):
            continue
        return re.sub(r"\s+", " ", sentence).strip()
    for sentence in sentences:
        if dimension.lower() in sentence.lower():
            return re.sub(r"\s+", " ", sentence).strip()
    return ""


def _dimension_condition(sources: list[Source], zh: bool) -> str:
    text = " ".join(_source_text(source)[:800] for source in sources)
    return _conditions_from_text(text, zh) or ("需打开来源复核场景" if zh else "Verify scenario in source")


def _conditions_from_text(text: str, zh: bool) -> str:
    hits = [term for term in DECISION_SCENARIO_TERMS if term.lower() in text.lower()]
    if not hits:
        return ""
    return "、".join(hits[:3]) if zh else ", ".join(hits[:3])


def _confidence_color(source_count: int, contradictory: bool) -> str:
    if source_count >= 3 and not contradictory:
        return "green"
    if contradictory or source_count >= 2:
        return "yellow"
    return "gray"


def _decision_matrix_rows(candidates: list[DecisionCandidate], comparisons: list[DimensionComparison], zh: bool) -> list[ComparisonRow]:
    rows: list[ComparisonRow] = []
    for candidate in candidates:
        dimensions: list[ComparisonDimension] = []
        row_evidence: set[int] = set(candidate.sourceIds)
        for comparison in comparisons:
            value = next((item for item in comparison.values if item.candidate == candidate.name), None)
            if not value:
                continue
            row_evidence.update(value.sourceIds)
            dimensions.append(ComparisonDimension(
                key=_dimension_key(comparison.dimension),
                label=comparison.dimension,
                score={"green": 5, "yellow": 3, "gray": 2}.get(value.confidence, 2),
                summary=value.conclusion,
                evidence=value.sourceIds,
                metrics={"confidence": value.confidence, "condition": value.condition},
            ))
        rows.append(ComparisonRow(
            name=candidate.name,
            signal=candidate.matchReason,
            support=_aggregate_dimension_score(dimensions, default=3),
            risk=3,
            freshness=3,
            confidence=min(5, 1 + len(candidate.sourceIds)),
            price=_budget_hint_from_text(candidate.matchReason, zh),
            dimensions=dimensions,
            metrics={"sourceCount": len(candidate.sourceIds)},
            evidence=sorted(row_evidence),
        ))
    return rows


def _dimension_key(value: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", value):
        return "dim-" + str(sum((idx + 1) * ord(char) for idx, char in enumerate(value)) % 100000)
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value.lower()).strip("-")[:48] or "dimension"


def _decision_recommendation(
    candidates: list[DecisionCandidate],
    comparisons: list[DimensionComparison],
    risks: list[str],
    zh: bool,
) -> dict[str, object]:
    scores = {candidate.name: len(candidate.sourceIds) * 3 for candidate in candidates}
    value_by_candidate: dict[str, list[DimensionComparisonValue]] = defaultdict(list)
    for comparison in comparisons:
        for value in comparison.values:
            value_by_candidate[value.candidate].append(value)
            scores[value.candidate] = scores.get(value.candidate, 0) + {"green": 4, "yellow": 2, "gray": 1}.get(value.confidence, 1)
    ordered = sorted(candidates, key=lambda item: scores.get(item.name, 0), reverse=True)
    primary = ordered[0].name if ordered else ""
    backup = ordered[1].name if len(ordered) > 1 else primary
    caution = ordered[-1].name if len(ordered) > 2 else ("证据不足的候选" if zh else "thin-evidence candidates")
    primary_values = value_by_candidate.get(primary, [])
    top_conditions = [
        f"{value.condition}：{value.conclusion}" if value.condition else value.conclusion
        for value in primary_values[:2]
    ]
    source_ids = sorted({source_id for value in primary_values for source_id in value.sourceIds}) or (ordered[0].sourceIds if ordered else [])
    risks_text = "、".join(risks[:3]) if zh else ", ".join(risks[:3])
    if zh:
        body = (
            f"首选：建议买 {primary}。如果你更看重 {comparisons[0].dimension if comparisons else '核心体验'}，优先选 {primary}；"
            f"如果价格、渠道或佩戴/系统偏好更适合 {backup}，可以把 {backup} 作为备选。"
            f"不推荐的情况：你的主要场景正好命中 {risks_text or '矩阵中的黄色/灰色弱证据或矛盾场景'}，或无法接受打开来源后看到的反例。慎选：{caution}。"
        )
        bullets = [
            (f"首选：{primary}；理由是来源覆盖和高置信维度最集中。", source_ids),
            (f"备选：{backup}；当价格、渠道或个人偏好更匹配时选择。", ordered[1].sourceIds if len(ordered) > 1 else source_ids),
            (f"慎选/不推荐：{caution}；先核对矛盾条件和弱证据。", ordered[-1].sourceIds if ordered else source_ids),
        ]
    else:
        body = (
            f"Buy {primary}. If you care most about {comparisons[0].dimension if comparisons else 'the core experience'}, choose {primary}; "
            f"if price, channel or fit preferences favor {backup}, use {backup} as the backup. "
            f"Do not buy when your main scenario matches {risks_text or 'yellow/gray weak or contradictory evidence in the matrix'}. Caution: {caution}."
        )
        bullets = [
            (f"Top pick: {primary}; it has the most concentrated source coverage and high-confidence dimensions.", source_ids),
            (f"Backup: {backup}; choose it when price, channel or preference fits better.", ordered[1].sourceIds if len(ordered) > 1 else source_ids),
            (f"Caution/not recommended: {caution}; verify contradictions and weak evidence first.", ordered[-1].sourceIds if ordered else source_ids),
        ]
    return {
        "body": body,
        "bullets": bullets,
        "sourceIds": source_ids,
        "data": {
            "primary": primary,
            "backup": backup,
            "notRecommended": caution,
            "conditions": top_conditions,
            "scores": scores,
        },
    }


def _decision_need_summary(need: str, dimensions: list[str], confidence: str, zh: bool) -> str:
    budget = _budget_hint_from_text(need, zh)
    dim_text = "、".join(dimensions[:5]) if zh else ", ".join(dimensions[:5])
    if zh:
        return f"我理解你的需求是：{budget}，围绕「{need}」做购买决策；当前最该确认的维度是 {dim_text or '来源中重复出现的产品属性'}。请确认预算、使用场景和不能接受的短板是否准确。当前置信度为 {confidence}。"
    return f"I understand your need as: {budget}, making a purchase decision for '{need}'. The dimensions to confirm are {dim_text or 'repeated product attributes from sources'}. Please verify budget, use case and unacceptable trade-offs. Current confidence: {confidence}."


def _budget_hint_from_text(text: str, zh: bool) -> str:
    match = re.search(r"(\d{3,6})\s*(?:元|块|rmb|cny|usd|以内|左右)?", text, flags=re.IGNORECASE)
    if match:
        return (f"预算约 {match.group(1)}" if zh else f"budget around {match.group(1)}")
    return "预算未明确" if zh else "budget not explicit"


def _ids_from_comparisons(comparisons: list[DimensionComparison]) -> list[int]:
    ids = sorted({
        source_id
        for comparison in comparisons
        for value in comparison.values
        for source_id in value.sourceIds
    })
    return ids


def _source_text(source: Source) -> str:
    transcript = max(
        [getattr(source, "fullTranscript", ""), getattr(source, "transcriptText", ""), source.transcriptPreview],
        key=len,
    )
    return " ".join([source.title, source.summary, source.transcriptPreview, transcript[:6000], *(c.text for c in source.comments[:8])])


def _aggregate_dimension_score(dimensions: list[ComparisonDimension], default: int) -> int:
    scores = [dimension.score for dimension in dimensions if dimension.score]
    if not scores:
        return default
    return max(1, min(5, round(sum(scores) / len(scores))))


def _coverage(sources: list[Source], run_logs: list[RunLog]) -> CoverageSummary:
    return CoverageSummary(
        totalSources=len(sources),
        totalComments=sum(len(source.comments) for source in sources),
        platformCount=len({source.platform for source in sources}),
        citedSources=sum(1 for source in sources if source.citationCount > 0),
        withComments=sum(1 for source in sources if source.comments),
        withTranscripts=sum(1 for source in sources if source.transcriptPreview or getattr(source, "fullTranscript", "") or getattr(source, "transcriptText", "")),
        providerRuns=len(run_logs),
        successfulProviderRuns=sum(1 for log in run_logs if log.ok),
        failedProviderRuns=sum(1 for log in run_logs if not log.ok),
    )


def _insights(
    query: str,
    zh: bool,
    sources: list[Source],
    terms: list[str],
    risks: list[str],
    citations: list[int],
    confidence: str,
    coverage: CoverageSummary,
) -> list[ReportInsight]:
    confidence_score = {"high": 5, "medium": 4, "low": 2, "insufficient": 1}.get(confidence, 3)
    if not sources:
        return [
            ReportInsight(
                id="coverage-gap",
                kind="coverage",
                label="证据不足" if zh else "Insufficient evidence",
                summary=(
                    f"没有为「{query}」收集到可引用来源，当前只能展示抓取状态与下一步建议。"
                    if zh
                    else f"No citable source was collected for '{query}', so only retrieval status and next steps are available."
                ),
                confidence=1,
                sourceIds=[],
            )
        ]

    primary_terms = "、".join(terms[:3]) if zh else ", ".join(terms[:3])
    platform_text = str(coverage.platformCount)
    insights = [
        ReportInsight(
            id="initial-answer",
            kind="answer",
            label="初步回答" if zh else "Initial answer",
            summary=(
                f"围绕「{query}」，当前最稳定的观察维度是 {primary_terms or query}；仍需要打开引用来源复核语境。"
                if zh
                else f"For '{query}', the most stable dimensions are {primary_terms or query}; cited sources still need context checks."
            ),
            confidence=confidence_score,
            sourceIds=citations[:4],
        ),
        ReportInsight(
            id="cross-platform-coverage",
            kind="coverage",
            label="覆盖情况" if zh else "Coverage",
            summary=(
                f"本轮覆盖 {platform_text} 个平台、{coverage.totalSources} 条来源、{coverage.totalComments} 条评论样本。"
                if zh
                else f"This run covers {platform_text} platform(s), {coverage.totalSources} sources and {coverage.totalComments} sampled comments."
            ),
            confidence=min(5, 1 + coverage.platformCount),
            sourceIds=citations[:3],
        ),
    ]
    if risks:
        insights.append(ReportInsight(
            id="risk-checks",
            kind="risk",
            label="需要复核的风险" if zh else "Risks to verify",
            summary=(
                f"高频风险/分歧词包括：{'、'.join(risks[:4])}。"
                if zh
                else f"Repeated risk/disagreement terms include: {', '.join(risks[:4])}."
            ),
            confidence=max(1, min(5, len(risks))),
            sourceIds=citations[1:4] or citations[:3],
        ))
    else:
        insights.append(ReportInsight(
            id="no-strong-disagreement",
            kind="consensus",
            label="暂未发现强分歧" if zh else "No strong disagreement yet",
            summary=(
                "当前样本未出现明确高频负面词，但这不等于没有风险，仍要人工复核评论区反例。"
                if zh
                else "No repeated negative term was detected, but absence of evidence is not absence of risk; inspect comment counterexamples."
            ),
            confidence=3,
            sourceIds=citations[:3],
        ))
    return insights


def _infer_report_kind(text: str) -> str:
    lowered = (text or "").lower()
    if any(token in lowered for token in ["对比", "比较", "vs", "versus", "compare", "comparison"]):
        return "comparison"
    if any(token in lowered for token in ["值得", "买吗", "购买", "选择", "推荐", "should i", "worth", "buy"]):
        return "decision"
    consumer_tokens = ["手机", "耳机", "笔记本", "平板", "相机", "iphone", "ipad", "macbook", "headphone", "laptop", "tablet", "camera"]
    budget_tokens = ["以内", "左右", "预算", "价位", "元", "块", "under", "budget"]
    preference_tokens = ["好的", "好用", "适合", "更好", "best", "good", "better"]
    if any(token in lowered for token in consumer_tokens) and (
        any(token in lowered for token in budget_tokens) or any(token in lowered for token in preference_tokens)
    ):
        return "decision"
    if any(token in lowered for token in ["趋势", "格局", "市场", "舆情", "landscape", "trend", "market"]):
        return "landscape"
    if any(token in lowered for token in ["为什么", "如何", "怎么", "原因", "why", "how"]):
        return "explainer"
    return "general"


def _report_kind_label(kind: str, zh: bool) -> str:
    labels = {
        "comparison": ("对比分析", "comparison"),
        "decision": ("决策辅助", "decision support"),
        "landscape": ("趋势/格局扫描", "landscape scan"),
        "explainer": ("解释型研究", "explainer"),
        "general": ("通用研究", "general research"),
    }
    value = labels.get(kind, labels["general"])
    return value[0] if zh else value[1]


def _channel_counts(sources: list[Source]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for source in sources:
        counter.update(source.evidenceChannels or source.metrics.get("evidence_channels") or [])
    return dict(counter)


def _domain_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.replace("www.", "")
    except ValueError:
        return ""


def _infer_source_type(source: Source) -> str:
    media_type = str(source.metrics.get("media_type") or source.metrics.get("content_type") or "").lower()
    if source.platform in {"bilibili", "douyin", "youtube"}:
        return "video"
    if source.platform == "xiaohongshu":
        if "video" in media_type or source.metrics.get("video_url"):
            return "video"
        return "note"
    if source.platform == "zhihu":
        if "zvideo" in media_type or "video" in media_type:
            return "video"
        if "answer" in media_type:
            return "answer"
        return "article"
    return "content"


def _decorate_source(source: Source, query: str, generated_at: datetime) -> None:
    provider = str(source.metrics.get("source_provider") or source.provider or "")
    source.provider = provider
    source.author = source.author or source.creator
    source.domain = source.domain or _domain_from_url(source.url)
    source.sourceType = _infer_source_type(source)
    source.collectedAt = source.collectedAt or generated_at.isoformat(timespec="seconds")
    channels = []
    if source.title:
        channels.append("title")
    if source.comments:
        channels.append("comments")
    has_transcript = bool(source.transcriptPreview or getattr(source, "fullTranscript", "") or getattr(source, "transcriptText", ""))
    if has_transcript:
        channels.append("transcript")
    if source.url:
        channels.append("url")

    evidence_score = int(source.metrics.get("evidence_score") or 0)
    if not evidence_score:
        evidence_score = len(source.comments) * 2 + (8 if has_transcript else 0) + (3 if source.url else 0) + (2 if source.title else 0)
    source.evidenceScore = min(100, evidence_score)
    source.metrics["evidence_score"] = source.evidenceScore
    source.metrics["evidence_channels"] = channels
    source.evidenceChannels = channels

    query_terms = set(_tokenize(query))
    haystack = " ".join([source.title, source.summary, source.transcriptPreview, " ".join(c.text for c in source.comments[:5])]).lower()
    matches = [term for term in query_terms if term and term.lower() in haystack]
    source.relevanceScore = min(100, 35 + len(matches) * 15 + min(30, source.evidenceScore // 2)) if query_terms else min(100, 50 + source.evidenceScore)
    source.whyRelevant = (
        f"匹配关键词：{', '.join(matches[:4])}" if matches else "标题或摘要与研究问题相关"
    )
    if not source.summary:
        source.summary = _text_excerpt([source.title, source.transcriptPreview, *[c.text for c in source.comments[:3]]], 260)
    source.highlights = _highlights(source)
    source.badges = _badges(source)
    source.status = "weak" if source.evidenceScore < 5 else "ranked"
    source.quality = {
        "evidenceScore": source.evidenceScore,
        "relevanceScore": source.relevanceScore,
        "citationCount": source.citationCount,
        "hasComments": bool(source.comments),
        "hasTranscript": has_transcript,
        "channelCount": len(channels),
        "sourceType": source.sourceType,
        "provider": source.provider,
    }


def _apply_citation_counts(sources: list[Source], takeaways: list[CitationText], sections: list[ReportSection]) -> None:
    counts: Counter[int] = Counter()
    for item in takeaways:
        counts.update(item.citations)
    for section in sections:
        counts.update(section.sourceIds)
        for item in section.bullets:
            counts.update(item.citations)
        for row in section.table:
            counts.update(row.evidence)
        if section.quote:
            counts.update([section.quote.sourceId])
    for source in sources:
        source.citationCount = counts[source.id]
        source.quality["citationCount"] = source.citationCount
        if source.citationCount:
            source.status = "cited"


def _outline_from_sections(sections: list[ReportSection], sources: list[Source], zh: bool) -> list[OutlineItem]:
    items: list[OutlineItem] = []
    for section in sections:
        source_ids = sorted({
            citation
            for citation in section.sourceIds
        } | {
            citation
            for bullet in section.bullets
            for citation in bullet.citations
        } | {
            citation
            for row in section.table
            for citation in row.evidence
        } | ({section.quote.sourceId} if section.quote else set()))
        items.append(OutlineItem(
            id=section.id,
            label=re.sub(r"^\d+\.\s*", "", section.title),
            title=section.title,
            summary=(section.body[:80] + "...") if len(section.body) > 80 else section.body,
            status="completed",
            sourceIds=source_ids,
            citationCount=len(source_ids),
        ))
    return items


def _platform_summaries(sources: list[Source], run_logs: list[RunLog], is_demo: bool) -> list[PlatformSummary]:
    counts = Counter(s.platform for s in sources)
    logs_by_platform: dict[str, list[RunLog]] = defaultdict(list)
    for log in run_logs:
        logs_by_platform[log.platform].append(log)

    summaries: list[PlatformSummary] = []
    for pid in PLATFORM_ORDER:
        logs = logs_by_platform.get(pid, [])
        if is_demo:
            status = "demo"
        elif counts.get(pid, 0):
            status = "ok"
        elif logs and all(not log.ok for log in logs):
            status = "failed"
        else:
            status = "partial"
        note = "; ".join(log.note for log in logs if log.note)[:180]
        summaries.append(PlatformSummary(
            id=pid,  # type: ignore[arg-type]
            name=PLATFORM_META[pid]["name"],
            logo=PLATFORM_META[pid]["logo"],
            count=counts.get(pid, 0),
            status=status,  # type: ignore[arg-type]
            note=note,
        ))
    return summaries


def _ui_state(status: str, platforms: list[PlatformSummary], sources: list[Source], warnings: list[str], zh: bool) -> ReportUIState:
    stage_status = "completed" if status in {"completed", "partial"} else status
    labels = {
        "plan": "规划问题" if zh else "Plan query",
        "search": "搜索来源" if zh else "Search sources",
        "evidence": "整理证据" if zh else "Structure evidence",
        "synthesis": "生成报告" if zh else "Synthesize report",
    }
    stages = [
        ResearchStage(id="plan", label=labels["plan"], status="completed", progress=100),
        ResearchStage(id="search", label=labels["search"], status=stage_status, progress=100 if sources else 45, message=f"{len(sources)} sources"),
        ResearchStage(id="evidence", label=labels["evidence"], status=stage_status, progress=100 if sources else 30),
        ResearchStage(id="synthesis", label=labels["synthesis"], status=stage_status, progress=100 if status in {"completed", "partial"} else 30),
    ]
    groups = [
        SourceGroup(
            id=p.id,
            name=p.name,
            count=p.count,
            citedCount=sum(1 for s in sources if s.platform == p.id and s.citationCount > 0),
            status="completed" if p.count else ("failed" if p.status == "failed" else "partial"),
            note=p.note,
        )
        for p in platforms
    ]
    return ReportUIState(
        activeStage="synthesis" if status in {"completed", "partial"} else "search",
        progress=100 if status in {"completed", "partial"} else 45,
        stages=stages,
        sourceGroups=groups,
        interactionHints={
            "citations": "悬停或点击引用编号可高亮右侧来源" if zh else "Hover or click citation IDs to highlight sources",
            "sources": "按平台筛选来源，优先打开被多次引用的卡片" if zh else "Filter sources by platform and open repeatedly cited cards first",
            "outline": "左侧目录来自后端 outline，每个条目带 citationCount/sourceIds" if zh else "The outline is backend-driven and carries citationCount/sourceIds",
            "warnings": " / ".join(warnings[:2]),
        },
    )


def _title_from_query(query: str, zh: bool) -> str:
    clean = query.strip() or ("未命名研究" if zh else "Untitled research")
    return clean if len(clean) <= 48 else clean[:48] + "..."


def _keywords(sources: list[Source], query: str) -> list[str]:
    counter: Counter[str] = Counter()
    corpus = " ".join([query, *[s.title for s in sources], *[s.summary for s in sources]])
    for token in _tokenize(corpus):
        key = token.lower()
        if len(key) > 1 and key not in STOPWORDS:
            counter[key] += 1
    return [word for word, _ in counter.most_common(12)]


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9+\-_.]*|[\u4e00-\u9fff]{2,}", text or "")
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{5,}", token):
            expanded.extend(token[i : i + 2] for i in range(0, min(len(token) - 1, 10)))
    return expanded


def _risk_terms(sources: list[Source]) -> list[str]:
    counter: Counter[str] = Counter()
    corpus = " ".join(
        " ".join([
            s.title,
            s.summary,
            s.transcriptPreview,
            " ".join(c.text for c in s.comments[:8]),
        ])
        for s in sources
    )
    text = corpus.lower()
    for term in RISK_TERMS:
        if term.lower() in text:
            counter[term] += text.count(term.lower())
    return [term for term, _ in counter.most_common(8)]


def _confidence(sources: list[Source], run_logs: list[RunLog]) -> str:
    platform_count = len({s.platform for s in sources})
    comment_count = sum(len(s.comments) for s in sources)
    transcript_count = sum(1 for s in sources if s.transcriptPreview or getattr(s, "fullTranscript", "") or getattr(s, "transcriptText", ""))
    ok_logs = sum(1 for log in run_logs if log.ok)
    score = len(sources) * 8 + platform_count * 12 + min(30, comment_count) + transcript_count * 8 + ok_logs * 4
    if score >= 95:
        return "high"
    if score >= 55:
        return "medium"
    if score >= 20:
        return "low"
    return "insufficient"


def _warnings(sources: list[Source], run_logs: list[RunLog], is_demo: bool, zh: bool) -> list[str]:
    warnings: list[str] = []
    if is_demo:
        warnings.append("当前是示例/非实时结果。" if zh else "This is a demo or non-live result.")
    if not sources:
        warnings.append("没有可引用来源，报告不会生成事实性判断。" if zh else "No citable sources were collected; factual claims are not generated.")
    failed = [log for log in run_logs if not log.ok]
    if failed:
        names = ", ".join(f"{log.platform}/{log.provider}" for log in failed[:3])
        warnings.append((f"部分抓取器失败：{names}。" if zh else f"Some providers failed: {names}."))
    if sources and len({s.platform for s in sources}) == 1:
        warnings.append("当前证据只来自单个平台，跨平台共识不足。" if zh else "Evidence comes from one platform only; cross-platform agreement is limited.")
    if sources and not any(s.comments or s.transcriptPreview or getattr(s, "fullTranscript", "") or getattr(s, "transcriptText", "") for s in sources):
        warnings.append("多数来源只有标题/元数据，缺少评论或字幕证据。" if zh else "Most sources only have title/metadata evidence; comments or transcripts are missing.")
    return warnings


def _report_status(sources: list[Source], warnings: list[str], is_demo: bool) -> str:
    if not sources:
        return "partial" if is_demo else "failed"
    return "partial" if warnings else "completed"


def _quote_card(source: Source, zh: bool) -> VideoQuote:
    return VideoQuote(
        sourceId=source.id,
        quote=_quote_from_source(source, zh),
        author=f"— {source.creator or source.platform}",
        thumbnail=source.thumbnail,
        duration=source.duration,
    )


def _quote_from_source(source: Source, zh: bool) -> str:
    if source.comments:
        return source.comments[0].text[:160]
    transcript = source.transcriptPreview or getattr(source, "fullTranscript", "") or getattr(source, "transcriptText", "")
    if transcript:
        return transcript[:160]
    return (f"{source.title} 是本轮排序靠前的来源，建议打开原视频核对语境。" if zh else f"{source.title} is a top-ranked source in this run; open it to verify context.")


def _source_signal(source: Source, zh: bool) -> str:
    channels = "、".join(source.metrics.get("evidence_channels", []) or source.badges[:3])
    summary = source.summary or source.transcriptPreview or source.title
    if zh:
        return f"{source.platform} / {source.creator or 'creator'}：{summary[:110]}；证据分 {source.evidenceScore}，渠道：{channels or '标题'}。"
    return f"{source.platform} / {source.creator or 'creator'}: {summary[:110]}; evidence score {source.evidenceScore}, channels: {channels or 'title'}."


def _risk_bullets(sources: list[Source], risks: list[str], zh: bool) -> list[CitationText]:
    bullets: list[CitationText] = []
    if risks:
        for risk in risks[:4]:
            ids = [s.id for s in sources if risk.lower() in " ".join([s.title, s.summary, *(c.text for c in s.comments[:5])]).lower()][:3]
            bullets.append(CitationText(
                text=(f"复核「{risk}」是否只是个别评论，还是多个来源都反复提到。" if zh else f"Check whether '{risk}' is isolated or repeated across multiple sources."),
                citations=ids or [s.id for s in sources[:2]],
            ))
    else:
        bullets.append(CitationText(
            text=("未发现明确高频负面词；仍建议人工查看评论区反例。" if zh else "No repeated negative term was detected; still inspect comment counterexamples manually."),
            citations=[s.id for s in sources[:3]],
        ))
    return bullets


def _signal_rows(sources: list[Source], terms: list[str], zh: bool) -> list[ComparisonRow]:
    if not sources:
        return []
    rows: list[ComparisonRow] = []
    names = terms[:5] or [s.platform for s in sources[:5]]
    for idx, name in enumerate(names[:5]):
        haystack_matches = [
            s
            for s in sources
            if name.lower() in " ".join([s.title, s.summary, s.transcriptPreview]).lower()
        ] or sources[idx : idx + 3] or sources[:3]
        evidence = [s.id for s in haystack_matches[:4]]
        support = min(5, 2 + len([s for s in haystack_matches if _has_any(s, POSITIVE_TERMS)]))
        risk = min(5, 2 + len([s for s in haystack_matches if _has_any(s, RISK_TERMS)]))
        confidence = min(5, 1 + len(evidence) + (1 if any(s.comments for s in haystack_matches) else 0))
        freshness = 4 if any(s.published for s in haystack_matches) else 3
        signal = (
            f"{len(evidence)} 条来源提到或关联该信号"
            if zh
            else f"{len(evidence)} source(s) mention or relate to this signal"
        )
        rows.append(ComparisonRow(
            name=name,
            signal=signal,
            support=support,
            risk=risk,
            freshness=freshness,
            confidence=confidence,
            camera=confidence,
            lowLight=support,
            video=max(1, 6 - risk),
            battery=freshness,
            price="需复核" if zh else "Verify",
            metrics={
                "sourceCount": len(haystack_matches),
                "commentSources": sum(1 for s in haystack_matches if s.comments),
                "transcriptSources": sum(1 for s in haystack_matches if s.transcriptPreview),
                "platforms": sorted({s.platform for s in haystack_matches}),
            },
            evidence=evidence,
        ))
    return rows


def _has_any(source: Source, terms: set[str]) -> bool:
    text = " ".join([source.title, source.summary, source.transcriptPreview, *(c.text for c in source.comments[:8])]).lower()
    return any(term.lower() in text for term in terms)


def _platform_sentence(sources: list[Source], zh: bool) -> str:
    counts = Counter(s.platform for s in sources)
    if not counts:
        return ""
    parts = [f"{PLATFORM_META[p]['name']} {count}" for p, count in counts.most_common()]
    joined = "、".join(parts) if zh else ", ".join(parts)
    return (f"平台覆盖：{joined}。" if zh else f"Platform coverage: {joined}. ")


def _evidence_sentence(sources: list[Source], zh: bool) -> str:
    with_comments = sum(1 for s in sources if s.comments)
    with_transcripts = sum(1 for s in sources if s.transcriptPreview or getattr(s, "fullTranscript", "") or getattr(s, "transcriptText", ""))
    if zh:
        return f"其中 {with_comments} 条带评论样本，{with_transcripts} 条带字幕/文本片段。"
    return f"{with_comments} source(s) include sampled comments and {with_transcripts} include transcript/text snippets. "


def _risk_sentence(risks: list[str], zh: bool) -> str:
    if risks:
        return "、".join(risks[:5]) if zh else ", ".join(risks[:5])
    return "评论区反例、发布时间、样本场景" if zh else "comment counterexamples, publish date and sample context"


def _run_log_summary(run_logs: list[RunLog], zh: bool) -> str:
    if not run_logs:
        return "本次没有实时抓取日志。" if zh else "No live retrieval logs were produced."
    ok = sum(1 for log in run_logs if log.ok)
    failed = len(run_logs) - ok
    if zh:
        return f"抓取器运行 {len(run_logs)} 次，成功 {ok} 次，失败/空结果 {failed} 次。"
    return f"Providers ran {len(run_logs)} time(s): {ok} succeeded and {failed} failed or returned empty results."


def _badges(source: Source) -> list[str]:
    badges = [source.platform]
    if source.provider:
        badges.append(source.provider)
    if source.comments:
        badges.append(f"{len(source.comments)} comments")
    if source.transcriptPreview or getattr(source, "fullTranscript", "") or getattr(source, "transcriptText", ""):
        badges.append("transcript")
    if source.url:
        badges.append("openable")
    return badges[:5]


def _highlights(source: Source) -> list[str]:
    values = [c.text for c in source.comments[:2]]
    transcript = source.transcriptPreview or getattr(source, "fullTranscript", "") or getattr(source, "transcriptText", "")
    if transcript:
        values.append(transcript[:160])
    if not values and source.summary:
        values.append(source.summary[:160])
    return [v for v in values if v][:3]


def _methodology(zh: bool) -> list[str]:
    if zh:
        return [
            "把用户问题扩展成平台搜索词，并保留 canonical query。",
            "按平台并发启动抓取器，并在单个平台内并发补充多个视频/内容的评论或字幕。",
            "按 URL/标题去重，避免同一视频重复计数。",
            "按评论、字幕、URL、标题完整度计算 evidenceScore。",
            "报告中的 citations/sourceIds 均来自后端，前端只负责定位和高亮。",
        ]
    return [
        "Expand the user need into platform-specific search targets while preserving the canonical query.",
        "Run platform crawlers concurrently and enrich multiple videos/content items per platform in parallel.",
        "Deduplicate sources by normalized URL/title.",
        "Score evidence by comments, transcripts, URL and title completeness.",
        "Citations/sourceIds are backend-owned; the frontend only highlights and navigates them.",
    ]


def _text_excerpt(parts: list[str], limit: int = 220) -> str:
    joined = " ".join(p.strip() for p in parts if p and p.strip())
    joined = re.sub(r"\s+", " ", joined)
    return joined[:limit]
