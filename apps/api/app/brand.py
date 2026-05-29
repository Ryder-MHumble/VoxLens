from __future__ import annotations

from typing import Any

from app.platform_catalog import platform_brand_payload


PRODUCT_NAME = "VoxLens"


BRAND: dict[str, Any] = {
    "productName": PRODUCT_NAME,
    "slogans": {
        "zh": "研究，不止文字",
        "en": "Research beyond text",
    },
    "positioning": {
        "zh": "面向视频社媒的多模态 DeepResearch Agent",
        "en": "A multimodal DeepResearch agent for social video evidence.",
    },
    "oneLiner": {
        "zh": "让 AI 看完视频、评论和字幕，把创作者观点压缩成可验证的研究报告。",
        "en": "Let AI watch videos, comments and transcripts, then turn creator signals into a verifiable research report.",
    },
    "personality": ["calm", "evidence-first", "multimodal", "source-aware"],
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
        "logoConcept": "A folded V-shaped prism lens around a play pupil, with voice bars and one citation node: watch, listen, cite.",
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
