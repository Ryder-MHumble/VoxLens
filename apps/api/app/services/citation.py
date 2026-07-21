from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote_plus

from app.models import EvidenceUnit, PlatformId

_CITATION_PATTERN = re.compile(r"^\[(?P<platform>[A-Z]+):(?P<object>[^@/\]]+)(?P<suffix>[^\]]*)\]$")
_TIMESTAMP_PATTERN = re.compile(r"^@(?P<start>\d{1,2}:\d{2}(?::\d{2})?)-(?P<end>\d{1,2}:\d{2}(?::\d{2})?)$")
_COMMENT_PATTERN = re.compile(r"^/comment/(?P<comment_id>[^/\]]+)$")
_FRAME_PATTERN = re.compile(r"^/frame/(?P<frame_index>\d+)(?:/ocr)?$")


class CitationParseError(ValueError):
    """Signal that a citation does not match a supported VoxLens reference format."""


@dataclass(frozen=True)
class ParsedCitation:
    """Represent a parsed source-, timestamp-, comment-, or frame-level citation."""

    raw: str
    platform: str
    platform_object_id: str
    kind: str
    start_ms: int | None = None
    end_ms: int | None = None
    comment_id: str = ""
    frame_index: int | None = None


def parse_citation(value: str) -> ParsedCitation:
    """Parse a VoxLens citation into structured lookup fields."""

    match = _CITATION_PATTERN.fullmatch(value.strip())
    if not match:
        raise CitationParseError(f"Unsupported citation format: {value}")
    platform = match.group("platform")
    object_id = match.group("object")
    suffix = match.group("suffix")
    if not suffix:
        return ParsedCitation(value, platform, object_id, "source")

    timestamp = _TIMESTAMP_PATTERN.fullmatch(suffix)
    if timestamp:
        start_ms = _timestamp_to_ms(timestamp.group("start"))
        end_ms = _timestamp_to_ms(timestamp.group("end"))
        if end_ms < start_ms:
            raise CitationParseError("Citation end timestamp precedes its start timestamp.")
        return ParsedCitation(value, platform, object_id, "timestamp", start_ms=start_ms, end_ms=end_ms)

    comment = _COMMENT_PATTERN.fullmatch(suffix)
    if comment:
        return ParsedCitation(value, platform, object_id, "comment", comment_id=comment.group("comment_id"))

    frame = _FRAME_PATTERN.fullmatch(suffix)
    if frame:
        return ParsedCitation(value, platform, object_id, "frame", frame_index=int(frame.group("frame_index")))

    raise CitationParseError(f"Unsupported citation suffix: {suffix}")


def format_citation(
    evidence_unit: EvidenceUnit,
    *,
    platform: PlatformId,
    platform_object_id: str,
) -> str:
    """Format an evidence unit as the most precise supported citation reference."""

    return evidence_unit.citation_ref(platform, platform_object_id)


def build_citation_link(citation: ParsedCitation, *, source_url: str = "") -> str:
    """Build a clickable platform URL while preserving the citation's precise location."""

    platform = citation.platform.lower()
    if platform == "bilibili":
        base = source_url or f"https://www.bilibili.com/video/{citation.platform_object_id}"
        if citation.start_ms is not None:
            separator = "&" if "?" in base else "?"
            return f"{base}{separator}t={citation.start_ms // 1000}"
        return base
    if platform == "douyin":
        base = source_url or f"https://www.douyin.com/video/{citation.platform_object_id}"
        if citation.comment_id:
            separator = "&" if "?" in base else "?"
            return f"{base}{separator}comment_id={quote_plus(citation.comment_id)}"
        return base
    if platform == "youtube":
        base = source_url or f"https://www.youtube.com/watch?v={citation.platform_object_id}"
        if citation.start_ms is not None:
            separator = "&" if "?" in base else "?"
            return f"{base}{separator}t={citation.start_ms // 1000}s"
        return base
    if platform == "xiaohongshu":
        return source_url or f"https://www.xiaohongshu.com/explore/{citation.platform_object_id}"
    return source_url


def resolve_evidence_unit(
    citation: ParsedCitation,
    evidence_units: Iterable[EvidenceUnit],
    *,
    source_id: int | None = None,
    artifact_id: str | None = None,
) -> EvidenceUnit | None:
    """Resolve a parsed citation back to the best matching original evidence unit."""

    candidates = [
        unit
        for unit in evidence_units
        if (source_id is None or unit.source_id == source_id)
        and (artifact_id is None or unit.artifact_id == artifact_id)
    ]
    if citation.kind == "comment":
        return next((unit for unit in candidates if unit.comment_id == citation.comment_id), None)
    if citation.kind == "frame":
        return next((unit for unit in candidates if unit.frame_index == citation.frame_index), None)
    if citation.kind == "timestamp" and citation.start_ms is not None:
        overlapping = [
            unit
            for unit in candidates
            if unit.start_ms is not None
            and unit.end_ms is not None
            and unit.start_ms <= (citation.end_ms or citation.start_ms)
            and unit.end_ms >= citation.start_ms
        ]
        return min(overlapping, key=lambda unit: abs((unit.start_ms or 0) - citation.start_ms), default=None)
    return candidates[0] if candidates else None


def _timestamp_to_ms(value: str) -> int:
    """Convert MM:SS or HH:MM:SS citation timestamps to milliseconds."""

    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        hours = 0
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise CitationParseError(f"Unsupported timestamp: {value}")
    if (hours and minutes >= 60) or seconds >= 60:
        raise CitationParseError(f"Invalid timestamp: {value}")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000
