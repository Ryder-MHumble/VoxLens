from __future__ import annotations

from typing import Any

from app.platform_catalog import platform_brand_payload


PRODUCT_NAME = "VoxLens"


BRAND: dict[str, Any] = {
    "productName": PRODUCT_NAME,
    "slogans": {
        "zh": "视频证据，可信研究",
        "en": "Citable social-video research",
    },
    "positioning": {
        "zh": "面向视频社媒证据的 DeepResearch 工作台",
        "en": "An evidence-first DeepResearch workspace for social-video signals.",
    },
    "oneLiner": {
        "zh": "从标题、评论、字幕/逐字稿和平台元数据中整理可核验证据，生成可引用的研究报告。",
        "en": "Turn titles, comments, transcripts and platform metadata into verifiable, citable research reports.",
    },
    "personality": ["calm", "evidence-first", "source-aware", "scope-honest"],
    "visualSystem": {
        "colors": {
            "inkPlum": "#201A36",
            "paper": "#FBFDFF",
            "auroraSky": "#79D7FF",
            "prismViolet": "#C28DFF",
            "creatorBlush": "#FF9FCF",
            "citationCoral": "#FF667C",
        },
        "gradients": {
            "aurora": "radial-gradient(circle at 18% 82%, #9EE5FF 0%, transparent 46%), radial-gradient(circle at 82% 18%, #FFC3DF 0%, transparent 42%), radial-gradient(circle at 52% 38%, #C4A0FF 0%, transparent 40%), linear-gradient(135deg, #FBFDFF 0%, #F7F4FF 55%, #FFF4F8 100%)",
            "glass": "linear-gradient(145deg, rgba(255,255,255,.82), rgba(255,255,255,.46))",
        },
        "typography": {
            "latin": "Inter / Manrope",
            "cjk": "Noto Sans SC",
            "numeric": "Space Grotesk",
        },
        "logoConcept": "A folded V-shaped evidence lens around a play/source mark, with voice bars and one citation node: search, sample, cite.",
        "assets": {
            "mark": "/brand/voxlens-mark.svg",
            "favicon": "/favicon.svg",
        },
    },
    "platforms": platform_brand_payload(),
}


def brand_payload(lang: str = "zh") -> dict[str, Any]:
    selected = "en" if lang == "en" else "zh"
    return {
        **BRAND,
        "slogan": BRAND["slogans"][selected],
        "positioningText": BRAND["positioning"][selected],
        "oneLinerText": BRAND["oneLiner"][selected],
    }
