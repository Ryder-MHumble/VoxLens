from __future__ import annotations

from typing import Any


DEFAULT_PLATFORM_IDS = (
    "bilibili",
    "douyin",
    "youtube",
    "xiaohongshu",
    "zhihu",
    "kuaishou",
    "weibo",
)

PLATFORM_META: dict[str, dict[str, str]] = {
    "bilibili": {
        "name": "Bilibili",
        "logo": "https://www.bilibili.com/favicon.ico",
        "role": "Long-form testing, creator methodology, detailed comments.",
    },
    "douyin": {
        "name": "Douyin",
        "logo": "https://www.douyin.com/favicon.ico",
        "role": "Short-form sentiment, fresh reactions, high-volume comment signals.",
    },
    "youtube": {
        "name": "YouTube",
        "logo": "https://www.youtube.com/favicon.ico",
        "role": "Global reviews, comparison videos, long-term experience.",
    },
    "xiaohongshu": {
        "name": "Xiaohongshu",
        "logo": "https://www.xiaohongshu.com/favicon.ico",
        "role": "Lifestyle notes, product experience, image/video posts and comment sentiment.",
    },
    "zhihu": {
        "name": "Zhihu",
        "logo": "https://static.zhihu.com/heifetz/favicon.ico",
        "role": "Long-form answers, zvideo, expert discussions and threaded comments.",
    },
    "kuaishou": {
        "name": "Kuaishou",
        "logo": "https://www.kuaishou.com/favicon.ico",
        "role": "Short-video product experience, regional sentiment and creator feedback.",
    },
    "weibo": {
        "name": "Weibo",
        "logo": "https://weibo.com/favicon.ico",
        "role": "Public conversation, trend diffusion, brand incidents and comment signals.",
    },
}

CRAWLER_PLATFORM_CONFIG: dict[str, dict[str, str]] = {
    "douyin": {"arg": "dy", "folder": "douyin"},
    "bilibili": {"arg": "bili", "folder": "bili"},
    "xiaohongshu": {"arg": "xhs", "folder": "xhs"},
    "zhihu": {"arg": "zhihu", "folder": "zhihu"},
    "kuaishou": {"arg": "ks", "folder": "kuaishou"},
    "weibo": {"arg": "wb", "folder": "weibo"},
}

CRAWLER_PLATFORM_IDS = frozenset(CRAWLER_PLATFORM_CONFIG)
PLATFORM_ORDER = list(DEFAULT_PLATFORM_IDS)

COOKIE_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "bilibili": ("VOXLENS_BILIBILI_COOKIE", "BILIBILI_COOKIE"),
    "douyin": ("VOXLENS_DOUYIN_COOKIE", "DOUYIN_COOKIE", "DY_COOKIE"),
    "xiaohongshu": (
        "VOXLENS_XHS_COOKIE",
        "VOXLENS_XIAOHONGSHU_COOKIE",
        "XHS_COOKIE",
        "XIAOHONGSHU_COOKIE",
        "REDNOTE_COOKIE",
    ),
    "zhihu": ("VOXLENS_ZHIHU_COOKIE", "ZHIHU_COOKIE"),
    "kuaishou": ("VOXLENS_KUAISHOU_COOKIE", "KUAISHOU_COOKIE", "KS_COOKIE"),
    "weibo": ("VOXLENS_WEIBO_COOKIE", "WEIBO_COOKIE", "WB_COOKIE"),
}

PLATFORM_CAPABILITIES: dict[str, dict[str, list[str]]] = {
    "bilibili": {
        "search": ["crawler", "opencli fallback"],
        "comments": ["opencli", "crawler"],
        "transcripts": ["opencli subtitle"],
    },
    "douyin": {
        "search": ["crawler"],
        "comments": ["crawler"],
        "transcripts": [],
    },
    "youtube": {
        "search": ["opencli", "yt-dlp fallback"],
        "comments": ["opencli"],
        "transcripts": ["opencli transcript", "yt-dlp subtitles fallback planned"],
    },
    "xiaohongshu": {
        "search": ["crawler"],
        "comments": ["crawler"],
        "media": ["note images", "note video url"],
    },
    "zhihu": {
        "search": ["crawler"],
        "comments": ["crawler"],
        "content": ["answer", "article", "zvideo metadata"],
    },
    "kuaishou": {
        "search": ["crawler"],
        "comments": ["crawler"],
        "media": ["short video metadata"],
    },
    "weibo": {
        "search": ["crawler"],
        "comments": ["crawler"],
        "content": ["post text", "media metadata"],
    },
}


def platform_meta_for_report() -> dict[str, dict[str, str]]:
    return {
        platform: {"name": meta["name"], "logo": meta["logo"]}
        for platform, meta in PLATFORM_META.items()
    }


def platform_brand_payload() -> dict[str, dict[str, str]]:
    return {
        platform: {"name": meta["name"], "logo": meta["logo"], "role": meta["role"]}
        for platform, meta in PLATFORM_META.items()
    }


def capability_platforms() -> dict[str, dict[str, list[str]]]:
    return {
        platform: {name: list(values) for name, values in capability.items()}
        for platform, capability in PLATFORM_CAPABILITIES.items()
    }


def public_platform_catalog() -> dict[str, Any]:
    return {
        platform: {
            "name": meta["name"],
            "logo": meta["logo"],
            "role": meta["role"],
            "defaultEnabled": platform in DEFAULT_PLATFORM_IDS,
            "localCrawler": platform in CRAWLER_PLATFORM_IDS,
            "cookieEnvVars": list(COOKIE_ENV_ALIASES.get(platform, ())),
        }
        for platform, meta in PLATFORM_META.items()
    }
