from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from app.providers.registry import provider_capabilities
from app.utils import MEDIACRAWLER_DIR


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
        "mediaCrawler": {
            "available": (MEDIACRAWLER_DIR / "main.py").exists(),
            "path": str(MEDIACRAWLER_DIR),
            "licenseNote": "MediaCrawler is integrated as an external research crawler; review its non-commercial learning license before production use.",
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
            "mediacrawler": "Prefers explicit cookie env vars, otherwise uses MediaCrawler's existing-browser/CDP login state or QR fallback.",
            "cookieEnvVars": {
                "bilibili": ["VOXLENS_BILIBILI_COOKIE", "BILIBILI_COOKIE", "SCANCAST_BILIBILI_COOKIE"],
                "douyin": ["VOXLENS_DOUYIN_COOKIE", "DOUYIN_COOKIE", "DY_COOKIE", "SCANCAST_DOUYIN_COOKIE"],
                "xiaohongshu": ["VOXLENS_XHS_COOKIE", "VOXLENS_XIAOHONGSHU_COOKIE", "XHS_COOKIE", "XIAOHONGSHU_COOKIE", "REDNOTE_COOKIE"],
                "zhihu": ["VOXLENS_ZHIHU_COOKIE", "ZHIHU_COOKIE"],
                "kuaishou": ["VOXLENS_KUAISHOU_COOKIE", "KUAISHOU_COOKIE", "KS_COOKIE"],
                "weibo": ["VOXLENS_WEIBO_COOKIE", "WEIBO_COOKIE", "WB_COOKIE"],
            },
            "configured": {
                "bilibili": bool(os.getenv("VOXLENS_BILIBILI_COOKIE") or os.getenv("BILIBILI_COOKIE") or os.getenv("SCANCAST_BILIBILI_COOKIE")),
                "douyin": bool(os.getenv("VOXLENS_DOUYIN_COOKIE") or os.getenv("DOUYIN_COOKIE") or os.getenv("DY_COOKIE") or os.getenv("SCANCAST_DOUYIN_COOKIE")),
                "xiaohongshu": bool(os.getenv("VOXLENS_XHS_COOKIE") or os.getenv("VOXLENS_XIAOHONGSHU_COOKIE") or os.getenv("XHS_COOKIE") or os.getenv("XIAOHONGSHU_COOKIE") or os.getenv("REDNOTE_COOKIE")),
                "zhihu": bool(os.getenv("VOXLENS_ZHIHU_COOKIE") or os.getenv("ZHIHU_COOKIE")),
                "kuaishou": bool(os.getenv("VOXLENS_KUAISHOU_COOKIE") or os.getenv("KUAISHOU_COOKIE") or os.getenv("KS_COOKIE")),
                "weibo": bool(os.getenv("VOXLENS_WEIBO_COOKIE") or os.getenv("WEIBO_COOKIE") or os.getenv("WB_COOKIE")),
            },
            "privacy": "Cookies are only passed to local crawler subprocesses and are never returned by API responses.",
        },
        "platforms": {
            "bilibili": {
                "search": ["mediacrawler", "opencli fallback"],
                "comments": ["opencli", "mediacrawler"],
                "transcripts": ["opencli subtitle"],
            },
            "douyin": {
                "search": ["mediacrawler"],
                "comments": ["mediacrawler"],
                "transcripts": [],
            },
            "youtube": {
                "search": ["opencli", "yt-dlp fallback"],
                "comments": ["opencli"],
                "transcripts": ["opencli transcript", "yt-dlp subtitles fallback planned"],
            },
            "xiaohongshu": {
                "search": ["mediacrawler"],
                "comments": ["mediacrawler"],
                "media": ["note images", "note video url"],
            },
            "zhihu": {
                "search": ["mediacrawler"],
                "comments": ["mediacrawler"],
                "content": ["answer", "article", "zvideo metadata"],
            },
            "kuaishou": {
                "search": ["mediacrawler"],
                "comments": ["mediacrawler"],
                "media": ["short video metadata"],
            },
            "weibo": {
                "search": ["mediacrawler"],
                "comments": ["mediacrawler"],
                "content": ["post text", "media metadata"],
            },
        },
        "warnings": [] if ffmpeg["available"] else ["ffmpeg is not installed or not on PATH; video frame/audio extraction is disabled until installed."],
    }
