from __future__ import annotations

import re
from collections import Counter, defaultdict

from app.models import (
    CitationText,
    ComparisonDimension,
    ComparisonRow,
    CoverageSummary,
    DecisionCandidate,
    DimensionComparison,
    DimensionComparisonValue,
    ReportSection,
    Source,
)
from app.services.report_terms import POSITIVE_TERMS, STOPWORDS

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


build_decision_sections = _decision_sections
decision_candidates = _decision_candidates
decision_dimensions = _decision_dimensions
dimension_comparisons = _dimension_comparisons
decision_recommendation = _decision_recommendation
