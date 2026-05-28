from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.platform_catalog import DEFAULT_PLATFORM_IDS


PlatformId = Literal["bilibili", "douyin", "youtube", "xiaohongshu", "zhihu", "kuaishou", "weibo"]
Lang = Literal["zh", "en"]
AuthMode = Literal["auto", "existing_browser", "cookie", "qrcode"]
AgentStatus = Literal["ok", "partial", "failed", "skipped"]
ReportStatus = Literal["queued", "running", "completed", "partial", "failed"]
StageStatus = Literal["queued", "running", "completed", "partial", "failed", "skipped"]
RunStatus = Literal["queued", "running", "completed", "partial", "failed", "cancelled"]
ProviderMode = Literal["local", "online", "hybrid"]


class ResearchRequest(BaseModel):
    need: str = Field(..., min_length=1)
    query: str | None = None
    platforms: list[PlatformId] = Field(default_factory=lambda: list(DEFAULT_PLATFORM_IDS))
    limitPerPlatform: int = Field(default=12, ge=1, le=50)
    commentsPerVideo: int = Field(default=12, ge=0, le=50)
    detailVideosPerPlatform: int = Field(default=3, ge=0, le=8)
    useLiveProviders: bool = True
    useCrawlerRuntime: bool = True
    providerMode: ProviderMode = "local"
    authMode: AuthMode = "auto"
    includeTranscripts: bool = True
    crawlMedia: bool = False
    maxParallelPlatforms: int = Field(default=3, ge=1, le=5)
    maxParallelVideos: int = Field(default=3, ge=1, le=8)
    minLiveSources: int | None = Field(default=None, ge=1, le=30)
    lang: Lang = "zh"


class Comment(BaseModel):
    author: str = ""
    text: str = ""
    likes: str | int | None = None
    time: str = ""


class TranscriptSegment(BaseModel):
    text: str = ""
    start: str | int | float | None = None
    end: str | int | float | None = None


class Source(BaseModel):
    id: int
    platform: PlatformId
    sourceType: str = "video"
    domain: str = ""
    title: str
    author: str = ""
    creator: str = ""
    url: str = ""
    thumbnail: str = ""
    duration: str = ""
    published: str = ""
    summary: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    comments: list[Comment] = Field(default_factory=list)
    transcriptPreview: str = ""
    transcriptText: str = Field(default="", exclude=True)
    transcriptSegments: list[TranscriptSegment] = Field(default_factory=list, exclude=True)
    evidenceChannels: list[str] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)
    provider: str = ""
    relevanceScore: int = 0
    evidenceScore: int = 0
    citationCount: int = 0
    badges: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    whyRelevant: str = ""
    status: Literal["collected", "ranked", "cited", "weak"] = "collected"
    collectedAt: str = ""


class PlatformSummary(BaseModel):
    id: PlatformId
    name: str
    logo: str
    count: int
    status: Literal["ok", "partial", "failed", "demo"] = "ok"
    note: str = ""


class CitationText(BaseModel):
    text: str
    citations: list[int] = Field(default_factory=list)


class VideoQuote(BaseModel):
    sourceId: int
    quote: str
    author: str
    thumbnail: str
    duration: str = ""


class ComparisonDimension(BaseModel):
    key: str
    label: str
    score: int | None = Field(default=None, ge=1, le=5)
    summary: str = ""
    evidence: list[int] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ComparisonRow(BaseModel):
    name: str
    signal: str = ""
    support: int = 3
    risk: int = 3
    freshness: int = 3
    confidence: int = 3
    camera: int | None = None
    lowLight: int | None = None
    video: int | None = None
    battery: int | None = None
    price: str = ""
    dimensions: list[ComparisonDimension] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    evidence: list[int] = Field(default_factory=list)


class ReportSection(BaseModel):
    id: str
    title: str
    kind: str = "narrative"
    level: int = 1
    body: str = ""
    bullets: list[CitationText] = Field(default_factory=list)
    quote: VideoQuote | None = None
    table: list[ComparisonRow] = Field(default_factory=list)
    sourceIds: list[int] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)


class OutlineItem(BaseModel):
    id: str
    label: str
    title: str = ""
    summary: str = ""
    status: StageStatus = "queued"
    sourceIds: list[int] = Field(default_factory=list)
    citationCount: int = 0


class ResearchStage(BaseModel):
    id: str
    label: str
    status: StageStatus = "queued"
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    startedAt: str = ""
    completedAt: str = ""


class SourceGroup(BaseModel):
    id: PlatformId
    name: str
    count: int = 0
    citedCount: int = 0
    status: StageStatus = "queued"
    note: str = ""


class ReportUIState(BaseModel):
    activeStage: str = ""
    progress: int = Field(default=0, ge=0, le=100)
    stages: list[ResearchStage] = Field(default_factory=list)
    sourceGroups: list[SourceGroup] = Field(default_factory=list)
    interactionHints: dict[str, str] = Field(default_factory=dict)


class RunLog(BaseModel):
    provider: str
    platform: str
    ok: bool
    count: int
    elapsedSec: float = 0
    note: str = ""
    query: str = ""


class CrawlTarget(BaseModel):
    platform: PlatformId
    provider: str
    query: str
    limit: int
    commentsLimit: int
    detailLimit: int
    videoParallelism: int = 1
    authMode: AuthMode = "auto"
    role: str = "primary"


class ResearchPlan(BaseModel):
    canonicalQuery: str
    expandedQueries: list[str] = Field(default_factory=list)
    platforms: list[PlatformId] = Field(default_factory=list)
    targets: list[CrawlTarget] = Field(default_factory=list)
    retrievalDepth: str = "standard"
    notes: list[str] = Field(default_factory=list)


class AgentStep(BaseModel):
    name: str
    role: str
    status: AgentStatus
    message: str = ""
    elapsedSec: float = 0
    metrics: dict[str, Any] = Field(default_factory=dict)


class ReportInsight(BaseModel):
    id: str
    kind: Literal["answer", "consensus", "disagreement", "risk", "opportunity", "coverage"] = "consensus"
    label: str
    summary: str = ""
    confidence: int = Field(default=3, ge=1, le=5)
    sourceIds: list[int] = Field(default_factory=list)


class CoverageSummary(BaseModel):
    totalSources: int = 0
    totalComments: int = 0
    platformCount: int = 0
    citedSources: int = 0
    withComments: int = 0
    withTranscripts: int = 0
    providerRuns: int = 0
    successfulProviderRuns: int = 0
    failedProviderRuns: int = 0


class QualityMetric(BaseModel):
    score: int = Field(default=0, ge=0, le=100)
    label: str = ""
    rationale: str = ""
    sourceIds: list[int] = Field(default_factory=list)


class QualityEvaluation(BaseModel):
    coverage: QualityMetric = Field(default_factory=QualityMetric)
    citationAccuracy: QualityMetric = Field(default_factory=QualityMetric)
    evidenceStrength: QualityMetric = Field(default_factory=QualityMetric)
    conclusionRisk: QualityMetric = Field(default_factory=QualityMetric)
    overall: int = Field(default=0, ge=0, le=100)
    warnings: list[str] = Field(default_factory=list)


class ResearchReport(BaseModel):
    runId: str = ""
    productName: str = "VoxLens"
    slogan: str
    title: str
    query: str
    need: str
    lang: Lang
    status: ReportStatus = "completed"
    confidence: Literal["high", "medium", "low", "insufficient"] = "medium"
    generatedAt: str
    totalVideos: int
    totalComments: int
    platforms: list[PlatformSummary]
    outline: list[OutlineItem]
    takeaways: list[CitationText]
    insights: list[ReportInsight] = Field(default_factory=list)
    coverage: CoverageSummary = Field(default_factory=CoverageSummary)
    quality: QualityEvaluation = Field(default_factory=QualityEvaluation)
    sections: list[ReportSection]
    sources: list[Source]
    warnings: list[str] = Field(default_factory=list)
    methodology: list[str] = Field(default_factory=list)
    ui: ReportUIState | None = None
    runLogs: list[RunLog] = Field(default_factory=list)
    plan: ResearchPlan | None = None
    agentTrace: list[AgentStep] = Field(default_factory=list)
    isDemoFallback: bool = False


class RunRecord(BaseModel):
    runId: str
    status: RunStatus = "queued"
    request: ResearchRequest
    createdAt: str
    updatedAt: str
    queuedAt: str = ""
    startedAt: str = ""
    completedAt: str = ""
    progress: int = Field(default=0, ge=0, le=100)
    eventCount: int = 0
    report: ResearchReport | None = None
    error: str = ""
