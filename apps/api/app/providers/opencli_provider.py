from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.models import Comment, RunLog, Source
from app.utils import bvid_from_url, extract_first_json, first_nonempty, rows_from_payload, run_command, strip_html, text_excerpt


THUMBS = [
    "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1598327105666-5b89351aff97?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1510557880182-3d4d3cba35a5?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1565630916779-e303be97b6f5?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1605236453806-6ff36851218e?auto=format&fit=crop&w=420&q=80",
]


def _command(site: str, command: str, *args: str, fmt: bool = True) -> list[str]:
    cmd = ["opencli", site, command, *args]
    if fmt:
        cmd.extend(["-f", "json"])
    return cmd


def _run_opencli_rows(cmd: list[str], timeout: int = 100) -> tuple[list[dict[str, Any]], int, str, str, float]:
    code, stdout, stderr, elapsed = run_command(cmd, timeout=timeout)
    if code != 0:
        return [], code, stdout, stderr, elapsed
    try:
        payload = extract_first_json(stdout)
    except ValueError:
        return [], code, stdout, stderr or "no JSON payload", elapsed
    return rows_from_payload(payload), code, stdout, stderr, elapsed


def search_youtube(
    query: str,
    limit: int,
    detail_limit: int,
    comments_limit: int,
    include_transcripts: bool = True,
    video_parallelism: int = 3,
) -> tuple[list[Source], RunLog]:
    cmd = _command("youtube", "search", query, "--limit", str(limit), "--type", "video")
    sources: list[Source] = []
    try:
        rows, code, stdout, stderr, elapsed = _run_opencli_rows(cmd, timeout=110)
        for idx, row in enumerate(rows[:limit], start=1):
            source = _youtube_source_from_row(row, idx)
            if source.url or source.title != "Untitled":
                sources.append(source)
        if not sources:
            fallback_sources, fallback_note = _search_youtube_with_ytdlp(query, limit)
            if fallback_sources:
                return fallback_sources, RunLog(provider="yt-dlp", platform="youtube", ok=True, count=len(fallback_sources), elapsedSec=elapsed, note=fallback_note)
        _enrich_many(
            sources[:detail_limit],
            lambda source: _enrich_youtube(source, comments_limit, include_transcripts),
            video_parallelism,
        )
        note = "" if sources else (stderr or stdout or "no results")[:240]
        return sources, RunLog(provider="opencli", platform="youtube", ok=code == 0, count=len(sources), elapsedSec=elapsed, note=note)
    except Exception as exc:  # noqa: BLE001
        fallback_sources, fallback_note = _search_youtube_with_ytdlp(query, limit)
        if fallback_sources:
            return fallback_sources, RunLog(provider="yt-dlp", platform="youtube", ok=True, count=len(fallback_sources), note=fallback_note)
        return [], RunLog(provider="opencli", platform="youtube", ok=False, count=0, note=str(exc)[:240])


def search_bilibili(
    query: str,
    limit: int,
    detail_limit: int,
    comments_limit: int,
    include_transcripts: bool = True,
    video_parallelism: int = 3,
) -> tuple[list[Source], RunLog]:
    cmd = _command("bilibili", "search", query, "--limit", str(limit), "--type", "video")
    sources: list[Source] = []
    try:
        rows, code, stdout, stderr, elapsed = _run_opencli_rows(cmd, timeout=110)
        for idx, row in enumerate(rows[:limit], start=1):
            source = _bilibili_source_from_row(row, idx)
            if source.url or source.title != "Untitled":
                sources.append(source)
        _enrich_many(
            sources[:detail_limit],
            lambda source: _enrich_bilibili(source, comments_limit, include_transcripts),
            video_parallelism,
        )
        note = "" if sources else (stderr or stdout or "no results")[:240]
        return sources, RunLog(provider="opencli", platform="bilibili", ok=code == 0, count=len(sources), elapsedSec=elapsed, note=note)
    except Exception as exc:  # noqa: BLE001
        return [], RunLog(provider="opencli", platform="bilibili", ok=False, count=0, note=str(exc)[:240])


def _youtube_source_from_row(row: dict[str, Any], idx: int) -> Source:
    video_id = first_nonempty(row.get("videoId"), row.get("id"))
    url = first_nonempty(row.get("url"), row.get("href"), row.get("link"))
    if not url and video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
    title = strip_html(first_nonempty(row.get("title"), row.get("name"), default="Untitled"))
    thumbnail = first_nonempty(row.get("thumbnail"), row.get("thumbnailUrl"), row.get("thumb"), default=THUMBS[(idx - 1) % len(THUMBS)])
    return Source(
        id=0,
        platform="youtube",
        title=title,
        creator=first_nonempty(row.get("channel"), row.get("channelName"), row.get("author"), row.get("creator")),
        url=url,
        thumbnail=thumbnail,
        duration=first_nonempty(row.get("duration"), row.get("length")),
        published=first_nonempty(row.get("published"), row.get("publishedTime"), row.get("date")),
        metrics={
            "views": row.get("views") or row.get("viewCount"),
            "source_provider": "opencli",
        },
        summary=title,
    )


def _bilibili_source_from_row(row: dict[str, Any], idx: int) -> Source:
    bvid = first_nonempty(row.get("bvid"), row.get("bvId"), row.get("id"))
    url = first_nonempty(row.get("url"), row.get("href"), row.get("link"))
    if not url and bvid.startswith("BV"):
        url = f"https://www.bilibili.com/video/{bvid}"
    title = strip_html(first_nonempty(row.get("title"), row.get("name"), default="Untitled"))
    thumbnail = first_nonempty(row.get("thumbnail"), row.get("pic"), row.get("cover"), default=THUMBS[idx % len(THUMBS)])
    return Source(
        id=0,
        platform="bilibili",
        title=title,
        creator=first_nonempty(row.get("author"), row.get("up"), row.get("owner"), row.get("creator")),
        url=url,
        thumbnail=thumbnail,
        duration=first_nonempty(row.get("duration"), row.get("length")),
        published=first_nonempty(row.get("published"), row.get("pubdate"), row.get("date")),
        metrics={
            "score": row.get("score"),
            "views": row.get("views") or row.get("play") or row.get("view"),
            "source_provider": "opencli",
        },
        summary=title,
    )


def _enrich_youtube(source: Source, comments_limit: int, include_transcripts: bool) -> None:
    if comments_limit > 0 and source.url:
        try:
            code, stdout, _, _ = run_command(_command("youtube", "comments", source.url, "--limit", str(comments_limit)), timeout=90)
            rows = rows_from_payload(extract_first_json(stdout)) if code == 0 else []
            source.comments = [_comment_from_row(r) for r in rows][:comments_limit]
            if source.comments:
                source.summary = text_excerpt([source.title, *[c.text for c in source.comments[:4]]], 300)
        except Exception:
            pass
    if include_transcripts and source.url:
        try:
            code, stdout, _, _ = run_command(_command("youtube", "transcript", source.url, "--mode", "grouped"), timeout=80)
            rows = rows_from_payload(extract_first_json(stdout)) if code == 0 else []
            chunks = [first_nonempty(row.get("text"), row.get("content")) for row in rows[:6]]
            source.transcriptPreview = text_excerpt(chunks, 420)
        except Exception:
            pass


def _enrich_bilibili(source: Source, comments_limit: int, include_transcripts: bool) -> None:
    bvid = bvid_from_url(source.url)
    if comments_limit > 0 and bvid:
        try:
            code, stdout, _, _ = run_command(_command("bilibili", "comments", bvid, "--limit", str(min(comments_limit, 50))), timeout=90)
            rows = rows_from_payload(extract_first_json(stdout)) if code == 0 else []
            source.comments = [_comment_from_row(r) for r in rows][:comments_limit]
            if source.comments:
                source.summary = text_excerpt([source.title, *[c.text for c in source.comments[:4]]], 300)
        except Exception:
            pass
    if include_transcripts and bvid:
        try:
            code, stdout, _, _ = run_command(_command("bilibili", "subtitle", bvid), timeout=80)
            rows = rows_from_payload(extract_first_json(stdout)) if code == 0 else []
            source.transcriptPreview = text_excerpt([first_nonempty(r.get("content"), r.get("text")) for r in rows[:8]], 420)
        except Exception:
            pass


def _enrich_many(sources: list[Source], enrich: Any, video_parallelism: int) -> None:
    selected = [source for source in sources if source.url]
    if not selected:
        return
    max_workers = max(1, min(video_parallelism, len(selected), 6))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(enrich, source) for source in selected]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass


def _comment_from_row(row: dict[str, Any]) -> Comment:
    return Comment(
        author=first_nonempty(row.get("author"), row.get("user"), row.get("nickname"), row.get("name")),
        text=strip_html(first_nonempty(row.get("text"), row.get("content"), row.get("message"), row.get("comment"))),
        likes=row.get("likes") or row.get("like_count") or row.get("likeCount"),
        time=first_nonempty(row.get("time"), row.get("date"), row.get("published")),
    )


def _search_youtube_with_ytdlp(query: str, limit: int) -> tuple[list[Source], str]:
    cmd = [
        "python",
        "-m",
        "yt_dlp",
        "--dump-single-json",
        "--flat-playlist",
        f"ytsearch{limit}:{query}",
    ]
    try:
        code, stdout, stderr, _ = run_command(cmd, timeout=90)
        if code != 0:
            return [], (stderr or "yt-dlp failed")[:200]
        payload = extract_first_json(stdout)
        entries = rows_from_payload(payload.get("entries", []) if isinstance(payload, dict) else payload)
        sources = []
        for idx, row in enumerate(entries[:limit], start=1):
            video_id = first_nonempty(row.get("id"), row.get("url"))
            title = strip_html(first_nonempty(row.get("title"), default="Untitled"))
            sources.append(Source(
                id=0,
                platform="youtube",
                title=title,
                creator=first_nonempty(row.get("uploader"), row.get("channel")),
                url=f"https://www.youtube.com/watch?v={video_id}" if video_id and not video_id.startswith("http") else video_id,
                thumbnail=first_nonempty(row.get("thumbnail"), default=THUMBS[(idx - 1) % len(THUMBS)]),
                duration=first_nonempty(row.get("duration_string")),
                summary=title,
                metrics={"source_provider": "yt-dlp"},
            ))
        return sources, "opencli returned no usable YouTube results; used yt-dlp metadata fallback"
    except Exception as exc:  # noqa: BLE001
        return [], f"yt-dlp fallback unavailable: {exc}"[:200]
