export type PlatformId = "bilibili" | "douyin" | "youtube" | "xiaohongshu" | "zhihu" | "kuaishou" | "weibo";
export type Lang = "zh" | "en";
export type ResearchMode = "auto" | "consumer" | "business";

export type Comment = {
  author: string;
  text: string;
  likes?: string | number | null;
  time?: string;
};

export type Source = {
  id: number;
  platform: PlatformId;
  sourceType?: string;
  domain?: string;
  title: string;
  author?: string;
  creator: string;
  url: string;
  thumbnail: string;
  duration: string;
  published: string;
  summary: string;
  metrics: Record<string, unknown>;
  comments: Comment[];
  transcriptPreview: string;
  fullTranscript?: string;
  evidenceChannels?: string[];
  quality?: Record<string, unknown>;
  provider?: string;
  relevanceScore?: number;
  evidenceScore?: number;
  citationCount?: number;
  badges?: string[];
  highlights?: string[];
  whyRelevant?: string;
  status?: "collected" | "ranked" | "cited" | "weak";
  collectedAt?: string;
};

export type PlatformSummary = {
  id: PlatformId;
  name: string;
  logo: string;
  count: number;
  status: "ok" | "partial" | "failed" | "demo";
  note: string;
};

export type CitationText = {
  text: string;
  citations: number[];
};

export type VideoQuote = {
  sourceId: number;
  quote: string;
  author: string;
  thumbnail: string;
  duration: string;
};

export type ComparisonDimension = {
  key: string;
  label: string;
  score?: number | null;
  summary?: string;
  evidence: number[];
  metrics?: Record<string, unknown>;
};

export type ComparisonRow = {
  name: string;
  signal?: string;
  support?: number;
  risk?: number;
  freshness?: number;
  confidence?: number;
  camera?: number | null;
  lowLight?: number | null;
  video?: number | null;
  battery?: number | null;
  price: string;
  dimensions?: ComparisonDimension[];
  metrics?: Record<string, unknown>;
  evidence: number[];
};

export type DecisionCandidate = {
  name: string;
  matchReason: string;
  sourceIds: number[];
};

export type DimensionComparisonValue = {
  candidate: string;
  conclusion: string;
  condition?: string;
  confidence: "green" | "yellow" | "gray" | string;
  sourceIds: number[];
};

export type DimensionComparison = {
  dimension: string;
  values: DimensionComparisonValue[];
  isContradictory?: boolean;
  contradictionReason?: string;
};

export type DecisionRecommendation = {
  primary?: string;
  backup?: string;
  notRecommended?: string;
  conditions?: string[];
  sourceIds?: number[];
  scores?: Record<string, number>;
};

export type ReportSectionData = Record<string, unknown> & {
  candidates?: DecisionCandidate[];
  comparisons?: DimensionComparison[];
  recommendation?: DecisionRecommendation;
};

export type ReportSection = {
  id: string;
  title: string;
  kind?: string;
  level: number;
  body: string;
  bullets: CitationText[];
  quote?: VideoQuote | null;
  table: ComparisonRow[];
  sourceIds?: number[];
  metrics?: Record<string, unknown>;
  data?: ReportSectionData;
};

export type OutlineItem = {
  id: string;
  label: string;
  title?: string;
  summary?: string;
  status?: "queued" | "running" | "completed" | "partial" | "failed" | "skipped";
  sourceIds?: number[];
  citationCount?: number;
};

export type AgentStep = {
  name: string;
  role: string;
  status: "ok" | "partial" | "failed" | "skipped";
  message: string;
  elapsedSec: number;
  metrics: Record<string, unknown>;
};

export type ResearchStage = {
  id: string;
  label: string;
  status: "queued" | "running" | "completed" | "partial" | "failed" | "skipped";
  progress: number;
  message: string;
  startedAt?: string;
  completedAt?: string;
};

export type ReportUIState = {
  activeStage: string;
  progress: number;
  stages: ResearchStage[];
  sourceGroups: Array<{
    id: PlatformId;
    name: string;
    count: number;
    citedCount: number;
    status: "queued" | "running" | "completed" | "partial" | "failed" | "skipped";
    note: string;
  }>;
  interactionHints: Record<string, string>;
};

export type ReportInsight = {
  id: string;
  kind?: "answer" | "consensus" | "disagreement" | "risk" | "opportunity" | "coverage" | string;
  label: string;
  summary?: string;
  confidence?: number;
  sourceIds?: number[];
};

export type CoverageSummary = {
  totalSources?: number;
  totalComments?: number;
  platformCount?: number;
  citedSources?: number;
  withComments?: number;
  withTranscripts?: number;
  providerRuns?: number;
  successfulProviderRuns?: number;
  failedProviderRuns?: number;
};

export type QualityEvaluation = {
  coverage: QualityMetric;
  citationAccuracy: QualityMetric;
  evidenceStrength: QualityMetric;
  conclusionRisk: QualityMetric;
  overall: number;
  warnings: string[];
};

export type QualityMetric = {
  score: number;
  label: string;
  rationale: string;
  sourceIds: number[];
};

export type ResearchReport = {
  runId?: string;
  productName: string;
  slogan: string;
  title: string;
  query: string;
  need: string;
  lang: Lang;
  status?: "queued" | "running" | "completed" | "partial" | "failed";
  confidence?: "high" | "medium" | "low" | "insufficient";
  generatedAt: string;
  totalVideos: number;
  totalComments: number;
  platforms: PlatformSummary[];
  outline: OutlineItem[];
  takeaways: CitationText[];
  insights?: ReportInsight[];
  coverage?: CoverageSummary;
  quality?: QualityEvaluation;
  sections: ReportSection[];
  sources: Source[];
  warnings?: string[];
  methodology?: string[];
  ui?: ReportUIState | null;
  runLogs: Array<Record<string, unknown>>;
  agentTrace: AgentStep[];
  isDemoFallback: boolean;
};

export type ResearchRequest = {
  need: string;
  query?: string;
  researchMode?: ResearchMode;
  platforms?: PlatformId[];
  limitPerPlatform?: number;
  commentsPerVideo?: number;
  detailVideosPerPlatform?: number;
  useLiveProviders?: boolean;
  useCrawlerRuntime?: boolean;
  providerMode?: "local" | "online" | "hybrid";
  authMode?: "auto" | "existing_browser" | "cookie" | "qrcode";
  includeTranscripts?: boolean;
  crawlMedia?: boolean;
  maxParallelPlatforms?: number;
  maxParallelVideos?: number;
  minLiveSources?: number;
  lang?: Lang;
};

export type RunRecord = {
  runId: string;
  status: "queued" | "running" | "completed" | "partial" | "failed" | "cancelled";
  request: ResearchRequest;
  createdAt: string;
  updatedAt: string;
  queuedAt?: string;
  startedAt?: string;
  completedAt?: string;
  progress: number;
  eventCount: number;
  report?: ResearchReport | null;
  error?: string;
};

export type ResearchStreamEvent =
  | ({ type: "run_started"; runId: string; query: string; need: string; lang: Lang; stages: ResearchStage[]; message: string } & Record<string, unknown>)
  | ({ type: "stage"; stageId: string; status: ResearchStage["status"]; progress: number; stageProgress: number; message: string; stages: ResearchStage[] } & Record<string, unknown>)
  | ({ type: "plan"; runId: string; plan: unknown; step: AgentStep; progress: number; message: string } & Record<string, unknown>)
  | ({ type: "provider_started"; runId: string; target: unknown; progress: number; message: string } & Record<string, unknown>)
  | ({ type: "sources"; runId: string; sources: Source[]; log: Record<string, unknown>; progress: number; message: string } & Record<string, unknown>)
  | ({ type: "agent_step"; runId: string; step: AgentStep; progress: number; message: string } & Record<string, unknown>)
  | ({ type: "evidence"; runId: string; sources: Source[]; step: AgentStep; progress: number; message: string } & Record<string, unknown>)
  | ({ type: "outline"; runId: string; outline: OutlineItem[]; takeaways: CitationText[]; insights?: ReportInsight[]; coverage?: CoverageSummary; quality?: QualityEvaluation; warnings: string[]; progress: number; message: string } & Record<string, unknown>)
  | ({ type: "report_patch"; runId: string; report: ResearchReport; progress: number; message: string } & Record<string, unknown>)
  | ({ type: "section_started"; runId: string; sectionId: string; section: ReportSection; progress: number; message: string } & Record<string, unknown>)
  | ({ type: "section_delta"; runId: string; sectionId: string; delta: string; progress: number; message?: string } & Record<string, unknown>)
  | ({ type: "section_complete"; runId: string; section: ReportSection; progress: number; message: string } & Record<string, unknown>)
  | ({ type: "final_report"; runId: string; report: ResearchReport; progress: number; message: string } & Record<string, unknown>)
  | ({ type: "error"; runId: string; message: string; progress: number } & Record<string, unknown>);

const API_BASE = (
  import.meta.env.VITE_VOXLENS_API_BASE ||
  import.meta.env.VITE_SCANCAST_API_BASE ||
  "/api"
).replace(/\/$/, "");

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getDemoReport(lang: Lang) {
  return requestJson<ResearchReport>(`/demo-report?lang=${lang}`);
}

export function runResearch(payload: ResearchRequest) {
  return requestJson<ResearchReport>("/research", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createResearchRun(payload: ResearchRequest) {
  return requestJson<RunRecord>("/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getResearchRun(runId: string) {
  return requestJson<RunRecord>(`/runs/${encodeURIComponent(runId)}`);
}

export async function streamResearchRun(
  runId: string,
  onEvent: (event: ResearchStreamEvent) => void,
  signal?: AbortSignal,
) {
  const response = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/events`, { signal });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  await readSseResponse(response, onEvent);
}

export async function runResearchStream(
  payload: ResearchRequest,
  onEvent: (event: ResearchStreamEvent) => void,
  signal?: AbortSignal,
) {
  const response = await fetch(`${API_BASE}/research/stream`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  if (!response.body) {
    onEvent({ type: "final_report", runId: "", report: await response.json(), progress: 100, message: "completed" });
    return;
  }

  await readSseResponse(response, onEvent);
}

async function readSseResponse(
  response: Response,
  onEvent: (event: ResearchStreamEvent) => void,
) {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const parsed = parseSseEvent(part);
      if (parsed) onEvent(parsed);
    }
  }
  const tail = parseSseEvent(buffer);
  if (tail) onEvent(tail);
}

function parseSseEvent(raw: string): ResearchStreamEvent | null {
  const dataLines = raw
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (!dataLines.length) return null;
  try {
    return JSON.parse(dataLines.join("\n")) as ResearchStreamEvent;
  } catch {
    return null;
  }
}
