import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import gsap from "gsap";
import {
  CheckCircle2,
  Download,
  ExternalLink,
  Play,
  RefreshCw,
  Share2,
  Sparkles,
} from "lucide-react";
import { z } from "zod";
import { BrandMark } from "@/components/BrandMark";
import { LangToggle } from "@/components/LangToggle";
import { PLATFORMS } from "@/components/PlatformLogos";
import { WebSearchIcon } from "@/components/WebSearchIcon";
import {
  createResearchRun,
  getDemoReport,
  getResearchRun,
  runResearch,
  streamResearchRun,
  type PlatformId,
  type ResearchReport,
  type ResearchStage,
  type ResearchStreamEvent,
  type Source,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const searchSchema = z.object({
  q: z.preprocess((value) => (value == null ? undefined : String(value)), z.string().optional()),
  live: z.preprocess((value) => (value == null ? undefined : String(value)), z.string().optional()),
  run: z.preprocess((value) => (value == null ? undefined : String(value)), z.string().optional()),
});
const DEFAULT_RESEARCH_PLATFORMS: PlatformId[] = ["bilibili", "douyin", "youtube", "xiaohongshu", "zhihu", "kuaishou", "weibo"];

export const Route = createFileRoute("/results")({
  validateSearch: (s) => searchSchema.parse(s),
  component: Results,
  head: () => ({
    meta: [
      { title: "VoxLens Research - 研究，不止文字" },
      { name: "description", content: "Cross-platform creator research results." },
    ],
  }),
});

function Results() {
  const { t, lang } = useI18n();
  const { q, live, run } = Route.useSearch();
  const containerRef = useRef<HTMLDivElement>(null);
  const middleScrollRef = useRef<HTMLElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [activeFilter, setActiveFilter] = useState<"all" | PlatformId>("all");
  const [activeOutline, setActiveOutline] = useState<number>(0);
  const [highlightedSourceId, setHighlightedSourceId] = useState<string | null>(null);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [progress, setProgress] = useState(0);
  const [streamEvents, setStreamEvents] = useState<ResearchStreamEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

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
            authMode: "auto",
            includeTranscripts: true,
            minLiveSources: 3,
            lang,
          };
        setReport(createDraftReport(q, lang));
        const created = await createResearchRun(payload);
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

  const exportJson = () => {
    if (!report || typeof window === "undefined") return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `voxlens-report-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const shareUrl = async () => {
    if (typeof window === "undefined") return;
    await navigator.clipboard?.writeText(window.location.href);
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
            onClick={() => void shareUrl()}
            className="glass grid h-9 w-9 place-items-center rounded-full transition hover:-translate-y-0.5"
          >
            <Share2 className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={exportJson}
            className="glass grid h-9 w-9 place-items-center rounded-full transition hover:-translate-y-0.5"
          >
            <Download className="h-4 w-4" />
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

            <ProgressRail stages={report.ui?.stages ?? []} events={streamEvents} progress={progress} />

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
              <ProgressPanel report={report} events={streamEvents} streaming={isWorking} progress={progress} />

              <div className="flex flex-wrap items-center justify-around gap-4">
                {report.platforms.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setActiveFilter(p.id)}
                    className="flex flex-col items-center gap-1.5 rounded-2xl px-4 py-2 transition hover:bg-white/45"
                  >
                    <img
                      src={p.logo || platformLogo(p.id)}
                      alt={p.name}
                      width={36}
                      height={36}
                      className="h-9 w-9 rounded-xl bg-white/80 p-2 shadow-sm ring-1 ring-black/5"
                    />
                    <div className="flex items-center gap-1 text-xs">
                      <span className="font-medium">{p.count} {t("videos")}</span>
                      <CheckCircle2 className="h-3 w-3" style={{ color: "var(--violet)" }} />
                    </div>
                  </button>
                ))}
              </div>

              <InsightStrip report={report} onCitationHover={handleCitationHover} />

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
                  {section.body && <p className="text-[15px] leading-relaxed text-foreground/85">{section.body}</p>}
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

          <aside data-rise data-lenis-prevent className="scroll-col space-y-3 lg:self-start">
            <div className="flex items-center justify-between px-1">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                {t("sources")} / {report.sources.length}
              </p>
            </div>

            <div className="tabs-row overflow-x-auto pl-1 pr-1">
              {[{ id: "all" as const, name: t("all"), logo: "" }, ...PLATFORMS].map((f) => {
                const active = activeFilter === f.id;
                return (
                  <button
                    key={f.id}
                    data-active={active}
                    type="button"
                    onClick={() => setActiveFilter(f.id)}
                    className="chrome-tab whitespace-nowrap"
                  >
                    {f.logo && <img src={f.logo} alt="" width={12} height={12} className="h-3 w-3" />}
                    <span>{f.name}</span>
                  </button>
                );
              })}
            </div>

            <div className="glass -mt-px rounded-2xl rounded-tl-md p-3" style={{ boxShadow: "var(--shadow-glass)" }}>
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
      <Link to="/" className="hidden">home</Link>
    </div>
  );
}

function CitationList({ ids, onHover }: { ids: Array<number | string>; onHover?: (sourceId: number | string | null) => void }) {
  if (!ids.length) return null;
  return (
    <>
      {ids.slice(0, 4).map((id) => (
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
  onCitationHover,
}: {
  report: ResearchReport;
  onCitationHover?: (sourceId: number | string | null) => void;
}) {
  const insights = report.insights ?? [];
  const coverage = report.coverage;
  const quality = report.quality;
  if (!insights.length && !coverage && !quality) return null;

  return (
    <div className="mt-5 grid gap-3 lg:grid-cols-[1fr_220px]">
      {insights.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-3">
          {insights.slice(0, 3).map((insight) => (
            <div key={insight.id} className="rounded-2xl bg-white/45 p-3 ring-1 ring-white/60">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  {insight.kind || "insight"}
                </span>
                <span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-semibold text-foreground">
                  {insight.confidence ?? 3}/5
                </span>
              </div>
              <p className="mt-2 text-sm font-semibold leading-snug">{insight.label}</p>
              {insight.summary && (
                <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-foreground/70">
                  {insight.summary} <CitationList ids={insight.sourceIds ?? []} onHover={onCitationHover} />
                </p>
              )}
            </div>
          ))}
        </div>
      )}
      {coverage && (
        <div className="rounded-2xl bg-foreground/[0.04] p-3 text-xs ring-1 ring-white/60">
          <p className="font-semibold uppercase tracking-[0.14em] text-muted-foreground">Coverage</p>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <MetricPill label="Sources" value={coverage.totalSources} />
            <MetricPill label="Comments" value={coverage.totalComments} />
            <MetricPill label="Platforms" value={coverage.platformCount} />
            <MetricPill label="Cited" value={coverage.citedSources} />
          </div>
          {quality && (
            <div className="mt-2 rounded-xl bg-white/55 px-2.5 py-2 ring-1 ring-white/60">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] text-muted-foreground">Quality</span>
                <span className="text-sm font-semibold">{quality.overall}/100</span>
              </div>
              <p className="mt-1 line-clamp-2 text-[10px] text-muted-foreground">
                Evidence {quality.evidenceStrength?.score ?? 0} · Citations {quality.citationAccuracy?.score ?? 0} · Risk {quality.conclusionRisk?.label ?? "n/a"}
              </p>
            </div>
          )}
        </div>
      )}
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

function ProgressPanel({
  report,
  events,
  streaming,
  progress,
}: {
  report: ResearchReport;
  events: ResearchStreamEvent[];
  streaming: boolean;
  progress: number;
}) {
  const stages = report.ui?.stages ?? [];
  const lastMessage = [...events].reverse().find((event) => event.message)?.message;
  const warnings = report.warnings ?? [];
  if (!streaming && !warnings.length && !stages.length) return null;

  return (
    <div className="mb-5 rounded-2xl bg-white/45 p-4 ring-1 ring-white/50">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            DeepResearch pipeline
          </p>
          <p className="mt-1 text-sm text-foreground/80">
            {lastMessage || report.ui?.interactionHints?.citations || "Waiting for backend events..."}
          </p>
        </div>
        <span className="rounded-full bg-white/70 px-3 py-1 text-xs font-semibold text-foreground ring-1 ring-black/5">
          {Math.max(progress, report.ui?.progress ?? 0)}%
        </span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/60">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.max(progress, report.ui?.progress ?? 0)}%`, background: "linear-gradient(90deg, var(--violet), var(--indigo))" }}
        />
      </div>
      {stages.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {stages.map((stage) => (
            <div key={stage.id} className="rounded-xl bg-white/50 px-3 py-2 text-xs ring-1 ring-white/60">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium">{stage.label}</span>
                <span className={`h-2 w-2 rounded-full ${statusClass(stage.status)}`} />
              </div>
              <div className="mt-1 text-[10px] text-muted-foreground">{stage.progress}%</div>
            </div>
          ))}
        </div>
      )}
      {warnings.length > 0 && (
        <div className="mt-3 space-y-1 text-xs text-muted-foreground">
          {warnings.slice(0, 3).map((warning) => (
            <p key={warning}>• {warning}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function ProgressRail({ stages, events, progress }: { stages: ResearchStage[]; events: ResearchStreamEvent[]; progress: number }) {
  if (!stages.length && !events.length) return null;
  return (
    <div className="glass rounded-2xl p-4 text-xs" style={{ boxShadow: "var(--shadow-glass)" }}>
      <div className="flex items-center justify-between">
        <p className="font-semibold uppercase tracking-[0.16em] text-muted-foreground">Pipeline</p>
        <span className="font-medium text-foreground">{progress}%</span>
      </div>
      <div className="mt-3 space-y-2">
        {stages.map((stage) => (
          <div key={stage.id} className="flex items-center gap-2">
            <span className={`h-2 w-2 shrink-0 rounded-full ${statusClass(stage.status)}`} />
            <span className="min-w-0 flex-1 truncate text-muted-foreground">{stage.label}</span>
            <span className="text-[10px] text-muted-foreground/70">{stage.progress}%</span>
          </div>
        ))}
      </div>
      {events.length > 0 && (
        <div className="mt-3 border-t border-white/45 pt-3">
          <p className="line-clamp-2 text-muted-foreground">{[...events].reverse().find((event) => event.message)?.message}</p>
        </div>
      )}
    </div>
  );
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
  const logo = platformLogo(source.platform);
  return (
    <li
      data-source-id={String(source.id)}
      data-highlighted={highlighted ? "true" : "false"}
      className="source-card group flex gap-3 rounded-xl p-2 transition hover:bg-white/60"
    >
      <div className="relative h-16 w-24 shrink-0 overflow-hidden rounded-lg">
        <img src={source.thumbnail || fallbackThumb(source.platform)} alt="" className="h-full w-full object-cover" loading="lazy" />
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
          className="line-clamp-2 text-xs font-semibold leading-snug hover:text-primary"
        >
          #{source.id} {source.title} {source.url && <ExternalLink className="ml-1 inline h-3 w-3" />}
        </a>
        <div className="mt-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <img src={logo} alt="" width={10} height={10} className="h-2.5 w-2.5" />
          <span>{source.creator || source.platform}</span>
        </div>
        <p className="mt-1 line-clamp-2 text-[10px] leading-snug text-muted-foreground">
          {source.summary || source.transcriptPreview}
        </p>
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

function Stars({ n }: { n: number }) {
  return (
    <span className="inline-flex gap-0.5 text-[11px]" style={{ color: "var(--violet)" }} aria-label={`${n}/5`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <span key={i} className={i < n ? "" : "text-muted-foreground/30"}>{"\u2605"}</span>
      ))}
    </span>
  );
}

function platformLogo(platform?: string) {
  return PLATFORMS.find((p) => p.id === platform)?.logo || "https://www.youtube.com/favicon.ico";
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
    slogan: lang === "zh" ? "\u7814\u7a76\uff0c\u4e0d\u6b62\u6587\u5b57" : "Research beyond text",
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
