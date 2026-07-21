from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol, Sequence
from urllib.parse import urlparse

from app.models import AgentStep, Artifact, EvidenceUnit, Source, TranscriptSegment


class ASRProviderUnavailable(RuntimeError):
    """Signal that an ASR provider is configured but cannot run locally."""


@dataclass(frozen=True)
class MediaInput:
    """Describe a local or remote media candidate without fetching it."""

    value: str
    source_id: int
    candidate_rank: int = 1
    content_hash: str = ""
    rights_basis: str = ""


@dataclass(frozen=True)
class PermissionDecision:
    """Describe whether a media input may enter the extraction pipeline."""

    allowed: bool
    reason: str


@dataclass(frozen=True)
class AudioAsset:
    """Describe the planned or extracted audio passed to VAD and ASR."""

    path: str
    source_media: str
    command: tuple[str, ...] = ()


@dataclass(frozen=True)
class SpeechRegion:
    """Describe one VAD-selected interval in milliseconds."""

    start_ms: int
    end_ms: int | None = None


@dataclass(frozen=True)
class ASRSegment:
    """Describe one provider transcript segment with timing and confidence."""

    text: str
    start_ms: int
    end_ms: int
    confidence: float | None = None
    speaker: str = ""
    language: str = ""


@dataclass
class ASRRunResult:
    """Return the pipeline status, immutable artifact, and citable evidence units."""

    status: Literal["completed", "skipped", "denied"]
    media_hash: str
    artifact: Artifact | None = None
    evidence_units: list[EvidenceUnit] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cache_hit: bool = False


class PermissionChecker(Protocol):
    """Define media access and rights checks."""

    def check(self, media: MediaInput) -> PermissionDecision:
        """Return whether the media may be processed."""


class AudioExtractor(Protocol):
    """Define audio extraction from an approved media input."""

    def extract(self, media: MediaInput) -> AudioAsset:
        """Return an audio asset without prescribing execution mechanics."""


class VADProvider(Protocol):
    """Define voice activity detection over an audio asset."""

    def detect(self, audio: AudioAsset) -> list[SpeechRegion]:
        """Return speech regions to transcribe."""


class ASRProvider(Protocol):
    """Define timestamped speech recognition provider behavior."""

    name: str

    def transcribe(self, audio: AudioAsset, regions: Sequence[SpeechRegion]) -> list[ASRSegment]:
        """Return timestamped transcript segments for selected regions."""


class ASRCache(Protocol):
    """Define hash-keyed transcript caching."""

    def get(self, key: str) -> list[ASRSegment] | None:
        """Return cached transcript segments when present."""

    def set(self, key: str, segments: Sequence[ASRSegment]) -> None:
        """Persist transcript segments for future reuse."""


class DefaultPermissionChecker:
    """Apply a conservative local-file and declared-rights access policy."""

    def __init__(self, *, allow_remote: bool = True) -> None:
        """Configure whether rights-declared remote inputs may be planned."""

        self.allow_remote = allow_remote

    def check(self, media: MediaInput) -> PermissionDecision:
        """Allow local paths and rights-declared remote URLs without opening either."""

        scheme = urlparse(media.value).scheme.lower()
        if scheme in {"http", "https"}:
            if not self.allow_remote:
                return PermissionDecision(False, "Remote media processing is disabled by policy.")
            if not media.rights_basis:
                return PermissionDecision(False, "Remote media requires an explicit rights basis.")
            return PermissionDecision(True, "Remote media rights basis declared.")
        return PermissionDecision(True, "Local media path accepted for offline processing.")


class FFmpegAudioExtractor:
    """Build an ffmpeg extraction plan without executing a subprocess."""

    def __init__(self, *, ffmpeg_binary: str = "ffmpeg", output_dir: str = "/tmp") -> None:
        """Configure the binary name and planned output directory."""

        self.ffmpeg_binary = ffmpeg_binary
        self.output_dir = output_dir

    def extract(self, media: MediaInput) -> AudioAsset:
        """Return the deterministic ffmpeg command that an execution adapter may run."""

        media_hash = media.content_hash or _stable_hash(media.value)
        output_path = str(Path(self.output_dir) / f"voxlens-{media_hash[:16]}.wav")
        command = (
            self.ffmpeg_binary,
            "-i",
            media.value,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            output_path,
        )
        return AudioAsset(path=output_path, source_media=media.value, command=command)


class PassthroughVADProvider:
    """Provide a replaceable VAD placeholder for orchestration tests."""

    def detect(self, audio: AudioAsset) -> list[SpeechRegion]:
        """Return one open-ended region without inspecting audio bytes."""

        return [SpeechRegion(start_ms=0, end_ms=None)]


class FasterWhisperProvider:
    """Reserve the default provider contract for a future faster-whisper adapter."""

    name = "faster-whisper"

    def transcribe(self, audio: AudioAsset, regions: Sequence[SpeechRegion]) -> list[ASRSegment]:
        """Require an injected runtime adapter instead of loading a model implicitly."""

        raise ASRProviderUnavailable(
            "faster-whisper runtime is not bundled; inject an ASRProvider implementation to execute transcription."
        )


class InMemoryASRCache:
    """Store transcript segments by media and provider hash for tests and local runs."""

    def __init__(self) -> None:
        """Initialize an empty process-local transcript cache."""

        self._items: dict[str, list[ASRSegment]] = {}

    def get(self, key: str) -> list[ASRSegment] | None:
        """Return a defensive copy of cached segments."""

        segments = self._items.get(key)
        return list(segments) if segments is not None else None

    def set(self, key: str, segments: Sequence[ASRSegment]) -> None:
        """Cache a defensive copy of transcript segments."""

        self._items[key] = list(segments)


class ASRPipeline:
    """Orchestrate permission, extraction, VAD, ASR, caching, and evidence slicing."""

    def __init__(
        self,
        *,
        permission_checker: PermissionChecker | None = None,
        audio_extractor: AudioExtractor | None = None,
        vad_provider: VADProvider | None = None,
        asr_provider: ASRProvider | None = None,
        cache: ASRCache | None = None,
        top_n: int = 5,
        low_confidence_threshold: float = 0.65,
        collector_version: str = "asr-pipeline-v1",
    ) -> None:
        """Configure replaceable pipeline steps and cost-control thresholds."""

        self.permission_checker = permission_checker or DefaultPermissionChecker()
        self.audio_extractor = audio_extractor or FFmpegAudioExtractor()
        self.vad_provider = vad_provider or PassthroughVADProvider()
        self.asr_provider = asr_provider or FasterWhisperProvider()
        self.cache = cache or InMemoryASRCache()
        self.top_n = max(0, top_n)
        self.low_confidence_threshold = low_confidence_threshold
        self.collector_version = collector_version

    def check_permission(self, media: MediaInput) -> PermissionDecision:
        """Run the independently testable access-policy step."""

        return self.permission_checker.check(media)

    def extract_audio(self, media: MediaInput) -> AudioAsset:
        """Run the independently testable audio-extraction step."""

        return self.audio_extractor.extract(media)

    def detect_speech(self, audio: AudioAsset) -> list[SpeechRegion]:
        """Run the independently testable voice-activity step."""

        return self.vad_provider.detect(audio)

    def transcribe(self, audio: AudioAsset, regions: Sequence[SpeechRegion]) -> list[ASRSegment]:
        """Run the independently testable provider transcription step."""

        return self.asr_provider.transcribe(audio, regions)

    def slice_evidence(self, artifact: Artifact, segments: Sequence[ASRSegment]) -> list[EvidenceUnit]:
        """Convert timestamped transcript segments into stable evidence units."""

        units: list[EvidenceUnit] = []
        for segment in segments:
            confidence = segment.confidence
            review_status = (
                "low_confidence"
                if confidence is not None and confidence < self.low_confidence_threshold
                else "unreviewed"
            )
            unit_hash = _stable_hash(
                f"{artifact.id}:{segment.start_ms}:{segment.end_ms}:{segment.text}"
            )
            units.append(EvidenceUnit(
                id=f"ev-{unit_hash[:20]}",
                text=segment.text,
                normalized_text=" ".join(segment.text.split()),
                modality="speech",
                source_id=artifact.source_id,
                artifact_id=artifact.id,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                asr_confidence=confidence,
                speaker=segment.speaker,
                language=segment.language,
                extraction_method=self.asr_provider.name,
                content_hash=_stable_hash(segment.text),
                review_status=review_status,
            ))
        return units

    def run(self, media: MediaInput) -> ASRRunResult:
        """Execute the code-only pipeline while honoring Top-N and hash-cache controls."""

        media_hash = media.content_hash or _stable_hash(media.value)
        if media.candidate_rank > self.top_n:
            return ASRRunResult(
                status="skipped",
                media_hash=media_hash,
                warnings=[f"Candidate rank {media.candidate_rank} exceeds ASR Top-N limit {self.top_n}."],
            )

        permission = self.check_permission(media)
        if not permission.allowed:
            return ASRRunResult(status="denied", media_hash=media_hash, warnings=[permission.reason])

        cache_key = f"{self.asr_provider.name}:{media_hash}"
        segments = self.cache.get(cache_key)
        cache_hit = segments is not None
        if segments is None:
            audio = self.extract_audio(media)
            regions = self.detect_speech(audio)
            segments = self.transcribe(audio, regions)
            self.cache.set(cache_key, segments)

        artifact_id = f"artifact-asr-{media_hash[:16]}"
        transcript_text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        artifact = Artifact(
            id=artifact_id,
            source_id=media.source_id,
            artifact_type="subtitle",
            content_hash=_stable_hash(transcript_text) if transcript_text else media_hash,
            captured_at=datetime.now().isoformat(timespec="seconds"),
            collector_name=self.asr_provider.name,
            collector_version=self.collector_version,
            raw_metadata={"media_hash": media_hash, "cache_hit": cache_hit},
            full_transcript=transcript_text,
            transcript_segments=[
                TranscriptSegment(text=segment.text, start=segment.start_ms, end=segment.end_ms)
                for segment in segments
            ],
        )
        evidence_units = self.slice_evidence(artifact, segments)
        low_confidence_count = sum(unit.review_status == "low_confidence" for unit in evidence_units)
        warnings = []
        if low_confidence_count:
            warnings.append(f"{low_confidence_count} ASR segment(s) require review due to low confidence.")
        return ASRRunResult(
            status="low_confidence" if low_confidence_count else "completed",
            media_hash=media_hash,
            artifact=artifact,
            evidence_units=evidence_units,
            warnings=warnings,
            cache_hit=cache_hit,
        )


def plan_asr_candidates(sources: Sequence[Source], *, top_n: int = 5) -> tuple[list[MediaInput], AgentStep]:
    """Select Top-N URL-backed sources for later ASR execution without opening media."""

    candidates = [
        MediaInput(
            value=source.url,
            source_id=source.id,
            candidate_rank=rank,
            content_hash=str(source.metrics.get("content_hash", "")),
            rights_basis=str(source.metrics.get("rights_basis", "")),
        )
        for rank, source in enumerate((source for source in sources if source.url), start=1)
        if rank <= max(0, top_n)
    ]
    return candidates, AgentStep(
        name="ASRPipeline",
        role="Plans permission check, ffmpeg extraction, VAD, ASR, timestamp slicing and EvidenceUnit creation.",
        status="ok" if candidates else "skipped",
        message=(
            f"Selected {len(candidates)} Top-N media candidate(s) for deferred ASR execution."
            if candidates
            else "No URL-backed source qualified for deferred ASR execution."
        ),
        metrics={"candidates": len(candidates), "topN": max(0, top_n), "provider": FasterWhisperProvider.name},
    )


def _stable_hash(value: str) -> str:
    """Return a deterministic SHA-256 hash for cache and immutable identifiers."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()
