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
                    sources=sources,
                    coverage=coverage,
                    report_kind=report_kind,
                ),
            },
        ],
        "temperature": float(os.getenv("OPENROUTER_TEMPERATURE", "0.25")),
        "max_tokens": int(os.getenv("OPENROUTER_MAX_TOKENS", "5000")),
        "response_format": {"type": "json_object"},
    }
    content = _post_chat_completion(api_key, payload)
    parsed = _parse_json(content)
    result = _result_from_payload(parsed, valid_ids={source.id for source in sources})
    result.model = model
    return result


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
            "table": item.get("table", []) if isinstance(item.get("table"), list) else [],
            "sourceIds": _valid_ids(item.get("sourceIds", item.get("citations", [])), valid_ids),
            "metrics": item.get("metrics", {}) if isinstance(item.get("metrics"), dict) else {},
            "data": item.get("data", {}) if isinstance(item.get("data"), dict) else {},
        }
        sanitized.append(section)
    return sanitized


def _valid_ids(values: Any, valid_ids: set[int]) -> list[int]:
    if isinstance(values, (str, int)):
        values = [values]
    if not isinstance(values, list):
        return []
    ids: list[int] = []
    for value in values:
        try:
            source_id = int(value)
        except (TypeError, ValueError):
            continue
        if source_id in valid_ids and source_id not in ids:
            ids.append(source_id)
    return ids[:6]


def _safe_id(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug[:48] or "section"


def _int_range(value: Any, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = low
    return max(low, min(high, parsed))


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
) -> str:
    zh = lang == "zh"
    source_pack = [_source_payload(source) for source in sources[:14]]
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
            "sourceRules": [
                "Use only source ids present in sources.",
                "Every takeaway and section bullet should have at least one citation when possible.",
                "Mention uncertainty when evidence is thin, single-platform, or mostly title-only.",
                "Do not cite a source unless the claim is supported by its title, summary, comments, or transcriptPreview.",
            ],
            "outputSchema": schema,
            "sources": source_pack,
        },
        ensure_ascii=False,
    )


def _source_payload(source: Source) -> dict[str, Any]:
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
    }
