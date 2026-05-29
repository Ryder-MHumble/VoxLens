from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.models import Comment, RunLog, Source, TranscriptSegment
from app.utils import bvid_from_url, extract_first_json, first_nonempty, rows_from_payload, run_command, strip_html, text_excerpt


THUMBS = [
    "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1598327105666-5b89351aff97?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1510557880182-3d4d3cba35a5?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1565630916779-e303be97b6f5?auto=format&fit=crop&w=420&q=80",
    "https://images.unsplash.com/photo-1605236453806-6ff36851218e?auto=format&fit=crop&w=420&q=80",
]

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


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
    opencli_error = ""
    try:
        rows, code, stdout, stderr, elapsed = _run_opencli_rows(cmd, timeout=110)
        if code != 0:
            opencli_error = (stderr or stdout or f"opencli exited with {code}")[:160]
        for idx, row in enumerate(rows[:limit], start=1):
            source = _youtube_source_from_row(row, idx)
            if source.url or source.title != "Untitled":
                sources.append(source)
        if not sources:
            fallback_sources, fallback_note = _search_youtube_with_api(query, limit)
            if fallback_sources:
                _enrich_many(
                    fallback_sources[:detail_limit],
                    lambda source: _enrich_youtube(source, comments_limit, include_transcripts),
                    video_parallelism,
                )
                note = f"{opencli_error}; {fallback_note}" if opencli_error else fallback_note
                return fallback_sources, RunLog(provider="youtube-api", platform="youtube", ok=True, count=len(fallback_sources), elapsedSec=elapsed, note=note[:240])
            fallback_sources, fallback_note = _search_youtube_with_ytdlp(query, limit)
            if fallback_sources:
                _enrich_many(
                    fallback_sources[:detail_limit],
                    lambda source: _enrich_youtube(source, comments_limit, include_transcripts),
                    video_parallelism,
                )
                return fallback_sources, RunLog(provider="yt-dlp", platform="youtube", ok=True, count=len(fallback_sources), elapsedSec=elapsed, note=fallback_note)
        _enrich_many(
            sources[:detail_limit],
            lambda source: _enrich_youtube(source, comments_limit, include_transcripts),
            video_parallelism,
        )
        note = "" if sources else (stderr or stdout or "no results")[:240]
        return sources, RunLog(provider="opencli", platform="youtube", ok=code == 0, count=len(sources), elapsedSec=elapsed, note=note)
    except Exception as exc:  # noqa: BLE001
        opencli_error = _opencli_error_note(exc)
        fallback_sources, fallback_note = _search_youtube_with_api(query, limit)
        if fallback_sources:
            _enrich_many(
                fallback_sources[:detail_limit],
                lambda source: _enrich_youtube(source, comments_limit, include_transcripts),
                video_parallelism,
            )
            return fallback_sources, RunLog(provider="youtube-api", platform="youtube", ok=True, count=len(fallback_sources), note=f"{opencli_error}; {fallback_note}"[:240])
        fallback_sources, fallback_note = _search_youtube_with_ytdlp(query, limit)
        if fallback_sources:
            _enrich_many(
                fallback_sources[:detail_limit],
                lambda source: _enrich_youtube(source, comments_limit, include_transcripts),
                video_parallelism,
            )
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
        if not source.comments:
            _enrich_youtube_comments_with_api(source, comments_limit)
    if include_transcripts and source.url:
        try:
            code, stdout, _, _ = run_command(_command("youtube", "transcript", source.url, "--mode", "grouped"), timeout=80)
            rows = rows_from_payload(extract_first_json(stdout)) if code == 0 else []
            _apply_transcript_rows(source, rows)
        except Exception:
            pass
        if not source.transcriptText:
            _enrich_youtube_transcript_with_api(source)
        if not source.transcriptText:
            _enrich_youtube_transcript_with_ytdlp(source)


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
            _apply_transcript_rows(source, rows)
        except Exception:
            pass


def _apply_transcript_rows(source: Source, rows: list[dict[str, Any]]) -> None:
    segments = []
    for row in rows:
        text = strip_html(first_nonempty(row.get("text"), row.get("content"), row.get("caption"), row.get("sentence")))
        if not text:
            continue
        segments.append(TranscriptSegment(
            text=text,
            start=row.get("start") or row.get("from") or row.get("begin"),
            end=row.get("end") or row.get("to"),
        ))
    source.transcriptSegments = segments
    full_text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    source.fullTranscript = full_text
    source.transcriptText = full_text
    source.transcriptPreview = text_excerpt([full_text], 420)


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


def _youtube_api_key() -> str:
    return first_nonempty(os.getenv("YOUTUBE_API_KEY"), os.getenv("VOXLENS_YOUTUBE_API_KEY"), os.getenv("GOOGLE_API_KEY"))


def _opencli_error_note(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return "opencli is not installed or not on PATH"
    return f"opencli failed: {str(exc)[:160]}"


def _youtube_api_get(endpoint: str, params: dict[str, str | int]) -> dict[str, Any]:
    key = _youtube_api_key()
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY is not configured")
    query = urllib.parse.urlencode({**params, "key": key})
    url = f"{YOUTUBE_API_BASE}/{endpoint}?{query}"
    request = urllib.request.Request(url, headers={"accept": "application/json"})
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310 - fixed Google API host
        return json.loads(response.read().decode("utf-8"))


def _search_youtube_with_api(query: str, limit: int) -> tuple[list[Source], str]:
    try:
        max_results = max(1, min(limit, 50))
        search_payload = _youtube_api_get("search", {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "safeSearch": "none",
        })
        items = rows_from_payload(search_payload.get("items", []))
        video_ids = [
            first_nonempty((item.get("id") or {}).get("videoId") if isinstance(item.get("id"), dict) else "")
            for item in items
        ]
        video_ids = [video_id for video_id in video_ids if video_id]
        if not video_ids:
            return [], "YouTube Data API returned no video results"

        details_payload = _youtube_api_get("videos", {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids),
            "maxResults": len(video_ids),
        })
        details = {str(item.get("id", "")): item for item in rows_from_payload(details_payload.get("items", []))}
        sources: list[Source] = []
        for idx, video_id in enumerate(video_ids[:limit], start=1):
            detail = details.get(video_id, {})
            snippet = detail.get("snippet") if isinstance(detail.get("snippet"), dict) else {}
            statistics = detail.get("statistics") if isinstance(detail.get("statistics"), dict) else {}
            content = detail.get("contentDetails") if isinstance(detail.get("contentDetails"), dict) else {}
            search_snippet = (items[idx - 1].get("snippet") if idx - 1 < len(items) and isinstance(items[idx - 1].get("snippet"), dict) else {}) or {}
            title = strip_html(first_nonempty(snippet.get("title"), search_snippet.get("title"), default="Untitled"))
            description = strip_html(first_nonempty(snippet.get("description"), search_snippet.get("description")))
            thumbnails = snippet.get("thumbnails") if isinstance(snippet.get("thumbnails"), dict) else {}
            thumbnail = _youtube_thumbnail(thumbnails) or THUMBS[(idx - 1) % len(THUMBS)]
            sources.append(Source(
                id=0,
                platform="youtube",
                title=title,
                creator=first_nonempty(snippet.get("channelTitle"), search_snippet.get("channelTitle")),
                url=f"https://www.youtube.com/watch?v={video_id}",
                thumbnail=thumbnail,
                duration=first_nonempty(content.get("duration")),
                published=first_nonempty(snippet.get("publishedAt"), search_snippet.get("publishedAt")),
                summary=text_excerpt([title, description], 300),
                metrics={
                    "views": statistics.get("viewCount"),
                    "likes": statistics.get("likeCount"),
                    "comments": statistics.get("commentCount"),
                    "source_provider": "youtube-api",
                },
            ))
        return sources, "opencli returned no usable YouTube results; used YouTube Data API metadata fallback"
    except Exception as exc:  # noqa: BLE001
        return [], f"YouTube Data API fallback unavailable: {_safe_youtube_error(exc)}"[:220]


def _youtube_thumbnail(thumbnails: dict[str, Any]) -> str:
    for key in ("maxres", "standard", "high", "medium", "default"):
        value = thumbnails.get(key)
        if isinstance(value, dict):
            url = first_nonempty(value.get("url"))
            if url:
                return url
    return ""


def _enrich_youtube_comments_with_api(source: Source, comments_limit: int) -> None:
    video_id = _youtube_video_id(source.url)
    if not video_id:
        return
    try:
        payload = _youtube_api_get("commentThreads", {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": max(1, min(comments_limit, 100)),
            "textFormat": "plainText",
            "order": "relevance",
        })
        comments: list[Comment] = []
        for item in rows_from_payload(payload.get("items", [])):
            snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            top = snippet.get("topLevelComment") if isinstance(snippet.get("topLevelComment"), dict) else {}
            comment_snippet = top.get("snippet") if isinstance(top.get("snippet"), dict) else {}
            text = strip_html(first_nonempty(comment_snippet.get("textDisplay"), comment_snippet.get("textOriginal")))
            if not text:
                continue
            comments.append(Comment(
                author=first_nonempty(comment_snippet.get("authorDisplayName")),
                text=text,
                likes=comment_snippet.get("likeCount"),
                time=first_nonempty(comment_snippet.get("publishedAt"), comment_snippet.get("updatedAt")),
            ))
        source.comments = comments[:comments_limit]
        if source.comments:
            source.summary = text_excerpt([source.title, *[comment.text for comment in source.comments[:4]]], 300)
    except Exception:
        return


def _enrich_youtube_transcript_with_ytdlp(source: Source) -> None:
    try:
        import yt_dlp

        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(source.url, download=False)
    except Exception:
        return

    captions = info.get("subtitles") if isinstance(info, dict) and isinstance(info.get("subtitles"), dict) else {}
    automatic = info.get("automatic_captions") if isinstance(info, dict) and isinstance(info.get("automatic_captions"), dict) else {}
    track = _pick_caption_track(captions) or _pick_caption_track(automatic)
    if not track:
        return
    try:
        request = urllib.request.Request(str(track.get("url")), headers={"user-agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310 - YouTube caption URL from yt-dlp metadata
            body = response.read().decode("utf-8", errors="replace")
    except Exception:
        return

    rows = _caption_rows(body, first_nonempty(track.get("ext")))
    if rows:
        _apply_transcript_rows(source, rows)


def _enrich_youtube_transcript_with_api(source: Source) -> None:
    video_id = _youtube_video_id(source.url)
    if not video_id:
        return

    rows = _fetch_transcript_with_python(video_id, sys.executable)
    if not rows and sys.executable != "/opt/anaconda3/bin/python3":
        rows = _fetch_transcript_with_python(video_id, "/opt/anaconda3/bin/python3")
    if rows:
        _apply_transcript_rows(source, rows)


def _fetch_transcript_with_python(video_id: str, python_bin: str) -> list[dict[str, Any]]:
    script = r"""
import json
import sys
from youtube_transcript_api import YouTubeTranscriptApi

video_id = sys.argv[1]
ytt = YouTubeTranscriptApi()
languages = ["zh-Hans", "zh-CN", "zh-Hant", "zh", "en", "en-US"]
try:
    transcript = ytt.fetch(video_id, languages=languages)
except TypeError:
    transcript = ytt.fetch(video_id)
rows = []
for item in transcript:
    rows.append({
        "text": getattr(item, "text", ""),
        "start": getattr(item, "start", None),
        "end": (getattr(item, "start", 0) or 0) + (getattr(item, "duration", 0) or 0),
    })
print(json.dumps(rows, ensure_ascii=False))
"""
    try:
        result = subprocess.run(
            [python_bin, "-c", script, video_id],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    return rows_from_payload(rows)


def _pick_caption_track(groups: dict[str, Any]) -> dict[str, Any] | None:
    for lang in ("zh-Hans", "zh-CN", "zh", "en", "en-US"):
        tracks = groups.get(lang)
        if not isinstance(tracks, list):
            continue
        for preferred_ext in ("json3", "vtt"):
            for track in tracks:
                if isinstance(track, dict) and first_nonempty(track.get("url")) and track.get("ext") == preferred_ext:
                    return track
    return None


def _caption_rows(body: str, ext: str) -> list[dict[str, Any]]:
    if ext == "json3":
        try:
            payload = json.loads(body)
            rows = []
            for event in payload.get("events", []):
                if not isinstance(event, dict):
                    continue
                text = "".join(str(seg.get("utf8", "")) for seg in event.get("segs", []) if isinstance(seg, dict)).strip()
                if text:
                    rows.append({
                        "text": text,
                        "start": event.get("tStartMs"),
                        "end": (event.get("tStartMs") or 0) + (event.get("dDurationMs") or 0),
                    })
            return rows
        except Exception:
            return []
    rows = []
    for line in body.splitlines():
        clean = strip_html(re.sub(r"<[^>]+>", "", line)).strip()
        if not clean or clean == "WEBVTT" or "-->" in clean or clean.isdigit():
            continue
        rows.append({"text": clean})
    return rows


def _youtube_video_id(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.netloc.endswith("youtu.be"):
        return parsed.path.strip("/")
    if parsed.path.startswith("/shorts/"):
        return parsed.path.split("/", 2)[2].split("/", 1)[0]
    query = urllib.parse.parse_qs(parsed.query)
    return first_nonempty(*(query.get("v") or []))


def _safe_youtube_error(exc: Exception) -> str:
    text = str(exc)
    key = _youtube_api_key()
    if key:
        text = text.replace(key, "[redacted]")
    return text


def _search_youtube_with_ytdlp(query: str, limit: int) -> tuple[list[Source], str]:
    cmd = [
        sys.executable,
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
