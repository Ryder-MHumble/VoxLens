from __future__ import annotations

import os
import shutil
from typing import Any

from app.providers.registry import provider_capabilities
from app.utils import CRAWLER_ROOT


def command_capability(command: str) -> dict[str, Any]:
    path = shutil.which(command)
    return {
        "available": bool(path),
        "path": path or "",
    }


def capabilities_payload() -> dict[str, Any]:
    ffmpeg = command_capability("ffmpeg")
    return {
        "product": "VoxLens",
        "runtime": {
            "opencli": command_capability("opencli"),
            "uv": command_capability("uv"),
            "python": command_capability("python"),
            "ffmpeg": ffmpeg,
            "ytDlp": command_capability("yt-dlp"),
        },
        "crawlerRuntime": {
            "available": (CRAWLER_ROOT / "main.py").exists(),
            "path": str(CRAWLER_ROOT),
            "licenseNote": "VoxLens ships this crawler runtime as an integrated package; keep the upstream MediaCrawler license and third-party notice in production reviews.",
        },
        "providers": provider_capabilities(),
        "llm": {
            "provider": "openrouter",
            "configured": bool(os.getenv("OPENROUTER_API_KEY")),
            "model": os.getenv("OPENROUTER_MODEL", "z-ai/glm-5.1"),
            "note": "API keys are read from environment variables and are never returned by report APIs.",
        },
        "auth": {
            "strategy": "auto",
            "opencli": "Reuses the user's logged-in Chrome session through OpenCLI Browser Bridge when configured.",
            "crawler": "Prefers explicit cookie env vars, otherwise uses the crawler runtime's existing-browser/CDP login state or QR fallback.",
            "cookieEnvVars": {
                "bilibili": ["VOXLENS_BILIBILI_COOKIE", "BILIBILI_COOKIE"],
                "douyin": ["VOXLENS_DOUYIN_COOKIE", "DOUYIN_COOKIE", "DY_COOKIE"],
                "xiaohongshu": ["VOXLENS_XHS_COOKIE", "VOXLENS_XIAOHONGSHU_COOKIE", "XHS_COOKIE", "XIAOHONGSHU_COOKIE", "REDNOTE_COOKIE"],
                "zhihu": ["VOXLENS_ZHIHU_COOKIE", "ZHIHU_COOKIE"],
                "kuaishou": ["VOXLENS_KUAISHOU_COOKIE", "KUAISHOU_COOKIE", "KS_COOKIE"],
                "weibo": ["VOXLENS_WEIBO_COOKIE", "WEIBO_COOKIE", "WB_COOKIE"],
            },
            "configured": {
                "bilibili": bool(os.getenv("VOXLENS_BILIBILI_COOKIE") or os.getenv("BILIBILI_COOKIE")),
                "douyin": bool(os.getenv("VOXLENS_DOUYIN_COOKIE") or os.getenv("DOUYIN_COOKIE") or os.getenv("DY_COOKIE")),
                "xiaohongshu": bool(os.getenv("VOXLENS_XHS_COOKIE") or os.getenv("VOXLENS_XIAOHONGSHU_COOKIE") or os.getenv("XHS_COOKIE") or os.getenv("XIAOHONGSHU_COOKIE") or os.getenv("REDNOTE_COOKIE")),
                "zhihu": bool(os.getenv("VOXLENS_ZHIHU_COOKIE") or os.getenv("ZHIHU_COOKIE")),
                "kuaishou": bool(os.getenv("VOXLENS_KUAISHOU_COOKIE") or os.getenv("KUAISHOU_COOKIE") or os.getenv("KS_COOKIE")),
                "weibo": bool(os.getenv("VOXLENS_WEIBO_COOKIE") or os.getenv("WEIBO_COOKIE") or os.getenv("WB_COOKIE")),
            },
            "privacy": "Cookies are only passed to local crawler subprocesses and are never returned by API responses.",
        },
        "platforms": {
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
        },
        "warnings": [] if ffmpeg["available"] else ["ffmpeg is not installed or not on PATH; video frame/audio extraction is disabled until installed."],
    }
