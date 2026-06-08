import { PLATFORMS } from "@/lib/platforms";
import type { ResearchReport, ResearchStage, RunRecord, Source } from "@/lib/api";

export const runCreationCache = new Map<string, Promise<RunRecord>>();

export function createDraftReport(
  query: string,
  lang: "zh" | "en",
  runId = "",
  stages: ResearchStage[] = [],
): ResearchReport {
  return {
    runId,
    productName: "VoxLens",
    slogan:
      lang === "zh"
        ? "\u89c6\u9891\u8bc1\u636e\uff0c\u53ef\u4fe1\u7814\u7a76"
        : "Citable social-video research",
    title: query,
    query,
    need: query,
    lang,
    status: "running",
    confidence: "insufficient",
    generatedAt: new Date().toISOString(),
    totalVideos: 0,
    totalComments: 0,
    platforms: createPlatformSummaries([]),
    outline: [],
    takeaways: [],
    sections: [],
    sources: [],
    warnings: [],
    methodology: [],
    ui: createDraftUi(stages),
    runLogs: [],
    agentTrace: [],
    isDemoFallback: false,
  };
}

export function createDraftUi(stages: ResearchStage[] = []) {
  return {
    activeStage: stages.find((stage) => stage.status === "running")?.id || "plan",
    progress: 0,
    stages,
    sourceGroups: PLATFORMS.map((p) => ({
      id: p.id,
      name: p.name,
      count: 0,
      citedCount: 0,
      status: "queued" as const,
      note: "",
    })),
    interactionHints: {},
  };
}

export function mergeSourcesIntoReport(
  report: ResearchReport,
  incoming: Source[],
  replace = false,
): ResearchReport {
  const byKey = new Map<string, Source>();
  const seed = replace ? incoming : [...report.sources, ...incoming];
  for (const source of seed) {
    const key = source.url || `${source.platform}-${source.id}-${source.title}`;
    byKey.set(key, { ...byKey.get(key), ...source });
  }
  const sources = Array.from(byKey.values()).sort((a, b) => (a.id || 9999) - (b.id || 9999));
  return {
    ...report,
    totalVideos: sources.length,
    totalComments: sources.reduce((sum, source) => sum + (source.comments?.length ?? 0), 0),
    platforms: createPlatformSummaries(sources, report.platforms),
    sources,
    ui: report.ui
      ? {
          ...report.ui,
          sourceGroups: PLATFORMS.map((p) => ({
            id: p.id,
            name: p.name,
            count: sources.filter((source) => source.platform === p.id).length,
            citedCount: sources.filter(
              (source) => source.platform === p.id && (source.citationCount ?? 0) > 0,
            ).length,
            status: sources.some((source) => source.platform === p.id) ? "completed" : "queued",
            note: report.platforms.find((platform) => platform.id === p.id)?.note ?? "",
          })),
        }
      : report.ui,
  };
}

function createPlatformSummaries(sources: Source[], existing: ResearchReport["platforms"] = []) {
  return PLATFORMS.map((p) => {
    const old = existing.find((item) => item.id === p.id);
    const count = sources.filter((source) => source.platform === p.id).length;
    return {
      id: p.id,
      name: p.name,
      logo: p.logo,
      count,
      status: (count > 0 ? "ok" : (old?.status ?? "partial")) as
        | "ok"
        | "partial"
        | "failed"
        | "demo",
      note: old?.note ?? "",
    };
  });
}

export function upsertSection(
  report: ResearchReport,
  section: ResearchReport["sections"][number],
): ResearchReport {
  const sections = [...report.sections];
  const index = sections.findIndex((item) => item.id === section.id);
  if (index >= 0) sections[index] = section;
  else sections.push(section);
  return { ...report, sections };
}

export function appendSectionDelta(
  report: ResearchReport,
  sectionId: string,
  delta: string,
): ResearchReport {
  const sections = [...report.sections];
  const index = sections.findIndex((item) => item.id === sectionId);
  if (index >= 0) {
    sections[index] = { ...sections[index], body: `${sections[index].body || ""}${delta}` };
  } else {
    sections.push({
      id: sectionId,
      title: sectionId,
      level: 1,
      body: delta,
      bullets: [],
      table: [],
    });
  }
  return { ...report, sections };
}
