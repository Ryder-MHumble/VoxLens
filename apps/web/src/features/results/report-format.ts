import { PLATFORMS } from "@/lib/platforms";
import type { ResearchReport, ResearchStage, ResearchStreamEvent, Source } from "@/lib/api";
import type { Lang } from "@/lib/i18n";

export type ProviderActivity = {
  key: string;
  platform: string;
  provider: string;
  status: "running" | "completed" | "failed" | "partial";
  count: number;
  message: string;
};

export function failedPlatformsFromWarnings(
  warnings: string[],
  platforms: ResearchReport["platforms"],
) {
  const failed = new Map<string, string>();
  const counts = new Map(platforms.map((platform) => [platform.id, platform.count]));
  for (const warning of warnings) {
    for (const platform of PLATFORMS) {
      if (warning.toLowerCase().includes(platform.id) && (counts.get(platform.id) ?? 0) === 0) {
        failed.set(platform.id, warning);
      }
    }
  }
  return Array.from(failed, ([platform, message]) => ({ platform, message }));
}

export function providerActivities(events: ResearchStreamEvent[]): ProviderActivity[] {
  const byKey = new Map<string, ProviderActivity>();
  for (const event of events) {
    if (event.type !== "provider_started" && event.type !== "sources") continue;
    const target = event.target as { platform?: string; provider?: string } | undefined;
    const log = event.type === "sources" ? event.log : undefined;
    const platform = target?.platform || String(log?.platform || "unknown");
    const provider = target?.provider || String(log?.provider || "provider");
    const key = `${platform}:${provider}`;
    const count =
      typeof log?.count === "number"
        ? log.count
        : Array.isArray(event.sources)
          ? event.sources.length
          : 0;
    const ok = typeof log?.ok === "boolean" ? log.ok : true;
    byKey.set(key, {
      key,
      platform,
      provider,
      status:
        event.type === "provider_started"
          ? "running"
          : ok
            ? "completed"
            : count > 0
              ? "partial"
              : "failed",
      count,
      message: event.message || String(log?.note || ""),
    });
  }
  return Array.from(byKey.values()).sort((a, b) => a.platform.localeCompare(b.platform));
}

export function activityStatusClass(status: ProviderActivity["status"]) {
  if (status === "completed") return "bg-emerald-400";
  if (status === "failed") return "bg-red-400";
  if (status === "partial") return "bg-amber-400";
  return "animate-pulse bg-[color:var(--violet)]";
}

export function platformName(platform: string) {
  return PLATFORMS.find((p) => p.id === platform)?.name || platform;
}

const RESULT_COPY = {
  en: {
    deepResearchPipeline: "DeepResearch pipeline",
    collapse: "Collapse",
    expand: "Expand",
    waitingForBackend: "Waiting for backend events...",
    backend: "Backend",
    coverage: "Coverage",
    sources: "Sources",
    comments: "Comments",
    platforms: "Platforms",
    cited: "Cited",
    quality: "Quality",
    evidence: "Evidence",
    citations: "Citations",
    risk: "Risk",
    insight: "Insight",
    opportunity: "Opportunity",
    finding: "Finding",
    trend: "Trend",
    recommendation: "Recommendation",
    disagreement: "Disagreement",
    notAvailable: "n/a",
  },
  zh: {
    deepResearchPipeline: "DeepResearch 流程",
    collapse: "收起",
    expand: "展开",
    waitingForBackend: "等待后端事件...",
    backend: "后端",
    coverage: "覆盖度",
    sources: "来源",
    comments: "评论",
    platforms: "平台",
    cited: "被引用",
    quality: "质量",
    evidence: "证据",
    citations: "引用",
    risk: "风险",
    insight: "洞察",
    opportunity: "机会",
    finding: "发现",
    trend: "趋势",
    recommendation: "建议",
    disagreement: "分歧",
    notAvailable: "暂无",
  },
} as const;

export type ResultCopyKey = keyof typeof RESULT_COPY.en;

export function resultCopy(lang: Lang, key: ResultCopyKey) {
  return RESULT_COPY[lang][key];
}

export function formatStageLabel(stage: ResearchStage, lang: Lang) {
  const labels: Record<string, Record<Lang, string>> = {
    plan: { en: "Plan query", zh: "规划问题" },
    search: { en: "Search sources", zh: "搜索来源" },
    evidence: { en: "Structure evidence", zh: "整理证据" },
    synthesis: { en: "Synthesize report", zh: "生成报告" },
  };
  return labels[stage.id]?.[lang] || stage.label;
}

export function formatInsightKind(kind: string | undefined, lang: Lang) {
  const normalized = (kind || "").trim().toLowerCase();
  const keys: Record<string, ResultCopyKey> = {
    insight: "insight",
    risk: "risk",
    opportunity: "opportunity",
    finding: "finding",
    findings: "finding",
    trend: "trend",
    recommendation: "recommendation",
    recommendations: "recommendation",
    disagreement: "disagreement",
    disagreements: "disagreement",
    coverage: "coverage",
  };
  const key = keys[normalized] || "insight";
  return resultCopy(lang, key);
}

export function formatRiskLabel(label: string | undefined, lang: Lang) {
  if (!label) return resultCopy(lang, "notAvailable");
  if (lang === "en") return label;
  const normalized = label.toLowerCase();
  if (normalized.includes("low")) return "低";
  if (normalized.includes("medium") || normalized.includes("moderate")) return "中";
  if (normalized.includes("high")) return "高";
  return label;
}

export function formatEventType(type: string, lang: Lang) {
  if (lang === "en") return type;
  const labels: Record<string, string> = {
    run_started: "任务启动",
    stage: "阶段更新",
    provider_started: "平台检索",
    sources: "来源更新",
    evidence: "证据更新",
    agent_step: "代理步骤",
    outline: "大纲生成",
    report_patch: "报告更新",
    section_started: "开始章节",
    section_delta: "章节流式生成",
    section_complete: "完成章节",
    final_report: "最终报告",
    error: "错误",
  };
  return labels[type] || type;
}

export function localizePipelineMessage(message: string | undefined, lang: Lang) {
  const text = (message || "").trim();
  if (!text) return "";
  if (lang === "en" || /[\u4e00-\u9fff]/u.test(text)) return text;

  const exact: Record<string, string> = {
    "DeepResearch run started.": "DeepResearch 任务已启动。",
    "DeepResearch report completed.": "DeepResearch 报告已完成。",
    completed: "已完成。",
    "Outline and takeaways are ready.": "大纲和核心结论已生成。",
    "Report shell is ready; streaming sections next.": "报告框架已生成，正在流式输出正文。",
    "Generated report outline, takeaways, source metadata and streamable sections.":
      "已生成报告大纲、核心结论、来源元数据和可流式输出的章节。",
    "Generated report sections, takeaways, comparison table and source citations.":
      "已生成报告章节、核心结论、对比表和来源引用。",
    "Live providers disabled; returned a query-specific planning report without factual claims.":
      "实时来源已关闭，已返回不含事实断言的查询规划报告。",
  };
  if (exact[text]) return exact[text];

  const collected = text.match(/^Collected (\d+) sources\.$/);
  if (collected) return `已收集 ${collected[1]} 个来源。`;

  const planned = text.match(/^Planned (\d+) crawl targets for (\d+) platforms\.$/);
  if (planned) return `已为 ${planned[2]} 个平台规划 ${planned[1]} 个抓取目标。`;

  const prepared = text.match(/^Prepared (\d+) sources for report synthesis\.$/);
  if (prepared) return `已为报告生成准备 ${prepared[1]} 个来源。`;

  const searching = text.match(/^Searching (.+?) with (.+)$/);
  if (searching) return `正在使用 ${searching[2]} 搜索 ${platformName(searching[1])}。`;

  const returned = text.match(/^(.+?) returned (\d+) new sources for (.+)$/);
  if (returned)
    return `${returned[1]} 为 ${platformName(returned[3])} 返回 ${returned[2]} 个新来源。`;

  const onlySources = text.match(/^Only (\d+) live sources collected; requested at least (\d+)\./);
  if (onlySources)
    return `仅收集到 ${onlySources[1]} 个实时来源，低于至少 ${onlySources[2]} 个来源的目标。`;

  const streaming = text.match(/^Streaming section (\d+)\/(\d+)$/);
  if (streaming) return `正在生成第 ${streaming[1]}/${streaming[2]} 个章节。`;

  const completedSection = text.match(/^Completed section (\d+)\/(\d+)$/);
  if (completedSection) return `已完成第 ${completedSection[1]}/${completedSection[2]} 个章节。`;

  return text;
}

export function statusClass(status?: ResearchStage["status"]) {
  if (status === "completed") return "bg-emerald-400";
  if (status === "failed") return "bg-red-400";
  if (status === "partial") return "bg-amber-400";
  if (status === "running") return "animate-pulse bg-[color:var(--violet)]";
  return "bg-muted-foreground/30";
}

export function sourceTeaser(source: Source) {
  const rawText =
    source.summary ||
    source.whyRelevant ||
    source.transcriptPreview ||
    source.highlights?.[0] ||
    "";
  const text = rawText.replace(/\s+/g, " ").trim();
  const maxLength = 82;
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).replace(/[\s,.;:!?]+$/u, "")}...`;
}

export function imageFileName(title: string) {
  const safeTitle = title
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 64);
  return `voxlens-report-${safeTitle || Date.now()}`;
}

export function formatReportDate(value: string | undefined, lang: "zh" | "en") {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(lang === "zh" ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export type ComparisonTableRow = ResearchReport["sections"][number]["table"][number];

export function getDimensionColumns(rows: ComparisonTableRow[]) {
  const columns: Array<{ key: string; label: string }> = [];
  for (const row of rows) {
    for (const dimension of row.dimensions ?? []) {
      if (!dimension.key || columns.some((column) => column.key === dimension.key)) continue;
      columns.push({ key: dimension.key, label: dimension.label || dimension.key });
      if (columns.length >= 6) return columns;
    }
  }
  return columns;
}

export function getRowDimension(row: ComparisonTableRow, key: string) {
  return row.dimensions?.find((dimension) => dimension.key === key);
}

export function scoreValue(...values: Array<number | null | undefined>) {
  const value = values.find((item) => typeof item === "number");
  return Math.max(1, Math.min(5, Math.round(value ?? 3)));
}

export function legacyRisk(row: ComparisonTableRow) {
  if (typeof row.risk === "number") return scoreValue(row.risk);
  if (typeof row.video === "number") return scoreValue(6 - row.video);
  return 3;
}

export function fallbackThumb(platform?: string) {
  if (platform === "douyin")
    return "https://images.unsplash.com/photo-1611162618071-b39a2ec055fb?auto=format&fit=crop&w=420&q=80";
  if (platform === "bilibili")
    return "https://images.unsplash.com/photo-1536240478700-b869070f9279?auto=format&fit=crop&w=420&q=80";
  if (platform === "xiaohongshu")
    return "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=420&q=80";
  if (platform === "zhihu")
    return "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?auto=format&fit=crop&w=420&q=80";
  if (platform === "kuaishou")
    return "https://images.unsplash.com/photo-1522869635100-9f4c5e86aa37?auto=format&fit=crop&w=420&q=80";
  if (platform === "weibo")
    return "https://images.unsplash.com/photo-1495020689067-958852a7765e?auto=format&fit=crop&w=420&q=80";
  return "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=420&q=80";
}
