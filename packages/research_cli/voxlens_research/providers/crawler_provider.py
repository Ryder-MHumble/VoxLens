"""VoxLens crawler runtime subprocess provider."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from voxlens_research.models import ProviderRun, SearchItem
from voxlens_research.utils import CRAWLER_ROOT, RUNTIME_ROOT, read_jsonl_files, run_command, slugify


CRAWLER_PLATFORM = {
    "bilibili": "bili",
    "xiaohongshu": "xhs",
    "douyin": "dy",
    "kuaishou": "ks",
    "weibo": "wb",
    "zhihu": "zhihu",
}

OUTPUT_DIR_NAME = {
    "bili": "bili",
    "xhs": "xhs",
    "dy": "douyin",
    "ks": "kuaishou",
    "wb": "weibo",
    "zhihu": "zhihu",
}

COOKIE_ENV_ALIASES = {
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


def supports(platform: str) -> bool:
    return platform in CRAWLER_PLATFORM


def search(
    platform: str,
    query: str,
    limit: int,
    crawler_dir: Path | None = None,
    save_root: Path | None = None,
    timeout: int = 300,
) -> ProviderRun:
    platform_code = CRAWLER_PLATFORM.get(platform)
    if not platform_code:
        return ProviderRun(provider="crawler", platform=platform, query=query, ok=False, note="VoxLens crawler runtime does not support this platform")

    crawler_dir = crawler_dir or CRAWLER_ROOT
    save_root = save_root or RUNTIME_ROOT / "runs" / "crawler" / slugify(query)
    run = ProviderRun(provider="crawler", platform=platform, query=query)
    if not (crawler_dir / "main.py").exists():
        run.note = f"VoxLens crawler runtime not found at {crawler_dir}"
        return run

    before = _content_files(save_root, platform_code)
    cookie = _cookie_for_platform(platform)
    login_type = "cookie" if cookie else "qrcode"
    command = [
        "uv",
        "run",
        "main.py",
        "--platform",
        platform_code,
        "--lt",
        login_type,
        "--type",
        "search",
        "--keywords",
        query,
        "--save_data_option",
        "jsonl",
        "--save_data_path",
        str(save_root),
        "--get_comment",
        "false",
        "--get_sub_comment",
        "false",
        "--max_concurrency_num",
        "1",
        "--headless",
        "false",
    ]
    if cookie:
        command.extend(["--cookies", cookie])
    run.command = _redact_cookie(command)
    try:
        code, stdout, stderr, elapsed = run_command(command, cwd=crawler_dir, timeout=timeout)
        run.elapsed_sec = elapsed
        run.stderr = stderr.strip()
        run.ok = code == 0
        after = _content_files(save_root, platform_code)
        new_or_latest = [p for p in after if p not in before] or after
        rows = read_jsonl_files(sorted(new_or_latest, reverse=True), limit=limit)
        run.items = [_normalize(platform, row) for row in rows[:limit]]
        if not run.ok:
            run.note = (stderr or stdout).strip()[:1000]
        elif not run.items:
            run.note = "crawler finished but no JSONL search contents were found"
        return run
    except Exception as exc:  # noqa: BLE001
        run.ok = False
        run.note = str(exc)
        return run


def _content_files(save_root: Path, platform_code: str) -> set[Path]:
    platform_dir = OUTPUT_DIR_NAME.get(platform_code, platform_code)
    jsonl_dir = save_root / platform_dir / "jsonl"
    if not jsonl_dir.exists():
        return set()
    return set(jsonl_dir.glob("search_contents_*.jsonl"))


def _cookie_for_platform(platform: str) -> str:
    for name in COOKIE_ENV_ALIASES.get(platform, ()):
        value = os.getenv(name)
        if value:
            return value
    return ""


def _redact_cookie(command: list[str]) -> list[str]:
    redacted = list(command)
    for idx, part in enumerate(redacted[:-1]):
        if part == "--cookies":
            redacted[idx + 1] = "<redacted>"
    return redacted


def _normalize(platform: str, row: dict[str, Any]) -> SearchItem:
    if platform == "douyin":
        metrics = {
            "likes": row.get("liked_count"),
            "comments": row.get("comment_count"),
            "shares": row.get("share_count"),
        }
        return SearchItem(
            platform=platform,
            title=str(row.get("title") or row.get("desc") or "Untitled"),
            url=str(row.get("aweme_url") or ""),
            provider="crawler",
            author=str(row.get("nickname") or ""),
            published=str(row.get("create_time") or ""),
            summary_text=str(row.get("desc") or ""),
            metrics=metrics,
            raw=row,
        )

    if platform == "bilibili":
        metrics = {
            "views": row.get("video_play_count"),
            "likes": row.get("liked_count"),
            "comments": row.get("video_comment"),
        }
        return SearchItem(
            platform=platform,
            title=str(row.get("title") or "Untitled"),
            url=str(row.get("video_url") or ""),
            provider="crawler",
            author=str(row.get("nickname") or ""),
            published=str(row.get("create_time") or ""),
            summary_text=str(row.get("desc") or ""),
            metrics=metrics,
            raw=row,
        )

    if platform == "xiaohongshu":
        metrics = {
            "likes": row.get("liked_count"),
            "collects": row.get("collected_count"),
            "comments": row.get("comment_count"),
        }
        return SearchItem(
            platform=platform,
            title=str(row.get("title") or row.get("desc") or "Untitled"),
            url=str(row.get("note_url") or ""),
            provider="crawler",
            author=str(row.get("nickname") or ""),
            published=str(row.get("time") or ""),
            summary_text=str(row.get("desc") or ""),
            metrics=metrics,
            raw=row,
        )

    return SearchItem(
        platform=platform,
        title=str(row.get("title") or row.get("desc") or row.get("content_text") or "Untitled"),
        url=str(row.get("url") or row.get("note_url") or row.get("content_url") or ""),
        provider="crawler",
        author=str(row.get("nickname") or row.get("user_nickname") or ""),
        summary_text=str(row.get("desc") or row.get("content_text") or ""),
        raw=row,
    )
