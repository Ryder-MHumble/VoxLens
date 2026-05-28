import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import gsap from "gsap";
import { toPng } from "html-to-image";
import {
  ChevronDown,
  ChevronUp,
  Download,
  ExternalLink,
  Play,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { z } from "zod";
import { BrandMark } from "@/components/BrandMark";
import { LangToggle } from "@/components/LangToggle";
import { PlatformLogoImage, PLATFORMS } from "@/components/PlatformLogos";
import { WebSearchIcon } from "@/components/WebSearchIcon";
import {
  createResearchRun,
  getDemoReport,
  getResearchRun,
  runResearch,
  streamResearchRun,
  type PlatformId,
  type ResearchReport,
  type RunRecord,
  type ResearchStage,
  type ResearchStreamEvent,
  type Source,
} from "@/lib/api";
import { useI18n, type Lang } from "@/lib/i18n";

const searchSchema = z.object({
  q: z.preprocess((value) => (value == null ? undefined : String(value)), z.string().optional()),
  live: z.preprocess((value) => (value == null ? undefined : String(value)), z.string().optional()),
  run: z.preprocess((value) => (value == null ? undefined : String(value)), z.string().optional()),
});
const DEFAULT_RESEARCH_PLATFORMS: PlatformId[] = ["bilibili", "douyin", "youtube", "xiaohongshu", "zhihu", "kuaishou", "weibo"];
const runCreationCache = new Map<string, Promise<RunRecord>>();

export const Route = createFileRoute("/results")({
  validateSearch: (s) => searchSchema.parse(s),
  component: Results,
  head: () => ({
    meta: [
      { title: "VoxLens Research - 视频证据，可信研究" },
      { name: "description", content: "Citable social-video evidence research results." },
    ],
  }),
});

function Results() {
  const { t, lang } = useI18n();
  const { q, live, run } = Route.useSearch();
  const containerRef = useRef<HTMLDivElement>(null);
  const middleScrollRef = useRef<HTMLElement>(null);
  const sourcesListRef = useRef<HTMLDivElement>(null);
  const exportRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [activeFilter, setActiveFilter] = useState<"all" | PlatformId>("all");
  const [activeOutline, setActiveOutline] = useState<number>(0);
  const [highlightedSourceId, setHighlightedSourceId] = useState<string | null>(null);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [progress, setProgress] = useState(0);
  const [streamEvents, setStreamEvents] = useState<ResearchStreamEvent[]>([]);
  const [exportingImage, setExportingImage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pipelineExpanded, setPipelineExpanded] = useState(true);

  const handleStreamEvent = useCallback(
    (event: ResearchStreamEvent) => {
      setStreamEvents((items) => [...items.slice(-17), event]);
      if (typeof event.progress === "number") setProgress(event.progress);

      if (event.type === "run_started") {
        setReport(createDraftReport(event.query || q || "VoxLens", lang, event.runId, event.stages));
        return;
      }

      if (event.type === "stage" && Array.isArray(event.stages)) {
        setReport((current) => current ? {
          ...current,
          status: "running",
          ui: {
            ...(current.ui ?? createDraftUi()),
            stages: event.stages,
            progress: event.progress,
            activeStage: event.stageId,
          },
        } : current);
        return;
      }

      if (event.type === "sources") {
        setReport((current) => current ? mergeSourcesIntoReport(current, event.sources || []) : current);
        return;
      }

      if (event.type === "evidence") {
        setReport((current) => current ? mergeSourcesIntoReport(current, event.sources || [], true) : current);
        return;
      }

      if (event.type === "outline") {
        setReport((current) => current ? {
          ...current,
          outline: event.outline || current.outline,
          takeaways: event.takeaways || current.takeaways,
          insights: event.insights || current.insights,
          coverage: event.coverage || current.coverage,
          quality: event.quality || current.quality,
          warnings: event.warnings || current.warnings,
        } : current);
        return;
      }

      if (event.type === "report_patch") {
        setReport((current) => ({
          ...event.report,
          sources: event.report.sources?.length ? event.report.sources : (current?.sources ?? []),
          sections: current?.sections?.length ? current.sections : event.report.sections,
        }));
        return;
      }

      if (event.type === "section_started") {
        setReport((current) => current ? upsertSection(current, event.section) : current);
        return;
      }

      if (event.type === "section_delta") {
        setReport((current) => current ? appendSectionDelta(current, event.sectionId, event.delta) : current);
        return;
      }

      if (event.type === "section_complete") {
        setReport((current) => current ? upsertSection(current, event.section) : current);
        return;
      }

      if (event.type === "final_report") {
        setReport(event.report);
        setProgress(100);
        setStreaming(false);
        setLoading(false);
        return;
      }

      if (event.type === "error") {
        setError(event.message || "Stream failed");
        setStreaming(false);
        setLoading(false);
      }
    },
    [lang, q],
  );

  const loadReport = useCallback(
    async (forceLive = false) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setLoading(true);
      setStreaming(Boolean(q));
      setProgress(0);
      setStreamEvents([]);
      setError(null);
      try {
        if (run) {
          const existing = await getResearchRun(run);
          if (existing.report) {
            setReport(existing.report);
            setProgress(existing.progress || 100);
          } else {
            setReport(createDraftReport(existing.request.query || existing.request.need || "VoxLens", existing.request.lang ?? lang, existing.runId));
            setProgress(existing.progress || 0);
          }
          await streamResearchRun(run, handleStreamEvent, controller.signal);
          return;
        }

        if (!q) {
          const data = await getDemoReport(lang);
          setReport(data);
          setProgress(100);
          return;
        }

        const liveFlag = (live ?? "").replace(/^"+|"+$/g, "").toLowerCase();
        const shouldUseCrawlerRuntime = liveFlag !== "0" && liveFlag !== "false";
        const payload = {
            need: q,
            query: q,
            platforms: DEFAULT_RESEARCH_PLATFORMS,
            limitPerPlatform: forceLive ? 20 : 12,
            commentsPerVideo: forceLive ? 16 : 8,
            detailVideosPerPlatform: forceLive ? 4 : 2,
            maxParallelPlatforms: forceLive ? 4 : 3,
            maxParallelVideos: forceLive ? 4 : 3,
            useLiveProviders: true,
            useCrawlerRuntime: shouldUseCrawlerRuntime,
            providerMode: "local" as const,
            authMode: "auto" as const,
            includeTranscripts: true,
            minLiveSources: 3,
            lang,
          };
        setReport(createDraftReport(q, lang));
        const cacheKey = `${q}|${lang}|${liveFlag || "1"}|${forceLive ? "force" : "normal"}`;
        let pendingRun = runCreationCache.get(cacheKey);
        if (!pendingRun || forceLive) {
          pendingRun = createResearchRun(payload);
          runCreationCache.set(cacheKey, pendingRun);
        }
        const created = await pendingRun;
        if (typeof window !== "undefined") {
          const params = new URLSearchParams(window.location.search);
          params.set("q", q);
          params.set("run", created.runId);
          params.set("live", liveFlag || "1");
          window.history.replaceState(null, "", `/results?${params.toString()}`);
        }
        await streamResearchRun(created.runId, handleStreamEvent, controller.signal);
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          try {
            const data = q
              ? await runResearch({
                need: q,
                query: q,
                platforms: DEFAULT_RESEARCH_PLATFORMS,
                limitPerPlatform: 8,
                commentsPerVideo: 6,
                detailVideosPerPlatform: 1,
                useLiveProviders: true,
                useCrawlerRuntime: true,
                providerMode: "local",
                minLiveSources: 2,
                lang,
              })
              : await getDemoReport(lang);
            setReport(data);
            setProgress(100);
          } catch (fallbackErr) {
            setError(fallbackErr instanceof Error ? fallbackErr.message : String(fallbackErr));
          }
        }
      } finally {
        setLoading(false);
        setStreaming(false);
      }
    },
    [handleStreamEvent, lang, live, q, run],
  );

  useEffect(() => {
    void loadReport(false);
  }, [loadReport]);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    setActiveOutline(0);
    setHighlightedSourceId(null);
  }, [report]);

  useEffect(() => {
    const bodyOverflow = document.body.style.overflow;
    const htmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = bodyOverflow;
      document.documentElement.style.overflow = htmlOverflow;
    };
  }, []);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.from("[data-rise]", {
        y: 18,
        opacity: 0,
        duration: 0.7,
        ease: "power3.out",
        stagger: 0.06,
      });
    }, containerRef);
    return () => ctx.revert();
  }, [report]);

  const filteredSources = useMemo(() => {
    if (!report) return [];
    return activeFilter === "all" ? report.sources : report.sources.filter((s) => s.platform === activeFilter);
  }, [activeFilter, report]);

  const title = report?.title || q || "VoxLens";
  const isWorking = loading || streaming || report?.status === "running";
  const visibleOutline = report?.outline ?? [];

  useEffect(() => {
    if (!highlightedSourceId) return;
    const sourceCard = containerRef.current?.querySelector<HTMLElement>(`[data-source-id="${highlightedSourceId}"]`);
    sourceCard?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightedSourceId, filteredSources]);

  const handleOutlineClick = (sectionId: string, index: number) => {
    setActiveOutline(index);
    const container = middleScrollRef.current;
    const target = document.getElementById(sectionId);
    if (!container || !target) return;
    const containerRect = container.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    container.scrollTo({
      top: container.scrollTop + targetRect.top - containerRect.top - 8,
      behavior: "smooth",
    });
  };

  const handleReportScroll = () => {
    const container = middleScrollRef.current;
    if (!container || !report?.sections.length) return;
    const threshold = container.getBoundingClientRect().top + 80;
    let next = 0;
    report.sections.forEach((section, index) => {
      const node = document.getElementById(section.id);
      if (node && node.getBoundingClientRect().top <= threshold) {
        next = index;
      }
    });
    setActiveOutline((current) => (current === next ? current : next));
  };

  const handleCitationHover = (sourceId: number | string | null) => {
    setHighlightedSourceId(sourceId == null ? null : String(sourceId));
  };

  const handleSourceFilterChange = (filter: "all" | PlatformId) => {
    setActiveFilter(filter);
    window.requestAnimationFrame(() => {
      sourcesListRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    });
  };

  const exportReportImage = async () => {
    if (!report || typeof window === "undefined" || !exportRef.current) return;
    setExportingImage(true);
    try {
      await document.fonts?.ready;
      const node = exportRef.current;
      const pixelRatio = node.offsetHeight > 9000 ? 1.15 : 1.55;
      const dataUrl = await toPng(node, {
        backgroundColor: "#fbf7ff",
        cacheBust: true,
        imagePlaceholder: "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==",
        pixelRatio,
        skipFonts: true,
      });
      const link = document.createElement("a");
      link.href = dataUrl;
      link.download = `${imageFileName(report.title || title)}.png`;
      link.click();
    } finally {
      setExportingImage(false);
    }
  };

  return (
    <div ref={containerRef} className="results-shell relative h-screen overflow-hidden">
      <header className="flex h-[72px] shrink-0 items-center justify-between px-6 py-5 sm:px-10">
        <div className="flex items-center gap-4">
          <BrandMark />
          <span className="h-5 w-px bg-border" />
          <span className="text-sm font-medium text-muted-foreground">{t("research_title")}</span>
        </div>
        <div className="flex items-center gap-2">
          <LangToggle />
          <button
            type="button"
            onClick={() => void loadReport(true)}
            disabled={isWorking}
            className="glass inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-xs font-medium transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isWorking ? "animate-spin" : ""}`} style={{ color: "var(--violet)" }} />
            {t("re_research")}
          </button>
          <button
            type="button"
            onClick={() => void exportReportImage()}
            disabled={!report || exportingImage}
            aria-label="download report image"
            className="glass grid h-9 w-9 place-items-center rounded-full transition hover:-translate-y-0.5 disabled:cursor-wait disabled:opacity-60"
          >
            <Download className={`h-4 w-4 ${exportingImage ? "animate-bounce" : ""}`} />
          </button>
        </div>
      </header>

      {loading && !report && (
        <div className="mx-auto mt-20 max-w-md px-6 text-center">
          <div className="glass rounded-3xl p-8" style={{ boxShadow: "var(--shadow-glass)" }}>
            <Sparkles className="mx-auto h-8 w-8 animate-pulse" style={{ color: "var(--violet)" }} />
            <p className="mt-4 text-sm text-muted-foreground">{t("loading")}</p>
          </div>
        </div>
      )}

      {!report && error && (
        <div className="mx-auto mt-20 max-w-md px-6 text-center">
          <div className="glass rounded-3xl p-8" style={{ boxShadow: "var(--shadow-glass)" }}>
            <h1 className="text-lg font-semibold">{t("error_title")}</h1>
            <p className="mt-3 text-xs text-muted-foreground">{error}</p>
            <button
              type="button"
              onClick={() => void loadReport(false)}
              className="mt-5 rounded-full bg-primary px-5 py-2 text-sm text-primary-foreground"
            >
              {t("retry")}
            </button>
          </div>
        </div>
      )}

      {report && (
        <div className="mx-auto grid h-[calc(100vh-4.5rem)] w-full max-w-[1400px] gap-6 overflow-hidden px-6 sm:px-10 lg:grid-cols-[260px_minmax(0,1fr)_340px]">
          <aside data-rise className="space-y-6 lg:self-start">
            <div>
              <div className="mb-3 inline-flex rounded-full bg-white/60 px-3 py-1 text-[11px] font-medium text-muted-foreground ring-1 ring-black/5">
                {isWorking ? `${t("streaming_badge")} ${progress}%` : report.isDemoFallback ? t("demo_badge") : report.status === "partial" ? t("partial_badge") : t("live_badge")}
              </div>
              <h1 className="font-display text-3xl font-normal italic leading-[1.05] tracking-tight sm:text-4xl">
                {title}
              </h1>
            </div>

            <div className="glass rounded-2xl p-4" style={{ boxShadow: "var(--shadow-glass)" }}>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                {t("outline")}
              </p>
              <ul className="mt-3 space-y-1">
                {visibleOutline.map((item, i) => {
                  const active = activeOutline === i;
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => handleOutlineClick(item.id, i)}
                        className={`group flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left text-sm transition ${
                          active ? "bg-white/70 font-medium text-foreground" : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        <span
                          className={`h-4 w-[2px] rounded-full transition ${active ? "" : "bg-transparent"}`}
                          style={active ? { background: "linear-gradient(180deg, var(--violet), var(--indigo))" } : undefined}
                        />
                        <span className="text-[11px] tabular-nums text-muted-foreground/70">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <span className="truncate">{item.label}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="px-1 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{report.totalVideos}</span> {t("videos")} /{" "}
              <span className="font-medium text-foreground">{report.platforms.filter((p) => p.count > 0).length}</span>{" "}
              {t("platforms")} / <span className="font-medium text-foreground">{report.totalComments}</span>{" "}
              {t("comments")}
            </div>

          </aside>

          <section
            ref={middleScrollRef}
            data-rise
            data-lenis-prevent
            onScroll={handleReportScroll}
            className="scroll-col space-y-6 lg:self-start"
          >
            <div className="glass rounded-2xl p-5" style={{ boxShadow: "var(--shadow-glass)" }}>
              <ProgressPanel
                report={report}
                events={streamEvents}
                streaming={isWorking}
                progress={progress}
                lang={lang}
                expanded={pipelineExpanded}
                onExpandedChange={setPipelineExpanded}
              />

              <InsightStrip report={report} lang={lang} onCitationHover={handleCitationHover} />

              <div className="mt-6 border-t border-white/40 pt-5">
                <h3 className="text-sm font-semibold">{t("key_takeaways")}</h3>
                <ul className="mt-3 space-y-2 text-sm text-foreground/85">
                  {report.takeaways.map((item, i) => (
                    <li key={`${item.text}-${i}`} className="flex gap-2">
                      <span
                        className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
                        style={{ background: "linear-gradient(135deg, var(--violet), var(--indigo))" }}
                      />
                      <span>
                        {item.text} <CitationList ids={item.citations} onHover={handleCitationHover} />
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <article className="space-y-7">
              {report.sections.length === 0 && (
                <div className="glass rounded-2xl p-6 text-sm text-muted-foreground" style={{ boxShadow: "var(--shadow-glass)" }}>
                  {isWorking ? t("streaming_report") : t("empty_report")}
                </div>
              )}
              {report.sections.map((section) => (
                <section key={section.id} id={section.id} className="space-y-4">
                  <h2 className="text-xl font-bold tracking-tight">{section.title}</h2>
                  {section.body && (
                    <p className="text-[15px] leading-relaxed text-foreground/85">
                      {section.body} <CitationList ids={section.sourceIds ?? []} onHover={handleCitationHover} />
                    </p>
                  )}
                  {section.bullets.length > 0 && (
                    <ul className="space-y-2 text-sm text-foreground/85">
                      {section.bullets.map((item, i) => (
                        <li key={`${section.id}-${i}`} className="flex gap-2">
                          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-foreground/40" />
                          <span>{item.text} <CitationList ids={item.citations} onHover={handleCitationHover} /></span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {section.quote && <QuoteCard quote={section.quote} source={report.sources.find((s) => s.id === section.quote?.sourceId)} />}
                  {section.table.length > 0 && <ComparisonTable rows={section.table} onCitationHover={handleCitationHover} />}
                </section>
              ))}
            </article>
          </section>

          <aside data-rise data-lenis-prevent className="sources-panel lg:self-start">
            <div className="sources-panel-head">
              <div className="flex items-center justify-between px-1">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  {t("sources")} / {report.sources.length}
                </p>
                <span className="rounded-full bg-white/65 px-2.5 py-1 text-[10px] font-medium text-muted-foreground ring-1 ring-white/70">
                  {filteredSources.length}
                </span>
              </div>

              <PlatformLogoStrip
                platforms={report.platforms}
                activeFilter={activeFilter}
                onSelect={handleSourceFilterChange}
                allLabel={t("all")}
                videoLabel={t("videos")}
              />
            </div>

            <div ref={sourcesListRef} className="sources-list glass rounded-2xl p-3" style={{ boxShadow: "var(--shadow-glass)" }}>
              {filteredSources.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">{t("empty")}</p>
              ) : (
                <ul className="space-y-3">
                  {filteredSources.map((source) => (
                    <SourceItem
                      key={`${source.platform}-${source.id}-${source.url}`}
                      source={source}
                      highlighted={highlightedSourceId === String(source.id)}
                    />
                  ))}
                </ul>
              )}
            </div>
          </aside>
        </div>
      )}

      <div className="results-followup pointer-events-none">
        <form
          onSubmit={(e) => e.preventDefault()}
          className="followup-float search-shell glass pointer-events-auto flex w-full items-center gap-3 rounded-full px-3 py-2.5 pl-5"
        >
          <span
            className="inline-flex items-center rounded-full px-3 py-1.5 text-xs font-medium text-white"
            style={{ background: "linear-gradient(135deg, var(--violet), var(--indigo))" }}
          >
            {t("follow_up")}
          </span>
          <input
            placeholder={t("follow_up_ph")}
            className="min-w-0 flex-1 bg-transparent text-sm placeholder:text-muted-foreground/80 focus:outline-none"
          />
          <button
            type="submit"
            aria-label="web search"
            className="search-submit search-icon-button grid h-9 shrink-0 place-items-center"
          >
            <WebSearchIcon className="h-5 w-5" />
          </button>
        </form>
      </div>

      <div className="sr-only">{lang}</div>
      {report && (
        <div className="fixed left-[-10000px] top-0 w-[1120px] overflow-visible" aria-hidden="true">
          <div ref={exportRef}>
            <ReportExportSheet report={report} title={title} />
          </div>
        </div>
      )}
      <Link to="/" className="hidden">home</Link>
    </div>
  );
}

function ReportExportSheet({ report, title }: { report: ResearchReport; title: string }) {
  const activePlatforms = report.platforms.filter((platform) => platform.count > 0);
  const insights = report.insights ?? [];
  const exportSources = selectExportSources(report.sources);
  const omittedSources = Math.max(0, report.sources.length - exportSources.length);
  const generatedAt = formatReportDate(report.generatedAt, report.lang);
  return (
    <div className="w-[1120px] overflow-hidden rounded-[36px] bg-[#fbf7ff] p-12 text-[#1f1930] shadow-[0_28px_100px_-46px_rgba(126,93,255,0.5)]">
      <div className="rounded-[30px] border border-white/75 bg-white/70 p-9 shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]">
        <div className="flex items-start justify-between gap-8">
          <div className="flex items-center gap-4">
            <span className="grid h-16 w-16 place-items-center rounded-[24px] bg-white shadow-[0_18px_45px_-28px_rgba(121,91,255,0.9)] ring-1 ring-black/5">
              <img src="/brand/voxlens-mark.svg" alt="" width={56} height={56} className="h-14 w-14" />
            </span>
            <div>
              <p className="text-2xl font-bold tracking-tight">{report.productName || "VoxLens"}</p>
              <p className="mt-1 text-sm font-medium uppercase tracking-[0.18em] text-[#7f7595]">
                {report.slogan || (report.lang === "zh" ? "视频证据，可信研究" : "Citable social-video research")}
              </p>
            </div>
          </div>
          <div className="text-right text-xs leading-relaxed text-[#7f7595]">
            <p>{generatedAt}</p>
            <p className="mt-1 font-semibold text-[#1f1930]">{report.status}</p>
          </div>
        </div>

        <div className="mt-10 grid grid-cols-[1fr_280px] gap-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8a7a99]">Research Report</p>
            <h1 className="mt-3 font-display text-5xl font-normal italic leading-[0.98] tracking-tight text-[#151020]">
              {title}
            </h1>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <ExportMetric label="Sources" value={report.totalVideos || report.sources.length} />
            <ExportMetric label="Comments" value={report.totalComments} />
            <ExportMetric label="Platforms" value={activePlatforms.length} />
            <ExportMetric label="Cited" value={report.coverage?.citedSources ?? report.sources.filter((source) => (source.citationCount ?? 0) > 0).length} />
          </div>
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-2 border-y border-[#ebe3f2] py-4">
          {activePlatforms.map((platform) => (
            <span key={platform.id} className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-[#332b44] ring-1 ring-[#eadff2]">
              <PlatformLogoImage platform={platform.id} size={18} />
              {platform.name}
              <span className="text-[#8a7a99]">{platform.count}</span>
            </span>
          ))}
        </div>

        {report.takeaways.length > 0 && (
          <div className="mt-9 rounded-[24px] bg-[#f2edf8] p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#7f7595]">Key Takeaways</p>
            <div className="mt-4 grid gap-3">
              {report.takeaways.map((item, index) => (
                <p key={`${item.text}-${index}`} className="text-[15px] leading-relaxed text-[#342b44]">
                  <span className="mr-2 font-semibold text-[#8c63ff]">{String(index + 1).padStart(2, "0")}</span>
                  {item.text} <ExportCitations ids={item.citations} />
                </p>
              ))}
            </div>
          </div>
        )}

        {insights.length > 0 && (
          <div className="mt-7 grid grid-cols-3 gap-4">
            {insights.slice(0, 3).map((insight) => (
              <div key={insight.id} className="rounded-[22px] bg-white/80 p-5 ring-1 ring-[#eadff2]">
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-[10px] font-semibold uppercase tracking-[0.16em] text-[#8a7a99]">{insight.kind || "insight"}</p>
                  <span className="rounded-full bg-[#f2edf8] px-2 py-0.5 text-[10px] font-bold">{insight.confidence ?? 3}/5</span>
                </div>
                <p className="mt-3 text-base font-bold leading-snug">{insight.label}</p>
                {insight.summary && (
                  <p className="mt-2 text-xs leading-relaxed text-[#625772]">
                    {insight.summary} <ExportCitations ids={insight.sourceIds ?? []} />
                  </p>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="mt-10 space-y-8">
          {report.sections.map((section, index) => (
            <section key={section.id} className="rounded-[26px] bg-white/78 p-7 ring-1 ring-[#eadff2]">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8a7a99]">
                Section {String(index + 1).padStart(2, "0")}
              </p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight">{section.title}</h2>
              {section.body && (
                <p className="mt-4 text-[15px] leading-relaxed text-[#3a304c]">
                  {section.body} <ExportCitations ids={section.sourceIds ?? []} />
                </p>
              )}
              {section.bullets.length > 0 && (
                <div className="mt-4 grid gap-2">
                  {section.bullets.map((item, bulletIndex) => (
                    <p key={`${section.id}-${bulletIndex}`} className="text-sm leading-relaxed text-[#3a304c]">
                      <span className="mr-2 text-[#8c63ff]">•</span>
                      {item.text} <ExportCitations ids={item.citations} />
                    </p>
                  ))}
                </div>
              )}
              {section.quote && (
                <div className="mt-5 rounded-2xl bg-[#f2edf8] p-5">
                  <p className="text-base italic leading-relaxed text-[#2a2139]">"{section.quote.quote}"</p>
                  <p className="mt-2 text-xs font-semibold text-[#7f7595]">{section.quote.author}</p>
                </div>
              )}
              {section.table.length > 0 && <ExportComparisonTable rows={section.table} />}
            </section>
          ))}
        </div>

        {exportSources.length > 0 && (
          <div className="mt-10">
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8a7a99]">Evidence Sources</p>
                <h2 className="mt-2 text-2xl font-bold tracking-tight">{exportSources.length} featured sources</h2>
                {omittedSources > 0 && (
                  <p className="mt-1 text-xs text-[#8a7a99]">
                    {omittedSources} additional sources are summarized in the analysis and omitted from this image.
                  </p>
                )}
              </div>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-4">
              {exportSources.map((source) => (
                <div key={`${source.platform}-${source.id}-${source.url}`} className="overflow-hidden rounded-[20px] bg-white/82 ring-1 ring-[#eadff2]">
                  <div className="relative aspect-video bg-[#f2edf8]">
                    <img
                      src={exportSourceCover(source)}
                      alt=""
                      crossOrigin="anonymous"
                      className="h-full w-full object-cover"
                    />
                    <span className="absolute left-3 top-3 grid h-8 w-8 place-items-center rounded-full bg-white/88 shadow-sm ring-1 ring-black/5">
                      <PlatformLogoImage platform={source.platform} size={20} />
                    </span>
                  </div>
                  <div className="p-4">
                  <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a7a99]">
                    <span>#{source.id}</span>
                    <span>{platformName(source.platform)}</span>
                    {source.provider && <span>{source.provider}</span>}
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm font-bold leading-snug text-[#21182e]">{source.title}</p>
                  <p className="mt-1 text-xs text-[#6d617d]">{source.creator || source.author || source.platform}</p>
                  {sourceTeaser(source) && <p className="mt-2 text-xs leading-relaxed text-[#625772]">{sourceTeaser(source)}</p>}
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {(source.badges ?? []).slice(0, 3).map((badge) => (
                      <span key={badge} className="rounded-full bg-[#f4eef9] px-2 py-0.5 text-[10px] font-semibold text-[#6d617d]">
                        {badge}
                      </span>
                    ))}
                    {Boolean(source.citationCount) && (
                      <span className="rounded-full bg-[#8c63ff] px-2 py-0.5 text-[10px] font-bold text-white">
                        cited x{source.citationCount}
                      </span>
                    )}
                  </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-10 flex items-center justify-between border-t border-[#ebe3f2] pt-6 text-xs text-[#8a7a99]">
          <span>{report.productName || "VoxLens"} · {report.slogan || "Citable social-video research"}</span>
          <span>{report.runId || "local-report"}</span>
        </div>
      </div>
    </div>
  );
}

function ExportMetric({ label, value }: { label: string; value?: number }) {
  return (
    <div className="rounded-[18px] bg-white px-4 py-3 ring-1 ring-[#eadff2]">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a7a99]">{label}</p>
      <p className="mt-1 text-2xl font-bold text-[#171020]">{value ?? 0}</p>
    </div>
  );
}

function ExportCitations({ ids }: { ids: Array<number | string> }) {
  if (!ids.length) return null;
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-baseline text-[10px] font-bold text-[#8c63ff]">
      {ids.map((id) => <span key={id}>[{id}]</span>)}
    </span>
  );
}

function ExportComparisonTable({ rows }: { rows: ResearchReport["sections"][number]["table"] }) {
  return (
    <table className="mt-5 w-full overflow-hidden rounded-2xl text-left text-xs">
      <thead className="bg-[#f2edf8] text-[10px] uppercase tracking-[0.14em] text-[#7f7595]">
        <tr>
          <th className="px-3 py-2 font-semibold">Signal</th>
          <th className="px-3 py-2 font-semibold">Support</th>
          <th className="px-3 py-2 font-semibold">Risk</th>
          <th className="px-3 py-2 font-semibold">Freshness</th>
          <th className="px-3 py-2 font-semibold">Confidence</th>
          <th className="px-3 py-2 font-semibold">Evidence</th>
        </tr>
      </thead>
      <tbody className="bg-white/70">
        {rows.map((row) => (
          <tr key={row.name} className="border-t border-[#eadff2]">
            <td className="px-3 py-3 font-semibold text-[#21182e]">{row.name}</td>
            <td className="px-3 py-3"><Stars n={row.support ?? row.lowLight} /></td>
            <td className="px-3 py-3"><Stars n={row.risk ?? Math.max(1, 6 - row.video)} /></td>
            <td className="px-3 py-3"><Stars n={row.freshness ?? row.battery} /></td>
            <td className="px-3 py-3"><Stars n={row.confidence ?? row.camera} /></td>
            <td className="px-3 py-3"><ExportCitations ids={row.evidence} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function selectExportSources(sources: Source[]) {
  const withCover = sources.filter((source) => Boolean(source.thumbnail?.trim()));
  const withoutCover = sources.filter((source) => !source.thumbnail?.trim());
  return [...withCover, ...withoutCover].slice(0, 4);
}

function exportSourceCover(source: Source) {
  return source.thumbnail?.trim() || fallbackThumb(source.platform);
}

function CitationList({ ids, onHover }: { ids: Array<number | string>; onHover?: (sourceId: number | string | null) => void }) {
  if (!ids.length) return null;
  return (
    <>
      {ids.map((id) => (
        <sup key={id} className="ml-0.5">
          <button
            type="button"
            className="citation-chip"
            onPointerEnter={() => onHover?.(id)}
            onPointerLeave={() => onHover?.(null)}
            onMouseEnter={() => onHover?.(id)}
            onMouseLeave={() => onHover?.(null)}
            onMouseOver={() => onHover?.(id)}
            onMouseOut={() => onHover?.(null)}
            onClick={() => onHover?.(id)}
            onFocus={() => onHover?.(id)}
            onFocusCapture={() => onHover?.(id)}
            onBlur={() => onHover?.(null)}
          >
            [{id}]
          </button>
        </sup>
      ))}
    </>
  );
}

function InsightStrip({
  report,
  lang,
  onCitationHover,
}: {
  report: ResearchReport;
  lang: Lang;
  onCitationHover?: (sourceId: number | string | null) => void;
}) {
  const insights = report.insights ?? [];
  const coverage = report.coverage;
  const quality = report.quality;
  const cardCount = Math.min(insights.length, 6) + (coverage ? 1 : 0);
  const railRef = useAutoCarousel<HTMLDivElement>(cardCount, 4200);
  if (!insights.length && !coverage && !quality) return null;

  return (
    <div className="mt-5">
      <div className="carousel-shell">
        <div ref={railRef} className="core-carousel" aria-label="research highlights">
          {insights.slice(0, 6).map((insight) => (
            <div key={insight.id} data-carousel-card className="insight-slide-card">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  {formatInsightKind(insight.kind, lang)}
                </span>
                <span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-semibold text-foreground">
                  {insight.confidence ?? 3}/5
                </span>
              </div>
              <p className="mt-2 text-base font-semibold leading-snug">{insight.label}</p>
              {insight.summary && (
                <p className="mt-2 insight-slide-copy text-xs leading-relaxed text-foreground/70">
                  {insight.summary} <CitationList ids={insight.sourceIds ?? []} onHover={onCitationHover} />
                </p>
              )}
            </div>
          ))}
          {coverage && (
            <div data-carousel-card className="coverage-slide-card text-xs">
              <p className="font-semibold uppercase tracking-[0.14em] text-muted-foreground">{resultCopy(lang, "coverage")}</p>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <MetricPill label={resultCopy(lang, "sources")} value={coverage.totalSources} />
                <MetricPill label={resultCopy(lang, "comments")} value={coverage.totalComments} />
                <MetricPill label={resultCopy(lang, "platforms")} value={coverage.platformCount} />
                <MetricPill label={resultCopy(lang, "cited")} value={coverage.citedSources} />
              </div>
              {quality && (
                <div className="mt-2 rounded-xl bg-white/55 px-2.5 py-2 ring-1 ring-white/60">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] text-muted-foreground">{resultCopy(lang, "quality")}</span>
                    <span className="text-sm font-semibold">{quality.overall}/100</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[10px] text-muted-foreground">
                    {resultCopy(lang, "evidence")} {quality.evidenceStrength?.score ?? 0} · {resultCopy(lang, "citations")} {quality.citationAccuracy?.score ?? 0} · {resultCopy(lang, "risk")} {formatRiskLabel(quality.conclusionRisk?.label, lang)}
                  </p>
                </div>
              )}
            </div>
            )}
          </div>
        <CarouselHints targetRef={railRef} count={cardCount} />
      </div>
    </div>
  );
}

function MetricPill({ label, value }: { label: string; value?: number }) {
  return (
    <div className="rounded-xl bg-white/55 px-2.5 py-2 ring-1 ring-white/60">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold">{value ?? 0}</div>
    </div>
  );
}

function PlatformLogoStrip({
  platforms,
  activeFilter,
  onSelect,
  allLabel,
  videoLabel,
}: {
  platforms: ResearchReport["platforms"];
  activeFilter: "all" | PlatformId;
  onSelect: (filter: "all" | PlatformId) => void;
  allLabel: string;
  videoLabel: string;
}) {
  return (
    <div className="sources-platform-filter">
      <div className="platform-logo-strip">
        {platforms.map((platform) => {
          const hasSources = platform.count > 0;
          const active = activeFilter === platform.id;
          return (
            <button
              key={platform.id}
              type="button"
              data-active={active}
              title={`${platform.name} · ${platform.count} ${videoLabel}${active ? ` · ${allLabel}` : ""}`}
              aria-label={`${platform.name}, ${platform.count} ${videoLabel}${active ? `, ${allLabel}` : ""}`}
              aria-pressed={active}
              onClick={() => onSelect(active ? "all" : platform.id)}
              className={`group relative grid h-9 w-9 place-items-center rounded-xl transition duration-200 hover:-translate-y-0.5 hover:bg-white/70 hover:opacity-100 ${
                hasSources ? "opacity-95" : "opacity-35 grayscale"
              }`}
            >
              <PlatformLogoImage platform={platform.id} size={22} />
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ProgressPanel({
  report,
  events,
  streaming,
  progress,
  lang,
  expanded,
  onExpandedChange,
}: {
  report: ResearchReport;
  events: ResearchStreamEvent[];
  streaming: boolean;
  progress: number;
  lang: Lang;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
}) {
  const stages = report.ui?.stages ?? [];
  const lastMessage = [...events].reverse().find((event) => event.message)?.message;
  const warnings = report.warnings ?? [];
  const percent = Math.max(progress, report.ui?.progress ?? 0);
  const isComplete = !streaming && report.status !== "running" && percent >= 100;
  const summary = localizePipelineMessage(
    lastMessage || report.ui?.interactionHints?.citations || (isComplete ? "DeepResearch report completed." : ""),
    lang,
  );
  if (!streaming && !warnings.length && !stages.length) return null;

  return (
    <div className="progress-panel mb-5 rounded-2xl bg-white/45 p-4 ring-1 ring-white/50" data-expanded={expanded}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            {resultCopy(lang, "deepResearchPipeline")}
          </p>
          <p className="mt-1 text-sm text-foreground/80">
            {summary || resultCopy(lang, "waitingForBackend")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-white/70 px-3 py-1 text-xs font-semibold text-foreground ring-1 ring-black/5">
            {percent}%
          </span>
          <button
            type="button"
            aria-expanded={expanded}
            onClick={() => onExpandedChange(!expanded)}
            className="pipeline-toggle"
          >
            <span>{expanded ? resultCopy(lang, "collapse") : resultCopy(lang, "expand")}</span>
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
      {expanded && (
        <>
          {!isComplete && (
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/60">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${percent}%`, background: "linear-gradient(90deg, var(--violet), var(--indigo))" }}
              />
            </div>
          )}
          {stages.length > 0 && !isComplete && <StageGrid stages={stages} lang={lang} />}
          <ProviderActivityList events={events} warnings={warnings} platforms={report.platforms} lang={lang} />
        </>
      )}
    </div>
  );
}

function StageGrid({ stages, lang }: { stages: ResearchStage[]; lang: Lang }) {
  return (
    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
      {stages.map((stage) => (
        <div key={stage.id} className="rounded-xl bg-white/50 px-3 py-2 text-xs ring-1 ring-white/60">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-medium">{formatStageLabel(stage, lang)}</span>
            <span className={`h-2 w-2 shrink-0 rounded-full ${statusClass(stage.status)}`} />
          </div>
          <div className="mt-1 text-[10px] text-muted-foreground">{stage.progress}%</div>
        </div>
      ))}
    </div>
  );
}

function useAutoCarousel<T extends HTMLElement>(itemCount: number, intervalMs: number) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (itemCount < 2) return;
    const timer = window.setInterval(() => {
      const node = ref.current;
      if (!node || node.scrollWidth <= node.clientWidth) return;
      const firstCard = node.querySelector<HTMLElement>("[data-carousel-card]");
      const step = (firstCard?.offsetWidth ?? node.clientWidth * 0.72) + 12;
      const reachedEnd = node.scrollLeft + node.clientWidth >= node.scrollWidth - 8;
      node.scrollTo({ left: reachedEnd ? 0 : node.scrollLeft + step, behavior: "smooth" });
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs, itemCount]);
  return ref;
}

function CarouselHints({ targetRef, count }: { targetRef: { current: HTMLElement | null }; count: number }) {
  if (count < 2) return null;
  const move = (direction: -1 | 1) => {
    const node = targetRef.current;
    if (!node) return;
    node.scrollBy({ left: direction * node.clientWidth * 0.72, behavior: "smooth" });
  };
  return (
    <div className="carousel-controls">
      <button type="button" onClick={() => move(-1)} className="carousel-nudge" aria-label="previous cards">‹</button>
      <button type="button" onClick={() => move(1)} className="carousel-nudge" aria-label="next cards">›</button>
    </div>
  );
}

type ProviderActivity = {
  key: string;
  platform: string;
  provider: string;
  status: "running" | "completed" | "failed" | "partial";
  count: number;
  message: string;
};

function ProviderActivityList({
  events,
  warnings,
  platforms,
  lang,
}: {
  events: ResearchStreamEvent[];
  warnings: string[];
  platforms: ResearchReport["platforms"];
  lang: Lang;
}) {
  const activities = providerActivities(events);
  const latestEvent = [...events].reverse().find((event) => event.message);
  const failedPlatforms = failedPlatformsFromWarnings(warnings, platforms);

  if (!activities.length && !latestEvent && !failedPlatforms.length) return null;

  return (
    <div className="mt-3 rounded-2xl bg-white/35 px-3 py-2.5 ring-1 ring-white/55">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{resultCopy(lang, "backend")}</span>
        {latestEvent && (
          <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
            <span className="font-semibold text-foreground/70">{formatEventType(latestEvent.type, lang)}</span> · {localizePipelineMessage(latestEvent.message, lang)}
          </span>
        )}
        {failedPlatforms.map((item) => (
          <span
            key={item.platform}
            title={item.message}
            className="inline-grid h-5 w-5 place-items-center rounded-full bg-white/65 opacity-45 grayscale ring-1 ring-black/5"
          >
            <PlatformLogoImage platform={item.platform} size={14} alt={item.platform} />
          </span>
        ))}
        {activities.slice(0, 8).map((item) => (
          <span
            key={item.key}
            title={`${platformName(item.platform)} · ${item.provider}: ${item.message || item.status}`}
            className={`h-2.5 w-2.5 shrink-0 rounded-full ${activityStatusClass(item.status)}`}
          />
        ))}
      </div>
    </div>
  );
}

function failedPlatformsFromWarnings(warnings: string[], platforms: ResearchReport["platforms"]) {
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

function providerActivities(events: ResearchStreamEvent[]): ProviderActivity[] {
  const byKey = new Map<string, ProviderActivity>();
  for (const event of events) {
    if (event.type !== "provider_started" && event.type !== "sources") continue;
    const target = event.target as { platform?: string; provider?: string } | undefined;
    const log = event.type === "sources" ? event.log : undefined;
    const platform = target?.platform || String(log?.platform || "unknown");
    const provider = target?.provider || String(log?.provider || "provider");
    const key = `${platform}:${provider}`;
    const count = typeof log?.count === "number" ? log.count : Array.isArray(event.sources) ? event.sources.length : 0;
    const ok = typeof log?.ok === "boolean" ? log.ok : true;
    byKey.set(key, {
      key,
      platform,
      provider,
      status: event.type === "provider_started" ? "running" : ok ? "completed" : count > 0 ? "partial" : "failed",
      count,
      message: event.message || String(log?.note || ""),
    });
  }
  return Array.from(byKey.values()).sort((a, b) => a.platform.localeCompare(b.platform));
}

function activityStatusClass(status: ProviderActivity["status"]) {
  if (status === "completed") return "bg-emerald-400";
  if (status === "failed") return "bg-red-400";
  if (status === "partial") return "bg-amber-400";
  return "animate-pulse bg-[color:var(--violet)]";
}

function platformName(platform: string) {
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

type ResultCopyKey = keyof typeof RESULT_COPY.en;

function resultCopy(lang: Lang, key: ResultCopyKey) {
  return RESULT_COPY[lang][key];
}

function formatStageLabel(stage: ResearchStage, lang: Lang) {
  const labels: Record<string, Record<Lang, string>> = {
    plan: { en: "Plan query", zh: "规划问题" },
    search: { en: "Search sources", zh: "搜索来源" },
    evidence: { en: "Structure evidence", zh: "整理证据" },
    synthesis: { en: "Synthesize report", zh: "生成报告" },
  };
  return labels[stage.id]?.[lang] || stage.label;
}

function formatInsightKind(kind: string | undefined, lang: Lang) {
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

function formatRiskLabel(label: string | undefined, lang: Lang) {
  if (!label) return resultCopy(lang, "notAvailable");
  if (lang === "en") return label;
  const normalized = label.toLowerCase();
  if (normalized.includes("low")) return "低";
  if (normalized.includes("medium") || normalized.includes("moderate")) return "中";
  if (normalized.includes("high")) return "高";
  return label;
}

function formatEventType(type: string, lang: Lang) {
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

function localizePipelineMessage(message: string | undefined, lang: Lang) {
  const text = (message || "").trim();
  if (!text) return "";
  if (lang === "en" || /[\u4e00-\u9fff]/u.test(text)) return text;

  const exact: Record<string, string> = {
    "DeepResearch run started.": "DeepResearch 任务已启动。",
    "DeepResearch report completed.": "DeepResearch 报告已完成。",
    completed: "已完成。",
    "Outline and takeaways are ready.": "大纲和核心结论已生成。",
    "Report shell is ready; streaming sections next.": "报告框架已生成，正在流式输出正文。",
    "Generated report outline, takeaways, source metadata and streamable sections.": "已生成报告大纲、核心结论、来源元数据和可流式输出的章节。",
    "Generated report sections, takeaways, comparison table and source citations.": "已生成报告章节、核心结论、对比表和来源引用。",
    "Live providers disabled; returned a query-specific planning report without factual claims.": "实时来源已关闭，已返回不含事实断言的查询规划报告。",
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
  if (returned) return `${returned[1]} 为 ${platformName(returned[3])} 返回 ${returned[2]} 个新来源。`;

  const onlySources = text.match(/^Only (\d+) live sources collected; requested at least (\d+)\./);
  if (onlySources) return `仅收集到 ${onlySources[1]} 个实时来源，低于至少 ${onlySources[2]} 个来源的目标。`;

  const streaming = text.match(/^Streaming section (\d+)\/(\d+)$/);
  if (streaming) return `正在生成第 ${streaming[1]}/${streaming[2]} 个章节。`;

  const completedSection = text.match(/^Completed section (\d+)\/(\d+)$/);
  if (completedSection) return `已完成第 ${completedSection[1]}/${completedSection[2]} 个章节。`;

  return text;
}

function statusClass(status?: ResearchStage["status"]) {
  if (status === "completed") return "bg-emerald-400";
  if (status === "failed") return "bg-red-400";
  if (status === "partial") return "bg-amber-400";
  if (status === "running") return "animate-pulse bg-[color:var(--violet)]";
  return "bg-muted-foreground/30";
}

function QuoteCard({ quote, source }: { quote: NonNullable<ResearchReport["sections"][number]["quote"]>; source?: Source }) {
  return (
    <div className="glass overflow-hidden rounded-2xl" style={{ boxShadow: "var(--shadow-glass)" }}>
      <div className="flex flex-col gap-0 sm:flex-row">
        <div className="relative aspect-video w-full shrink-0 overflow-hidden sm:w-48">
          <img
            src={quote.thumbnail || source?.thumbnail || fallbackThumb(source?.platform)}
            alt=""
            className="h-full w-full object-cover"
          />
          <div className="absolute inset-0 grid place-items-center bg-black/20">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-white/90 shadow-md">
              <Play className="h-4 w-4 translate-x-0.5" style={{ color: "var(--violet)" }} />
            </span>
          </div>
          {quote.duration && (
            <span className="absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white">
              {quote.duration}
            </span>
          )}
        </div>
        <div className="flex flex-col justify-center gap-2 p-5">
          <p className="text-[15px] italic leading-relaxed text-foreground/90">"{quote.quote}"</p>
          <p className="text-xs text-muted-foreground">{quote.author}</p>
        </div>
      </div>
    </div>
  );
}

function ComparisonTable({
  rows,
  onCitationHover,
}: {
  rows: ResearchReport["sections"][number]["table"];
  onCitationHover?: (sourceId: number | string | null) => void;
}) {
  return (
    <div className="glass overflow-hidden rounded-2xl" style={{ boxShadow: "var(--shadow-glass)" }}>
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
          <tr className="border-b border-white/50">
            <th className="px-4 py-3 font-semibold">Signal</th>
            <th className="px-4 py-3 font-semibold">Support</th>
            <th className="px-4 py-3 font-semibold">Risk</th>
            <th className="px-4 py-3 font-semibold">Freshness</th>
            <th className="px-4 py-3 font-semibold">Confidence</th>
            <th className="px-4 py-3 font-semibold">Evidence</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} className="border-b border-white/30 last:border-0">
              <td className="px-4 py-3">
                <div className="font-medium">{row.name}</div>
                {row.signal && <div className="mt-1 max-w-[220px] text-xs normal-case tracking-normal text-muted-foreground">{row.signal}</div>}
              </td>
              <td className="px-4 py-3"><Stars n={row.support ?? row.lowLight} /></td>
              <td className="px-4 py-3"><Stars n={row.risk ?? Math.max(1, 6 - row.video)} /></td>
              <td className="px-4 py-3"><Stars n={row.freshness ?? row.battery} /></td>
              <td className="px-4 py-3"><Stars n={row.confidence ?? row.camera} /></td>
              <td className="px-4 py-3"><CitationList ids={row.evidence} onHover={onCitationHover} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourceItem({ source, highlighted }: { source: Source; highlighted?: boolean }) {
  const teaser = sourceTeaser(source);
  return (
    <li
      data-source-id={String(source.id)}
      data-highlighted={highlighted ? "true" : "false"}
      className="source-card group grid grid-cols-[86px_minmax(0,1fr)] gap-3 rounded-2xl p-2.5 transition hover:bg-white/60"
    >
      <div className="source-cover-frame relative h-16 w-[86px] shrink-0 overflow-hidden rounded-xl">
        <SourceCover source={source} />
        {source.duration && (
          <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 py-0.5 text-[9px] font-medium text-white">
            {source.duration}
          </span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <a
          href={source.url || undefined}
          target="_blank"
          rel="noreferrer"
          className="source-title text-xs font-semibold leading-snug hover:text-primary"
        >
          #{source.id} {source.title} {source.url && <ExternalLink className="ml-1 inline h-3 w-3" />}
        </a>
        <div className="mt-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <PlatformLogoImage platform={source.platform} size={11} />
          <span>{source.creator || source.platform}</span>
        </div>
        {teaser && (
          <p className="source-teaser mt-1 text-[10px] leading-snug text-muted-foreground">
            {teaser}
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-1">
          {(source.badges ?? []).slice(0, 3).map((badge) => (
            <span key={badge} className="rounded-full bg-white/65 px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground ring-1 ring-black/5">
              {badge}
            </span>
          ))}
          {typeof source.evidenceScore === "number" && (
            <span className="rounded-full bg-white/65 px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground ring-1 ring-black/5">
              E{source.evidenceScore}
            </span>
          )}
          {Boolean(source.citationCount) && (
            <span className="rounded-full px-1.5 py-0.5 text-[9px] font-semibold text-white" style={{ background: "linear-gradient(135deg, var(--violet), var(--indigo))" }}>
              cited x{source.citationCount}
            </span>
          )}
        </div>
      </div>
    </li>
  );
}

function SourceCover({ source }: { source: Source }) {
  const [failed, setFailed] = useState(false);
  const thumbnail = normalizeThumbnailUrl(source.thumbnail);

  useEffect(() => {
    setFailed(false);
  }, [source.id, thumbnail]);

  if (!thumbnail || failed) {
    return <GeneratedSourceCover source={source} />;
  }

  return (
    <>
      <img
        src={thumbnail}
        alt=""
        className="source-cover-image h-full w-full object-cover"
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onLoad={(event) => {
          if (!event.currentTarget.naturalWidth || !event.currentTarget.naturalHeight) {
            setFailed(true);
          }
        }}
        onError={() => setFailed(true)}
      />
      <span className="source-cover-badge" aria-hidden="true">
        <PlatformLogoImage platform={source.platform} size={18} />
      </span>
    </>
  );
}

function normalizeThumbnailUrl(value?: string) {
  const thumbnail = value?.trim();
  if (!thumbnail) return "";
  if (thumbnail.startsWith("//")) return `https:${thumbnail}`;
  return thumbnail;
}

function GeneratedSourceCover({ source }: { source: Source }) {
  return (
    <div className="generated-source-cover h-full w-full">
      <PlatformLogoImage platform={source.platform} size={28} />
      <span className="source-cover-platform">{platformName(source.platform)}</span>
      <span className="source-cover-title">{source.title}</span>
    </div>
  );
}

function sourceTeaser(source: Source) {
  const rawText = source.summary || source.whyRelevant || source.transcriptPreview || source.highlights?.[0] || "";
  const text = rawText.replace(/\s+/g, " ").trim();
  const maxLength = 82;
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).replace(/[\s,.;:!?]+$/u, "")}...`;
}

function imageFileName(title: string) {
  const safeTitle = title.replace(/[^\p{L}\p{N}\s-]/gu, "").trim().replace(/\s+/g, "-").slice(0, 64);
  return `voxlens-report-${safeTitle || Date.now()}`;
}

function formatReportDate(value: string | undefined, lang: "zh" | "en") {
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

function Stars({ n }: { n: number }) {
  return (
    <span className="inline-flex gap-0.5 text-[11px]" style={{ color: "var(--violet)" }} aria-label={`${n}/5`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <span key={i} className={i < n ? "" : "text-muted-foreground/30"}>{"\u2605"}</span>
      ))}
    </span>
  );
}

function fallbackThumb(platform?: string) {
  if (platform === "douyin") return "https://images.unsplash.com/photo-1611162618071-b39a2ec055fb?auto=format&fit=crop&w=420&q=80";
  if (platform === "bilibili") return "https://images.unsplash.com/photo-1536240478700-b869070f9279?auto=format&fit=crop&w=420&q=80";
  if (platform === "xiaohongshu") return "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=420&q=80";
  if (platform === "zhihu") return "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?auto=format&fit=crop&w=420&q=80";
  if (platform === "kuaishou") return "https://images.unsplash.com/photo-1522869635100-9f4c5e86aa37?auto=format&fit=crop&w=420&q=80";
  if (platform === "weibo") return "https://images.unsplash.com/photo-1495020689067-958852a7765e?auto=format&fit=crop&w=420&q=80";
  return "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=420&q=80";
}

function createDraftReport(query: string, lang: "zh" | "en", runId = "", stages: ResearchStage[] = []): ResearchReport {
  return {
    runId,
    productName: "VoxLens",
    slogan: lang === "zh" ? "\u89c6\u9891\u8bc1\u636e\uff0c\u53ef\u4fe1\u7814\u7a76" : "Citable social-video research",
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

function createDraftUi(stages: ResearchStage[] = []) {
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

function mergeSourcesIntoReport(report: ResearchReport, incoming: Source[], replace = false): ResearchReport {
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
    ui: report.ui ? {
      ...report.ui,
      sourceGroups: PLATFORMS.map((p) => ({
        id: p.id,
        name: p.name,
        count: sources.filter((source) => source.platform === p.id).length,
        citedCount: sources.filter((source) => source.platform === p.id && (source.citationCount ?? 0) > 0).length,
        status: sources.some((source) => source.platform === p.id) ? "completed" : "queued",
        note: report.platforms.find((platform) => platform.id === p.id)?.note ?? "",
      })),
    } : report.ui,
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
      status: (count > 0 ? "ok" : old?.status ?? "partial") as "ok" | "partial" | "failed" | "demo",
      note: old?.note ?? "",
    };
  });
}

function upsertSection(report: ResearchReport, section: ResearchReport["sections"][number]): ResearchReport {
  const sections = [...report.sections];
  const index = sections.findIndex((item) => item.id === section.id);
  if (index >= 0) sections[index] = section;
  else sections.push(section);
  return { ...report, sections };
}

function appendSectionDelta(report: ResearchReport, sectionId: string, delta: string): ResearchReport {
  const sections = [...report.sections];
  const index = sections.findIndex((item) => item.id === sectionId);
  if (index >= 0) {
    sections[index] = { ...sections[index], body: `${sections[index].body || ""}${delta}` };
  } else {
    sections.push({ id: sectionId, title: sectionId, level: 1, body: delta, bullets: [], table: [] });
  }
  return { ...report, sections };
}
