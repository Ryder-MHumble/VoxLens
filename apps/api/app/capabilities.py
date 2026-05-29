from __future__ import annotations

import os
import shutil
from typing import Any

from app.platform_catalog import COOKIE_ENV_ALIASES, capability_platforms, public_platform_catalog
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
            "licenseNote": "VoxLens ships this crawler runtime as an integrated package; keep package license and third-party notices in production reviews.",
            "riskNote": "Crawler-style access can trigger rate limits, verification, IP blocking, account restrictions or account bans when misused.",
        },
        "providers": provider_capabilities(),
        "youtube": {
            "metadataApiConfigured": bool(os.getenv("YOUTUBE_API_KEY") or os.getenv("VOXLENS_YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")),
            "note": "YouTube Data API keys are read from environment variables and are never returned by report APIs.",
        },
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
            "cookieEnvVars": {platform: list(aliases) for platform, aliases in COOKIE_ENV_ALIASES.items()},
            "configured": {
                platform: any(os.getenv(name) for name in aliases)
                for platform, aliases in COOKIE_ENV_ALIASES.items()
            },
            "privacy": "Cookies are only passed to local crawler subprocesses and are never returned by API responses.",
        },
        "platformCatalog": public_platform_catalog(),
        "platforms": capability_platforms(),
        "warnings": [] if ffmpeg["available"] else ["ffmpeg is not installed or not on PATH; video frame/audio extraction is disabled until installed."],
    }
