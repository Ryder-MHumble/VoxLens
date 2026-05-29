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


@dataclass
class DecisionAttributeExtractionResult:
    products: dict[str, dict[str, list[dict[str, Any]]]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    model: str = ""


@dataclass
class DecisionContradictionResult:
    contradictions: dict[str, dict[str, Any]] = field(default_factory=dict)
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
    decision_attributes: DecisionAttributeExtractionResult | None = None
    decision_contradictions: DecisionContradictionResult | None = None
    if report_kind == "decision":
        decision_attributes = extract_decision_attributes_with_llm(
            need=need,
            query=query,
            lang=lang,
            sources=sources,
        )
        if decision_attributes:
            decision_contradictions = analyze_decision_contradictions_with_llm(
                need=need,
                query=query,
                lang=lang,
                attributes=decision_attributes.products,
            )
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
            {"role": "system", "content": _system_prompt(lang, report_kind)},
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
                    decision_attributes=decision_attributes.products if decision_attributes else {},
                    contradiction_analysis=decision_contradictions.contradictions if decision_contradictions else {},
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
    if decision_attributes and decision_attributes.warnings:
        result.warnings = [*decision_attributes.warnings, *result.warnings][:6]
    if decision_contradictions and decision_contradictions.warnings:
        result.warnings = [*decision_contradictions.warnings, *result.warnings][:6]
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


def extract_decision_attributes_with_llm(
    *,
    need: str,
    query: str,
    lang: str,
    sources: list[Source],
) -> DecisionAttributeExtractionResult | None:
    if not _enabled() or not sources:
        return None
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENROUTER_MODEL", "z-ai/glm-5.1")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _decision_attribute_system_prompt(lang)},
            {
                "role": "user",
                "content": _decision_attribute_prompt(
                    need=need,
                    query=query,
                    lang=lang,
                    sources=sources,
                ),
            },
        ],
        "temperature": float(os.getenv("OPENROUTER_EXTRACTION_TEMPERATURE", "0.1")),
        "max_tokens": int(os.getenv("OPENROUTER_DECISION_ATTRIBUTE_MAX_TOKENS", "3500")),
        "response_format": {"type": "json_object"},
    }
    content = _post_chat_completion(api_key, payload)
    parsed = _parse_json(content)
    valid_ids = {source.id for source in sources}
    return DecisionAttributeExtractionResult(
        products=_sanitize_decision_products(parsed.get("products", parsed.get("productAttributes", {})), valid_ids),
        warnings=[str(item)[:240] for item in parsed.get("warnings", []) if str(item).strip()][:6],
        model=model,
    )


def analyze_decision_contradictions_with_llm(
    *,
    need: str,
    query: str,
    lang: str,
    attributes: dict[str, dict[str, list[dict[str, Any]]]],
) -> DecisionContradictionResult | None:
    if not _enabled() or not attributes:
        return None
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENROUTER_MODEL", "z-ai/glm-5.1")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _decision_contradiction_system_prompt(lang)},
            {
                "role": "user",
                "content": _decision_contradiction_prompt(
                    need=need,
                    query=query,
                    lang=lang,
                    attributes=attributes,
                ),
            },
        ],
        "temperature": float(os.getenv("OPENROUTER_CONTRADICTION_TEMPERATURE", "0.1")),
        "max_tokens": int(os.getenv("OPENROUTER_CONTRADICTION_MAX_TOKENS", "2200")),
        "response_format": {"type": "json_object"},
    }
    content = _post_chat_completion(api_key, payload)
    parsed = _parse_json(content)
    return DecisionContradictionResult(
        contradictions=_sanitize_contradictions(parsed.get("contradictions", parsed.get("contradictionAnalysis", {}))),
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


def _sanitize_decision_products(items: Any, valid_ids: set[int]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    if not isinstance(items, dict):
        return {}
    products: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for product_name, dimensions in items.items():
        name = str(product_name).strip()[:120]
        if not name or not isinstance(dimensions, dict):
            continue
        clean_dimensions: dict[str, list[dict[str, Any]]] = {}
        for dimension_name, values in dimensions.items():
            dimension = str(dimension_name).strip()[:80]
            if not dimension:
                continue
            value_items = values if isinstance(values, list) else [values]
            clean_values: list[dict[str, Any]] = []
            for value in value_items:
                if not isinstance(value, dict):
                    continue
                source_ids = _valid_ids(value.get("sourceIds", value.get("sources", value.get("sourceId", []))), valid_ids)
                if not source_ids:
                    continue
                conclusion = str(value.get("conclusion", value.get("summary", ""))).strip()
                if not conclusion:
                    continue
                clean_values.append({
                    "conclusion": conclusion[:360],
                    "condition": str(value.get("condition", value.get("testCondition", value.get("scenario", ""))) or "")[:180],
                    "sourceIds": source_ids,
                    "value": str(value.get("value", value.get("metric", "")) or "")[:140],
                })
            if clean_values:
                clean_dimensions[dimension] = clean_values[:8]
        if clean_dimensions:
            products[name] = clean_dimensions
    return products


def _sanitize_contradictions(items: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(items, dict):
        return {}
    contradictions: dict[str, dict[str, Any]] = {}
    for dimension_name, value in items.items():
        if not isinstance(value, dict):
            continue
        dimension = str(dimension_name).strip()[:80]
        if not dimension:
            continue
        contradictions[dimension] = {
            "isContradictory": bool(value.get("isContradictory", value.get("contradictory", False))),
            "contradictionDescription": str(value.get("contradictionDescription", value.get("description", "")) or "")[:360],
            "possibleReason": str(value.get("possibleReason", value.get("reason", "")) or "")[:360],
        }
    return contradictions


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


def _decision_attribute_system_prompt(lang: str) -> str:
    if lang == "zh":
        return (
            "你是消费电子测评的结构化证据抽取员。你的任务是从多个视频/内容来源中抽取每个产品的属性、"
            "实测数值、场景评价和对比结论。维度必须来自来源内容，不要套用固定模板。只输出 JSON。"
        )
    return (
        "You extract structured evidence from consumer-electronics reviews. Extract each product's attributes, "
        "measured values, scenario evaluations and comparison conclusions. Dimensions must come from the sources, not a fixed template. Return JSON only."
    )


def _decision_contradiction_system_prompt(lang: str) -> str:
    if lang == "zh":
        return (
            "你是消费决策的交叉验证分析师。你会比较同一维度下的多个来源结论，明确哪些结论矛盾，"
            "并解释可能原因，例如测试条件、使用场景或评价标准不同。只输出 JSON。"
        )
    return (
        "You are a cross-validation analyst for purchase decisions. Compare conclusions under the same dimension, "
        "flag contradictions and explain likely causes such as test conditions, usage scenarios or standards. Return JSON only."
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
    task = (
        "从每个来源中提取候选产品、维度、结论、测试/使用场景、实测值或描述、短引用片段和置信度。"
        "维度名称必须来自标题、评论、字幕/正文中的真实表述；如果证据不足就不要补编。"
        if zh
        else "Extract candidate product, dimension, conclusion, test/use scenario, measured value or description, short quote and confidence from each source. Dimension names must come from real wording in titles, comments or transcripts/content; do not invent missing evidence."
    )
    return json.dumps(
        {
            "task": task,
            "need": need,
            "query": query,
            "reportKind": report_kind,
            "outputSchema": {
                "evidence": [
                    {
                        "candidate": "string",
                        "dimension": "source-derived attribute name",
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


def _decision_attribute_prompt(
    *,
    need: str,
    query: str,
    lang: str,
    sources: list[Source],
) -> str:
    zh = lang == "zh"
    task = (
        "先从所有来源中抽取结构化消费决策证据，输出 {产品: {维度: [{结论, 测试条件, 来源IDs}]}}。"
        "每个维度必须来自来源标题、评论或字幕/正文；实测数字优先；没有证据不要编造。"
        if zh
        else "Extract structured purchase-decision evidence from all sources as {product: {dimension: [{conclusion, condition, sourceIds}]}}. "
        "Each dimension must come from titles, comments or transcripts/content; measured numbers outrank subjective comments; do not invent evidence."
    )
    return json.dumps(
        {
            "task": task,
            "need": need,
            "query": query,
            "outputSchema": {
                "products": {
                    "Product name": {
                        "source-derived dimension": [
                            {
                                "conclusion": "source-grounded conclusion",
                                "condition": "test or use condition",
                                "value": "measured value if present",
                                "sourceIds": [1],
                            }
                        ]
                    }
                },
                "warnings": ["string"],
            },
            "sourceEvidencePacks": [_source_evidence_pack(source) for source in sources],
        },
        ensure_ascii=False,
    )


def _decision_contradiction_prompt(
    *,
    need: str,
    query: str,
    lang: str,
    attributes: dict[str, dict[str, list[dict[str, Any]]]],
) -> str:
    zh = lang == "zh"
    task = (
        "比较同一维度下不同产品/来源的结论，标注是否矛盾，并解释可能原因。重点说明为什么矛盾，而不是回避矛盾。"
        if zh
        else "Compare conclusions under each dimension across products/sources, flag contradictions and explain likely causes. Explain why contradictions happen instead of hiding them."
    )
    return json.dumps(
        {
            "task": task,
            "need": need,
            "query": query,
            "decisionAttributeMatrix": attributes,
            "outputSchema": {
                "contradictions": {
                    "dimension": {
                        "isContradictory": True,
                        "contradictionDescription": "what conflicts",
                        "possibleReason": "test condition, scenario, standard or source difference",
                    }
                },
                "warnings": ["string"],
            },
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


def _system_prompt(lang: str, report_kind: str = "general") -> str:
    if report_kind == "decision":
        if lang == "zh":
            return (
                "你是消费决策分析师。你收到的来源是多个视频博主对消费电子产品的测评。\n"
                "你的任务：\n"
                "1. 提取每个被测产品的结构化属性（实测数值、场景评价、对比结论等）。\n"
                "2. 当多个来源对同一属性结论矛盾时，分析可能原因（测试条件、使用场景、标准不同）。\n"
                "3. 输出对比矩阵和购买建议。\n"
                "规则：\n"
                "1. 每个属性值必须标注来源ID。\n"
                "2. 实测数据（数字）优先于主观评价。\n"
                "3. 发现矛盾时不要回避，明确说明“为什么矛盾”比“有没有矛盾”更重要。\n"
                "4. 不要编造来源中没有的数据。\n"
                "5. 不同品类的评价维度不同，从来源内容中提取，不要套用固定维度模板。"
            )
        return (
            "You are a consumer purchase-decision analyst. Sources are video creators reviewing consumer electronics.\n"
            "Tasks:\n"
            "1. Extract structured attributes for each reviewed product: measured values, scenario evaluations and comparison conclusions.\n"
            "2. When sources conflict on the same attribute, explain likely causes such as test conditions, usage scenarios or standards.\n"
            "3. Produce a comparison matrix and purchase recommendation.\n"
            "Rules:\n"
            "1. Every attribute value must cite source IDs.\n"
            "2. Measured numeric data outranks subjective evaluation.\n"
            "3. Do not hide contradictions; explaining why they conflict matters more than only saying whether they conflict.\n"
            "4. Do not invent data absent from sources.\n"
            "5. Dimensions differ by product category; extract them from source content instead of using a fixed template."
        )
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
    decision_attributes: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
    contradiction_analysis: dict[str, dict[str, Any]] | None = None,
) -> str:
    zh = lang == "zh"
    selected_source_ids = selected_source_ids or [source.id for source in sources]
    semantic_evidence = semantic_evidence or []
    decision_attributes = decision_attributes or {}
    contradiction_analysis = contradiction_analysis or {}
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
    if report_kind == "decision":
        instructions = (
            "请输出中文 JSON，不要 markdown。购买决策报告必须使用四段结构：我的需求、候选筛选、维度对比矩阵、最终推荐。维度来自来源内容，不要套用固定品类模板；最终推荐必须包含明确“买X”、条件建议和不推荐情况。"
            if zh
            else "Return English JSON, no markdown. Purchase-decision reports must use four sections: My Needs, Candidate Filtering, Dimension Comparison Matrix, Final Recommendation. Dimensions come from source content, not fixed category templates; the final recommendation must clearly say 'buy X', include conditional advice and not-recommended cases."
        )
        schema["sections"] = [
            {"id": "needs", "title": "1. 我的需求" if zh else "1. My Needs", "kind": "decision_needs", "body": "string", "bullets": [{"text": "string", "citations": [1]}], "sourceIds": [1]},
            {"id": "candidates", "title": "2. 候选筛选" if zh else "2. Candidate Filtering", "kind": "candidate_map", "body": "string", "bullets": [{"text": "string", "citations": [1]}], "sourceIds": [1], "data": {"candidates": [{"name": "string", "matchReason": "string", "sourceIds": [1]}]}},
            {"id": "dimension-comparison", "title": "3. 维度对比矩阵" if zh else "3. Dimension Comparison Matrix", "kind": "decision_matrix", "body": "string", "sourceIds": [1], "data": {"comparisons": [{"dimension": "source-derived name", "values": [{"candidate": "string", "conclusion": "string", "condition": "string", "confidence": "green|yellow|gray", "sourceIds": [1]}], "isContradictory": False, "contradictionReason": "string"}]}},
            {"id": "final-recommendation", "title": "4. 最终推荐" if zh else "4. Final Recommendation", "kind": "final_recommendation", "body": "string", "bullets": [{"text": "string", "citations": [1]}], "sourceIds": [1]},
        ]
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
                "Do not cite a source unless the claim is supported by its title, summary, comments, transcriptPreview, or fullTranscript.",
                "When fullTranscript is present, use it as the richer synthesis context; transcriptPreview is only a UI preview.",
                "Use semanticEvidence first when it is present; it was extracted from fuller transcript/content chunks before synthesis.",
                "Put the source ids that support each section body in section.sourceIds, even when bullets also carry citations.",
            ],
            "outputSchema": schema,
            "semanticEvidence": [_semantic_evidence_payload(item) for item in semantic_evidence if item.sourceId in selected_source_ids],
            "decisionAttributeMatrix": decision_attributes,
            "contradictionAnalysis": contradiction_analysis,
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
    full_transcript = _full_transcript_text(source, limit=int(os.getenv("VOXLENS_LLM_SYNTHESIS_TRANSCRIPT_CHARS", "4000")))
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
        "fullTranscript": full_transcript,
        "transcriptChunks": _transcript_chunks(source),
        "semanticEvidence": [_semantic_evidence_payload(item) for item in semantic_evidence or []],
    }


def _source_evidence_pack(source: Source) -> dict[str, Any]:
    full_transcript = _full_transcript_text(source, limit=int(os.getenv("VOXLENS_LLM_SYNTHESIS_TRANSCRIPT_CHARS", "4000")))
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
        "fullTranscript": full_transcript,
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


def _full_transcript_text(source: Source, limit: int | None = None) -> str:
    value = max(
        [getattr(source, "fullTranscript", ""), getattr(source, "transcriptText", ""), source.transcriptPreview],
        key=len,
    )
    max_chars = limit if limit is not None else int(os.getenv("VOXLENS_LLM_MAX_TRANSCRIPT_CHARS_PER_SOURCE", "12000"))
    return text_excerpt([value], max_chars)


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
