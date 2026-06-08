from __future__ import annotations

BUSINESS_REPORT_TEMPLATE = (
    ("executive-summary", "business_summary", "1. 研究结论摘要", "1. Research Brief"),
    ("category-scope", "category_scope", "2. 品类/产品范围", "2. Category & Product Scope"),
    ("competitive-landscape", "competitive_landscape", "3. 竞品与内容格局", "3. Competitive Landscape"),
    ("user-voice-signals", "user_voice_signals", "4. 用户声音与需求信号", "4. User Voice & Demand Signals"),
    ("opportunity-risks", "opportunity_risks", "5. 机会、风险与分歧", "5. Opportunities, Risks & Disagreements"),
    ("research-gaps", "research_gaps", "6. 证据缺口与下一步研究", "6. Evidence Gaps & Next Research"),
)


def business_template_payload(zh: bool) -> list[dict[str, str]]:
    return [
        {"id": section_id, "kind": kind, "title": title_zh if zh else title_en}
        for section_id, kind, title_zh, title_en in BUSINESS_REPORT_TEMPLATE
    ]
