from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from pydantic import TypeAdapter

from app.models import CitationText, CoverageSummary, ReportInsight, ReportSection, Source
from app.utils import extract_first_json, text_excerpt


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


def synthesize_with_llm(
    *,
    need: str,
    query: str,
    lang: str,
    sources: list[Source],
    coverage: CoverageSummary,
    report_kind: str,
) -> LlmSynthesisResult | None:
    if not _enabled() or not sources:
        return None
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENROUTER_MODEL", "z-ai/glm-5.1")
    semantic_result = extract_semantic_evidence_with_llm(
        need=need,
        query=query,
        lang=lang,
        sources=sources,
        report_kind=report_kind,
    )
    semantic_evidence = semantic_result.evidence if semantic_result else []
    selection = select_sources_with_llm(
        need=need,
        query=query,
        lang=lang,
        sources=sources,
        coverage=coverage,
        report_kind=report_kind,
        semantic_evidence=semantic_evidence,
    )
    synthesis_sources = selection.sources if selection and selection.sources else sources
    selected_source_ids = [source.id for source in synthesis_sources]
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt(lang)},
            {
                "role": "user",
                "content": _user_prompt(
                    need=need,
                    query=query,
                    lang=lang,
                    sources=synthesis_sources,
                    coverage=coverage,
                    report_kind=report_kind,
                    selected_source_ids=selected_source_ids,
                    total_source_count=len(sources),
                    semantic_evidence=semantic_evidence,
                ),
            },
        ],
        "temperature": float(os.getenv("OPENROUTER_TEMPERATURE", "0.25")),
        "max_tokens": int(os.getenv("OPENROUTER_MAX_TOKENS", "5000")),
        "response_format": {"type": "json_object"},
    }
    content = _post_chat_completion(api_key, payload)
    parsed = _parse_json(content)
    result = _result_from_payload(parsed, valid_ids=set(selected_source_ids))
    if selection and selection.warnings:
        result.warnings = [*selection.warnings, *result.warnings][:6]
    if semantic_result and semantic_result.warnings:
        result.warnings = [*semantic_result.warnings, *result.warnings][:6]
    result.model = model
    return result


def extract_semantic_evidence_with_llm(
    *,
    need: str,
    query: str,
    lang: str,
    sources: list[Source],
    report_kind: str,
) -> SemanticEvidenceExtractionResult | None:
    if not _enabled() or not sources:
        return None
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENROUTER_MODEL", "z-ai/glm-5.1")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _semantic_system_prompt(lang)},
            {
                "role": "user",
                "content": _semantic_extraction_prompt(
                    need=need,
                    query=query,
                    lang=lang,
                    sources=sources,
                    report_kind=report_kind,
                ),
            },
        ],
        "temperature": float(os.getenv("OPENROUTER_EXTRACTION_TEMPERATURE", "0.1")),
        "max_tokens": int(os.getenv("OPENROUTER_EXTRACTION_MAX_TOKENS", "3500")),
        "response_format": {"type": "json_object"},
    }
    content = _post_chat_completion(api_key, payload)
    parsed = _parse_json(content)
    valid_ids = {source.id for source in sources}
    return SemanticEvidenceExtractionResult(
        evidence=_sanitize_semantic_evidence(parsed.get("evidence", parsed.get("semanticEvidence", [])), valid_ids),
        warnings=[str(item)[:240] for item in parsed.get("warnings", []) if str(item).strip()][:6],
        model=model,
    )


def select_sources_with_llm(
    *,
    need: str,
    query: str,
    lang: str,
    sources: list[Source],
    coverage: CoverageSummary,
    report_kind: str,
    semantic_evidence: list[SemanticEvidenceExtraction] | None = None,
    max_sources: int | None = None,
) -> SourceSelectionResult | None:
    if not _enabled() or not sources:
        return None
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENROUTER_MODEL", "z-ai/glm-5.1")
    max_selected = max_sources or int(os.getenv("VOXLENS_LLM_SELECTED_SOURCE_LIMIT", "24"))
    max_selected = max(1, min(max_selected, len(sources)))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _selection_system_prompt(lang)},
            {
                "role": "user",
                "content": _selection_prompt(
                    need=need,
                    query=query,
                    lang=lang,
                    sources=sources,
                    coverage=coverage,
                    report_kind=report_kind,
                    semantic_evidence=semantic_evidence or [],
                    max_sources=max_selected,
                ),
            },
        ],
        "temperature": float(os.getenv("OPENROUTER_SELECTION_TEMPERATURE", "0.1")),
        "max_tokens": int(os.getenv("OPENROUTER_SELECTION_MAX_TOKENS", "1800")),
        "response_format": {"type": "json_object"},
    }
    content = _post_chat_completion(api_key, payload)
    parsed = _parse_json(content)
    selected_ids = _valid_ids(
        parsed.get("selectedSourceIds", parsed.get("sourceIds", parsed.get("sources", []))),
        {source.id for source in sources},
        limit=max_selected,
    )
    sources_by_id = {source.id: source for source in sources}
    selected_sources = [sources_by_id[source_id] for source_id in selected_ids if source_id in sources_by_id]
    warnings = [str(item)[:240] for item in parsed.get("warnings", []) if str(item).strip()]
    return SourceSelectionResult(
        sources=selected_sources,
        source_ids=selected_ids,
        warnings=warnings[:6],
        model=model,
    )


def _enabled() -> bool:
    return os.getenv("VOXLENS_ENABLE_LLM", "true").strip().lower() not in {"0", "false", "no", "off"}


def _post_chat_completion(api_key: str, payload: dict[str, Any]) -> str:
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {api_key}",
        "http-referer": os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:8765"),
        "x-title": os.getenv("OPENROUTER_X_TITLE", "VoxLens Alpha"),
    }
    timeout = int(os.getenv("OPENROUTER_TIMEOUT", "90"))
    req = urllib.request.Request(f"{base_url}/chat/completions", data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - OpenRouter endpoint is user-configurable
        body = json.loads(response.read().decode("utf-8"))
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter returned no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise RuntimeError("OpenRouter returned empty content")
    return str(content)


def _parse_json(content: str) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        value = extract_first_json(content)
    if not isinstance(value, dict):
        raise ValueError("LLM synthesis payload is not an object")
    return value


def _result_from_payload(payload: dict[str, Any], valid_ids: set[int]) -> LlmSynthesisResult:
    takeaways = TypeAdapter(list[CitationText]).validate_python(_sanitize_citation_items(payload.get("takeaways", []), valid_ids))
    insights = TypeAdapter(list[ReportInsight]).validate_python(_sanitize_insights(payload.get("insights", []), valid_ids))
    sections = TypeAdapter(list[ReportSection]).validate_python(_sanitize_sections(payload.get("sections", []), valid_ids))
    warnings = [str(item)[:240] for item in payload.get("warnings", []) if str(item).strip()]
    return LlmSynthesisResult(takeaways=takeaways[:6], insights=insights[:6], sections=sections[:8], warnings=warnings[:6])


def _sanitize_citation_items(items: Any, valid_ids: set[int]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return sanitized
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        sanitized.append({"text": text, "citations": _valid_ids(item.get("citations", item.get("sourceIds", [])), valid_ids)})
    return sanitized


def _sanitize_insights(items: Any, valid_ids: set[int]) -> list[dict[str, Any]]:
    allowed = {"answer", "consensus", "disagreement", "risk", "opportunity", "coverage"}
    sanitized: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return sanitized
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        if not label:
            continue
        kind = str(item.get("kind", "consensus"))
        sanitized.append({
            "id": _safe_id(str(item.get("id", f"insight-{idx}"))),
            "kind": kind if kind in allowed else "consensus",
            "label": label,
            "summary": str(item.get("summary", ""))[:360],
            "confidence": _int_range(item.get("confidence", 3), 1, 5),
            "sourceIds": _valid_ids(item.get("sourceIds", item.get("citations", [])), valid_ids),
        })
    return sanitized


def _sanitize_sections(items: Any, valid_ids: set[int]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return sanitized
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        body = str(item.get("body", "")).strip()
        if not title or not body:
            continue
        section = {
            "id": _safe_id(str(item.get("id", f"section-{idx}"))),
            "title": title,
            "kind": str(item.get("kind", "narrative"))[:40],
            "level": _int_range(item.get("level", 1), 1, 3),
            "body": body,
            "bullets": _sanitize_citation_items(item.get("bullets", []), valid_ids),
            "quote": None,
            "table": _sanitize_table_rows(item.get("table", []), valid_ids),
            "sourceIds": _valid_ids(item.get("sourceIds", item.get("citations", [])), valid_ids),
            "metrics": item.get("metrics", {}) if isinstance(item.get("metrics"), dict) else {},
            "data": item.get("data", {}) if isinstance(item.get("data"), dict) else {},
        }
        sanitized.append(section)
    return sanitized


def _sanitize_table_rows(items: Any, valid_ids: set[int]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return sanitized
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        sanitized.append({
            "name": name[:120],
            "signal": str(item.get("signal", ""))[:260],
            "support": _int_range(item.get("support", item.get("lowLight", 3)), 1, 5),
            "risk": _int_range(item.get("risk", 3), 1, 5),
            "freshness": _int_range(item.get("freshness", item.get("battery", 3)), 1, 5),
            "confidence": _int_range(item.get("confidence", item.get("camera", 3)), 1, 5),
            "price": str(item.get("price", ""))[:80],
            "dimensions": _sanitize_dimensions(item.get("dimensions", []), valid_ids),
            "metrics": item.get("metrics", {}) if isinstance(item.get("metrics"), dict) else {},
            "evidence": _valid_ids(item.get("evidence", item.get("sourceIds", [])), valid_ids),
        })
    return sanitized


def _sanitize_dimensions(items: Any, valid_ids: set[int]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return sanitized
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", item.get("dimension", ""))).strip()
        label = str(item.get("label", key)).strip()
        if not key or not label:
            continue
        sanitized.append({
            "key": _safe_id(key)[:40],
            "label": label[:80],
            "score": _int_range(item.get("score"), 1, 5) if item.get("score") is not None else None,
            "summary": str(item.get("summary", item.get("conclusion", "")))[:260],
            "evidence": _valid_ids(item.get("evidence", item.get("sourceIds", [])), valid_ids),
            "metrics": item.get("metrics", {}) if isinstance(item.get("metrics"), dict) else {},
        })
    return sanitized[:8]


def _sanitize_semantic_evidence(items: Any, valid_ids: set[int]) -> list[SemanticEvidenceExtraction]:
    if not isinstance(items, list):
        return []
    evidence: list[SemanticEvidenceExtraction] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        source_ids = _valid_ids(item.get("sourceId", item.get("source_id", item.get("sourceIds", []))), valid_ids, limit=1)
        source_id = source_ids[0] if source_ids else 0
        if not source_id:
            continue
        candidate = str(item.get("candidate", item.get("model", item.get("name", "")))).strip()
        dimension = str(item.get("dimension", item.get("key", ""))).strip()
        conclusion = str(item.get("conclusion", item.get("summary", ""))).strip()
        if not dimension or not conclusion:
            continue
        evidence.append(SemanticEvidenceExtraction(
            candidate=candidate[:120],
            dimension=dimension[:80],
            conclusion=conclusion[:360],
            scenario=str(item.get("scenario", ""))[:180],
            value=str(item.get("value", item.get("metric", ""))[:120] if isinstance(item.get("value", item.get("metric", "")), str) else item.get("value", item.get("metric", "")))[:120],
            quote=str(item.get("quote", item.get("excerpt", "")))[:280],
            sourceId=source_id,
            confidence=_int_range(item.get("confidence", 3), 1, 5),
        ))
    return evidence[:80]


def _valid_ids(values: Any, valid_ids: set[int], limit: int | None = None) -> list[int]:
    if isinstance(values, (str, int)):
        values = [values]
    if not isinstance(values, list):
        return []
    ids: list[int] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("id", value.get("sourceId", value.get("source_id")))
        try:
            source_id = int(value)
        except (TypeError, ValueError):
            continue
        if source_id in valid_ids and source_id not in ids:
            ids.append(source_id)
            if limit is not None and len(ids) >= limit:
                break
    return ids


def _safe_id(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug[:48] or "section"


def _int_range(value: Any, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = low
    return max(low, min(high, parsed))


def _selection_system_prompt(lang: str) -> str:
    if lang == "zh":
        return (
            "你是 VoxLens 的证据筛选员。你会看到本轮收集到的全部 sourceCandidates，"
            "任务是选择最值得进入正文合成的高置信视频/内容来源。只输出 JSON。"
        )
    return (
        "You are the evidence selection analyst for VoxLens. You will see every collected sourceCandidate. "
        "Select the highest-confidence sources that should be imported into report synthesis. Return JSON only."
    )


def _semantic_system_prompt(lang: str) -> str:
    if lang == "zh":
        return (
            "你是 VoxLens 的语义证据提取员。你会读取完整字幕/正文分块、评论和来源元数据，"
            "只提取能支撑消费决策的结构化证据。不要写报告，只输出 JSON。"
        )
    return (
        "You are the semantic evidence extraction analyst for VoxLens. Read transcript/content chunks, "
        "comments and metadata, then extract structured evidence for decision-making. Return JSON only."
    )


def _semantic_extraction_prompt(
    *,
    need: str,
    query: str,
    lang: str,
    sources: list[Source],
    report_kind: str,
) -> str:
    zh = lang == "zh"
    dimensions = _decision_dimensions_for_prompt(zh) if report_kind == "decision" else []
    task = (
        "从每个来源中提取候选产品、维度、结论、测试/使用场景、实测值或描述、短引用片段和置信度。"
        "手机推荐场景优先关注预算/价格、续航、拍照、性能、散热；如果证据不足就不要补编。"
        if zh
        else "Extract candidate product, dimension, conclusion, test/use scenario, measured value or description, short quote and confidence from each source. For phone recommendation decisions, prioritize budget/price, battery, camera, performance and thermal behavior; do not invent missing evidence."
    )
    return json.dumps(
        {
            "task": task,
            "need": need,
            "query": query,
            "reportKind": report_kind,
            "priorityDimensions": dimensions,
            "outputSchema": {
                "evidence": [
                    {
                        "candidate": "string",
                        "dimension": "budget|battery|camera|performance|thermal|other",
                        "conclusion": "string",
                        "scenario": "string",
                        "value": "string",
                        "quote": "short source-grounded quote",
                        "sourceId": 1,
                        "confidence": 1,
                    }
                ],
                "warnings": ["string"],
            },
            "sourceEvidencePacks": [_source_evidence_pack(source) for source in sources],
        },
        ensure_ascii=False,
    )


def _selection_prompt(
    *,
    need: str,
    query: str,
    lang: str,
    sources: list[Source],
    coverage: CoverageSummary,
    report_kind: str,
    semantic_evidence: list[SemanticEvidenceExtraction],
    max_sources: int,
) -> str:
    zh = lang == "zh"
    instructions = (
            "从全部候选中选择最能支撑用户问题的高置信来源。优先选择有评论、字幕/文本、摘要、明确 URL、跨平台互证和与问题直接相关的来源；"
            "尤其优先选择 semanticEvidence 能覆盖用户决策维度、解释矛盾场景的来源；避免只因排序靠前或热度高就选择。返回 selectedSourceIds，按推荐引用优先级排序。"
            if zh
            else "Select the highest-confidence sources for the user question from all candidates. Prefer sources with comments, transcript/text, summaries, URLs, cross-platform corroboration, direct relevance and semanticEvidence that covers decision dimensions or explains contradictory scenarios; do not select only because a source appears early or is popular. Return selectedSourceIds in recommended citation priority order."
    )
    evidence_by_source = _semantic_evidence_by_source(semantic_evidence)
    return json.dumps(
        {
            "task": instructions,
            "need": need,
            "query": query,
            "reportKind": report_kind,
            "coverage": coverage.model_dump(),
            "maxSelectedSources": max_sources,
            "outputSchema": {
                "selectedSourceIds": [1],
                "warnings": ["string"],
            },
            "sourceCandidates": [_source_candidate_payload(source, evidence_by_source.get(source.id, [])) for source in sources],
        },
        ensure_ascii=False,
    )


def _system_prompt(lang: str) -> str:
    if lang == "zh":
        return (
            "你是 VoxLens 的证据型视频社媒研究分析师。你必须只依据用户提供的 sources、comments、transcripts 写报告，"
            "所有重要判断都要引用 source id。不要编造没有证据的平台、品牌、数字或用户原话。"
        )
    return (
        "You are the evidence-backed social-video research analyst for VoxLens. Only use the supplied sources, comments and transcripts. "
        "Cite source ids for every important claim. Do not invent platforms, brands, numbers or quotes."
    )


def _user_prompt(
    *,
    need: str,
    query: str,
    lang: str,
    sources: list[Source],
    coverage: CoverageSummary,
    report_kind: str,
    selected_source_ids: list[int] | None = None,
    total_source_count: int | None = None,
    semantic_evidence: list[SemanticEvidenceExtraction] | None = None,
) -> str:
    zh = lang == "zh"
    selected_source_ids = selected_source_ids or [source.id for source in sources]
    semantic_evidence = semantic_evidence or []
    evidence_by_source = _semantic_evidence_by_source(semantic_evidence)
    source_pack = [_source_payload(source, evidence_by_source.get(source.id, [])) for source in sources]
    schema = {
        "takeaways": [{"text": "string", "citations": [1]}],
        "insights": [{"id": "short-id", "kind": "answer|consensus|disagreement|risk|opportunity|coverage", "label": "string", "summary": "string", "confidence": 1, "sourceIds": [1]}],
        "sections": [
            {
                "id": "executive-summary",
                "title": "1. 执行摘要" if zh else "1. Executive Summary",
                "kind": "answer",
                "body": "string",
                "bullets": [{"text": "string", "citations": [1]}],
                "sourceIds": [1],
            }
        ],
        "warnings": ["string"],
    }
    if report_kind == "decision" and _looks_like_phone_query(f"{need} {query}"):
        instructions = (
            "请输出中文 JSON，不要 markdown。手机购买决策报告必须使用四段结构：我的需求、候选机型、维度对比、最终推荐。维度优先覆盖预算/价格、续航、拍照、性能、散热；最终推荐必须包含首选、备选、慎选对象、适合人群和主要反证。"
            if zh
            else "Return English JSON, no markdown. Phone purchase decision reports must use four sections: My Needs, Candidate Phones, Dimension Comparison, Final Recommendation. Prioritize budget/price, battery, camera, performance and thermal behavior; final recommendation must include top pick, backup, caution/not-recommended option, fit and counter-evidence."
        )
    else:
        instructions = (
            "请输出中文 JSON，不要 markdown。报告要像业务团队可读的研究报告：执行摘要、关键发现、证据拆解、风险/分歧、建议动作。"
            if zh
            else "Return English JSON, no markdown. Write for business users: executive summary, findings, evidence, risks/disagreements and recommended actions."
        )
    return json.dumps(
        {
            "task": instructions,
            "need": need,
            "query": query,
            "reportKind": report_kind,
            "coverage": coverage.model_dump(),
            "sourceSelection": {
                "selectedSourceIds": selected_source_ids,
                "selectedSourceCount": len(selected_source_ids),
                "totalCollectedSources": total_source_count if total_source_count is not None else len(sources),
                "selectionMethod": "LLM evidence selection over all collected source candidates",
            },
            "sourceRules": [
                "The sources array is the LLM-selected high-confidence subset from the full collected candidate pool.",
                "Use only source ids present in sources.",
                "Every takeaway and section bullet should have at least one citation when possible.",
                "Mention uncertainty when evidence is thin, single-platform, or mostly title-only.",
                "Do not cite a source unless the claim is supported by its title, summary, comments, or transcriptPreview.",
                "Use semanticEvidence first when it is present; it was extracted from fuller transcript/content chunks before synthesis.",
                "Put the source ids that support each section body in section.sourceIds, even when bullets also carry citations.",
            ],
            "outputSchema": schema,
            "semanticEvidence": [_semantic_evidence_payload(item) for item in semantic_evidence if item.sourceId in selected_source_ids],
            "sources": source_pack,
        },
        ensure_ascii=False,
    )


def _source_candidate_payload(source: Source, semantic_evidence: list[SemanticEvidenceExtraction] | None = None) -> dict[str, Any]:
    transcript_text = _full_transcript_text(source)
    return {
        "id": source.id,
        "platform": source.platform,
        "sourceType": source.sourceType,
        "title": source.title[:220],
        "creator": (source.creator or source.author)[:120],
        "urlPresent": bool(source.url),
        "summary": text_excerpt([source.summary], 260),
        "evidenceScore": source.evidenceScore,
        "evidenceChannels": source.evidenceChannels or source.metrics.get("evidence_channels", []),
        "commentCount": len(source.comments),
        "commentsPreview": text_excerpt([comment.text for comment in source.comments[:2]], 220),
        "hasTranscript": bool(source.transcriptPreview or transcript_text),
        "hasFullTranscript": bool(transcript_text),
        "fullTranscriptChars": len(transcript_text),
        "transcriptPreview": text_excerpt([source.transcriptPreview], 260),
        "semanticEvidence": [_semantic_evidence_payload(item) for item in semantic_evidence or []],
        "metrics": _compact_metrics(source.metrics),
    }


def _source_payload(source: Source, semantic_evidence: list[SemanticEvidenceExtraction] | None = None) -> dict[str, Any]:
    return {
        "id": source.id,
        "platform": source.platform,
        "sourceType": source.sourceType,
        "title": source.title,
        "creator": source.creator or source.author,
        "url": source.url,
        "summary": source.summary,
        "metrics": source.metrics,
        "evidenceScore": source.evidenceScore,
        "comments": [
            {"author": comment.author, "text": comment.text[:280], "likes": comment.likes}
            for comment in source.comments[:4]
            if comment.text
        ],
        "transcriptPreview": text_excerpt([source.transcriptPreview], 900),
        "transcriptChunks": _transcript_chunks(source),
        "semanticEvidence": [_semantic_evidence_payload(item) for item in semantic_evidence or []],
    }


def _source_evidence_pack(source: Source) -> dict[str, Any]:
    return {
        "id": source.id,
        "platform": source.platform,
        "sourceType": source.sourceType,
        "title": source.title[:240],
        "creator": (source.creator or source.author)[:120],
        "summary": text_excerpt([source.summary], 360),
        "comments": [
            {"author": comment.author, "text": comment.text[:320], "likes": comment.likes}
            for comment in source.comments[:8]
            if comment.text
        ],
        "transcriptChunks": _transcript_chunks(source),
        "metrics": _compact_metrics(source.metrics),
    }


def _transcript_chunks(source: Source) -> list[dict[str, Any]]:
    text = _full_transcript_text(source)
    if not text:
        return []
    chunk_size = max(1, int(os.getenv("VOXLENS_LLM_TRANSCRIPT_CHUNK_CHARS", "1600")))
    max_chars = max(chunk_size, int(os.getenv("VOXLENS_LLM_MAX_TRANSCRIPT_CHARS_PER_SOURCE", "12000")))
    limited = text[:max_chars]
    chunks = []
    for idx in range(0, len(limited), chunk_size):
        chunks.append({"index": len(chunks), "text": limited[idx : idx + chunk_size]})
    return chunks[: max(1, int(os.getenv("VOXLENS_LLM_MAX_TRANSCRIPT_CHUNKS_PER_SOURCE", "8")))]


def _full_transcript_text(source: Source) -> str:
    value = getattr(source, "transcriptText", "") or source.transcriptPreview
    return text_excerpt([value], int(os.getenv("VOXLENS_LLM_MAX_TRANSCRIPT_CHARS_PER_SOURCE", "12000")))


def _semantic_evidence_by_source(items: list[SemanticEvidenceExtraction]) -> dict[int, list[SemanticEvidenceExtraction]]:
    grouped: dict[int, list[SemanticEvidenceExtraction]] = {}
    for item in items:
        grouped.setdefault(item.sourceId, []).append(item)
    return grouped


def _semantic_evidence_payload(item: SemanticEvidenceExtraction) -> dict[str, Any]:
    return {
        "candidate": item.candidate,
        "dimension": item.dimension,
        "conclusion": item.conclusion,
        "scenario": item.scenario,
        "value": item.value,
        "quote": item.quote,
        "sourceId": item.sourceId,
        "confidence": item.confidence,
    }


def _decision_dimensions_for_prompt(zh: bool) -> list[dict[str, str]]:
    if zh:
        return [
            {"key": "budget", "label": "预算/价格"},
            {"key": "battery", "label": "续航"},
            {"key": "camera", "label": "拍照"},
            {"key": "performance", "label": "性能"},
            {"key": "thermal", "label": "散热"},
        ]
    return [
        {"key": "budget", "label": "Budget/price"},
        {"key": "battery", "label": "Battery"},
        {"key": "camera", "label": "Camera"},
        {"key": "performance", "label": "Performance"},
        {"key": "thermal", "label": "Thermals"},
    ]


def _looks_like_phone_query(text: str) -> bool:
    lowered = (text or "").lower()
    phone_tokens = ["手机", "iphone", "phone", "redmi", "xiaomi", "oneplus", "oppo", "vivo", "荣耀", "honor", "pixel", "samsung", "galaxy"]
    return any(token in lowered for token in phone_tokens)


def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in metrics.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (str, int, float, bool)):
            compact[key] = str(value)[:120] if isinstance(value, str) else value
        if len(compact) >= 6:
            break
    return compact
