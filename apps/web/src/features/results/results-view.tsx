import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, Play } from "lucide-react";
import { PlatformLogoImage } from "@/components/PlatformLogos";
import type {
  DecisionCandidate,
  DecisionRecommendation,
  DimensionComparison,
  DimensionComparisonValue,
  PlatformId,
  ResearchReport,
  ResearchStage,
  ResearchStreamEvent,
  Source,
} from "@/lib/api";
import type { Lang } from "@/lib/i18n";
import {
  activityStatusClass,
  failedPlatformsFromWarnings,
  fallbackThumb,
  formatEventType,
  formatInsightKind,
  formatReportDate,
  formatRiskLabel,
  formatStageLabel,
  getDimensionColumns,
  getRowDimension,
  legacyRisk,
  localizePipelineMessage,
  platformName,
  providerActivities,
  resultCopy,
  scoreValue,
  sourceTeaser,
  statusClass,
} from "./report-format";

export function ReportExportSheet({ report, title }: { report: ResearchReport; title: string }) {
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
              <img
                src="/brand/voxlens-mark.svg"
                alt=""
                width={56}
                height={56}
                className="h-14 w-14"
              />
            </span>
            <div>
              <p className="text-2xl font-bold tracking-tight">{report.productName || "VoxLens Studio"}</p>
              <p className="mt-1 text-sm font-medium uppercase tracking-[0.18em] text-[#7f7595]">
                {report.slogan ||
                  (report.lang === "zh" ? "从视频里拿证据，不是拿答案。" : "Evidence, not answers.")}
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
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#8a7a99]">
              Research Report
            </p>
            <h1 className="mt-3 font-display text-5xl font-normal italic leading-[0.98] tracking-tight text-[#151020]">
              {title}
            </h1>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <ExportMetric label="Sources" value={report.totalVideos || report.sources.length} />
            <ExportMetric label="Comments" value={report.totalComments} />
            <ExportMetric label="Platforms" value={activePlatforms.length} />
            <ExportMetric
              label="Cited"
              value={
                report.coverage?.citedSources ??
                report.sources.filter((source) => (source.citationCount ?? 0) > 0).length
              }
            />
          </div>
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-2 border-y border-[#ebe3f2] py-4">
          {activePlatforms.map((platform) => (
            <span
              key={platform.id}
              className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-[#332b44] ring-1 ring-[#eadff2]"
            >
              <PlatformLogoImage platform={platform.id} size={18} />
              {platform.name}
              <span className="text-[#8a7a99]">{platform.count}</span>
            </span>
          ))}
        </div>

        {report.takeaways.length > 0 && (
          <div className="mt-9 rounded-[24px] bg-[#f2edf8] p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#7f7595]">
              Key Takeaways
            </p>
            <div className="mt-4 grid gap-3">
              {report.takeaways.map((item, index) => (
                <p
                  key={`${item.text}-${index}`}
                  className="text-[15px] leading-relaxed text-[#342b44]"
                >
                  <span className="mr-2 font-semibold text-[#8c63ff]">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  {item.text} <ExportCitations ids={item.citations} />
                </p>
              ))}
            </div>
          </div>
        )}

        {insights.length > 0 && (
          <div className="mt-7 grid grid-cols-3 gap-4">
            {insights.slice(0, 3).map((insight) => (
              <div
                key={insight.id}
                className="rounded-[22px] bg-white/80 p-5 ring-1 ring-[#eadff2]"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-[10px] font-semibold uppercase tracking-[0.16em] text-[#8a7a99]">
                    {insight.kind || "insight"}
                  </p>
                  <span className="rounded-full bg-[#f2edf8] px-2 py-0.5 text-[10px] font-bold">
                    {insight.confidence ?? 3}/5
                  </span>
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
            <section
              key={section.id}
              className="rounded-[26px] bg-white/78 p-7 ring-1 ring-[#eadff2]"
            >
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
                    <p
                      key={`${section.id}-${bulletIndex}`}
                      className="text-sm leading-relaxed text-[#3a304c]"
                    >
                      <span className="mr-2 text-[#8c63ff]">•</span>
                      {item.text} <ExportCitations ids={item.citations} />
                    </p>
                  ))}
                </div>
              )}
              {section.quote && (
                <div className="mt-5 rounded-2xl bg-[#f2edf8] p-5">
                  <p className="text-base italic leading-relaxed text-[#2a2139]">
                    "{section.quote.quote}"
                  </p>
                  <p className="mt-2 text-xs font-semibold text-[#7f7595]">
                    {section.quote.author}
                  </p>
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
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8a7a99]">
                  Evidence Sources
                </p>
                <h2 className="mt-2 text-2xl font-bold tracking-tight">
                  {exportSources.length} featured sources
                </h2>
                {omittedSources > 0 && (
                  <p className="mt-1 text-xs text-[#8a7a99]">
                    {omittedSources} additional sources are summarized in the analysis and omitted
                    from this image.
                  </p>
                )}
              </div>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-4">
              {exportSources.map((source) => (
                <div
                  key={`${source.platform}-${source.id}-${source.url}`}
                  className="overflow-hidden rounded-[20px] bg-white/82 ring-1 ring-[#eadff2]"
                >
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
                    <p className="mt-2 line-clamp-2 text-sm font-bold leading-snug text-[#21182e]">
                      {source.title}
                    </p>
                    <p className="mt-1 text-xs text-[#6d617d]">
                      {source.creator || source.author || source.platform}
                    </p>
                    {sourceTeaser(source) && (
                      <p className="mt-2 text-xs leading-relaxed text-[#625772]">
                        {sourceTeaser(source)}
                      </p>
                    )}
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {(source.badges ?? []).slice(0, 3).map((badge) => (
                        <span
                          key={badge}
                          className="rounded-full bg-[#f4eef9] px-2 py-0.5 text-[10px] font-semibold text-[#6d617d]"
                        >
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
          <span>
            {report.productName || "VoxLens Studio"} · {report.slogan || "Evidence, not answers."}
          </span>
          <span>{report.runId || "local-report"}</span>
        </div>
      </div>
    </div>
  );
}

function ExportMetric({ label, value }: { label: string; value?: number }) {
  return (
    <div className="rounded-[18px] bg-white px-4 py-3 ring-1 ring-[#eadff2]">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8a7a99]">
        {label}
      </p>
      <p className="mt-1 text-2xl font-bold text-[#171020]">{value ?? 0}</p>
    </div>
  );
}

function ExportCitations({ ids }: { ids: Array<number | string> }) {
  if (!ids.length) return null;
  return (
    <span className="ml-1 inline-flex flex-wrap gap-1 align-baseline text-[10px] font-bold text-[#8c63ff]">
      {ids.map((id) => (
        <span key={id}>[{id}]</span>
      ))}
    </span>
  );
}

function ExportComparisonTable({ rows }: { rows: ResearchReport["sections"][number]["table"] }) {
  const dimensionColumns = getDimensionColumns(rows);
  if (dimensionColumns.length > 0) {
    return (
      <table className="mt-5 w-full overflow-hidden rounded-2xl text-left text-xs">
        <thead className="bg-[#f2edf8] text-[10px] uppercase tracking-[0.14em] text-[#7f7595]">
          <tr>
            <th className="px-3 py-2 font-semibold">Candidate</th>
            {dimensionColumns.map((dimension) => (
              <th key={dimension.key} className="px-3 py-2 font-semibold">
                {dimension.label}
              </th>
            ))}
            <th className="px-3 py-2 font-semibold">Evidence</th>
          </tr>
        </thead>
        <tbody className="bg-white/70">
          {rows.map((row) => (
            <tr key={row.name} className="border-t border-[#eadff2] align-top">
              <td className="px-3 py-3 font-semibold text-[#21182e]">
                {row.name}
                {row.signal && (
                  <div className="mt-1 max-w-[180px] text-[10px] font-normal text-[#7f7595]">
                    {row.signal}
                  </div>
                )}
              </td>
              {dimensionColumns.map((column) => {
                const dimension = getRowDimension(row, column.key);
                return (
                  <td key={column.key} className="px-3 py-3">
                    <Stars n={scoreValue(dimension?.score, 3)} />
                    {dimension?.summary && (
                      <div className="mt-1 max-w-[160px] text-[10px] leading-snug text-[#5c526d]">
                        {dimension.summary}
                      </div>
                    )}
                    <ExportCitations ids={dimension?.evidence ?? []} />
                  </td>
                );
              })}
              <td className="px-3 py-3">
                <ExportCitations ids={row.evidence} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

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
            <td className="px-3 py-3">
              <Stars n={scoreValue(row.support, row.lowLight, 3)} />
            </td>
            <td className="px-3 py-3">
              <Stars n={legacyRisk(row)} />
            </td>
            <td className="px-3 py-3">
              <Stars n={scoreValue(row.freshness, row.battery, 3)} />
            </td>
            <td className="px-3 py-3">
              <Stars n={scoreValue(row.confidence, row.camera, 3)} />
            </td>
            <td className="px-3 py-3">
              <ExportCitations ids={row.evidence} />
            </td>
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

export function CitationList({
  ids,
  onHover,
}: {
  ids: Array<number | string>;
  onHover?: (sourceId: number | string | null) => void;
}) {
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

export function InsightStrip({
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
                  {insight.summary}{" "}
                  <CitationList ids={insight.sourceIds ?? []} onHover={onCitationHover} />
                </p>
              )}
            </div>
          ))}
          {coverage && (
            <div data-carousel-card className="coverage-slide-card text-xs">
              <p className="font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {resultCopy(lang, "coverage")}
              </p>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <MetricPill label={resultCopy(lang, "sources")} value={coverage.totalSources} />
                <MetricPill label={resultCopy(lang, "comments")} value={coverage.totalComments} />
                <MetricPill label={resultCopy(lang, "platforms")} value={coverage.platformCount} />
                <MetricPill label={resultCopy(lang, "cited")} value={coverage.citedSources} />
              </div>
              {quality && (
                <div className="mt-2 rounded-xl bg-white/55 px-2.5 py-2 ring-1 ring-white/60">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] text-muted-foreground">
                      {resultCopy(lang, "quality")}
                    </span>
                    <span className="text-sm font-semibold">{quality.overall}/100</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[10px] text-muted-foreground">
                    {resultCopy(lang, "evidence")} {quality.evidenceStrength?.score ?? 0} ·{" "}
                    {resultCopy(lang, "citations")} {quality.citationAccuracy?.score ?? 0} ·{" "}
                    {resultCopy(lang, "risk")}{" "}
                    {formatRiskLabel(quality.conclusionRisk?.label, lang)}
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

export function PlatformLogoStrip({
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

export function ProgressPanel({
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
    lastMessage ||
      report.ui?.interactionHints?.citations ||
      (isComplete ? "DeepResearch report completed." : ""),
    lang,
  );
  if (!streaming && !warnings.length && !stages.length) return null;

  return (
    <div
      className="progress-panel mb-5 rounded-2xl bg-white/45 p-4 ring-1 ring-white/50"
      data-expanded={expanded}
    >
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
            {expanded ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>
      {expanded && (
        <>
          {!isComplete && (
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/60">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${percent}%`,
                  background: "linear-gradient(90deg, var(--violet), var(--indigo))",
                }}
              />
            </div>
          )}
          {stages.length > 0 && !isComplete && <StageGrid stages={stages} lang={lang} />}
          <ProviderActivityList
            events={events}
            warnings={warnings}
            platforms={report.platforms}
            lang={lang}
          />
        </>
      )}
    </div>
  );
}

function StageGrid({ stages, lang }: { stages: ResearchStage[]; lang: Lang }) {
  return (
    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
      {stages.map((stage) => (
        <div
          key={stage.id}
          className="rounded-xl bg-white/50 px-3 py-2 text-xs ring-1 ring-white/60"
        >
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

function CarouselHints({
  targetRef,
  count,
}: {
  targetRef: { current: HTMLElement | null };
  count: number;
}) {
  if (count < 2) return null;
  const move = (direction: -1 | 1) => {
    const node = targetRef.current;
    if (!node) return;
    node.scrollBy({ left: direction * node.clientWidth * 0.72, behavior: "smooth" });
  };
  return (
    <div className="carousel-controls">
      <button
        type="button"
        onClick={() => move(-1)}
        className="carousel-nudge"
        aria-label="previous cards"
      >
        ‹
      </button>
      <button
        type="button"
        onClick={() => move(1)}
        className="carousel-nudge"
        aria-label="next cards"
      >
        ›
      </button>
    </div>
  );
}

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
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          {resultCopy(lang, "backend")}
        </span>
        {latestEvent && (
          <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
            <span className="font-semibold text-foreground/70">
              {formatEventType(latestEvent.type, lang)}
            </span>{" "}
            · {localizePipelineMessage(latestEvent.message, lang)}
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

export function ReportSectionContent({
  section,
  sources,
  onCitationHover,
}: {
  section: ResearchReport["sections"][number];
  sources: Source[];
  onCitationHover?: (sourceId: number | string | null) => void;
}) {
  const comparisons = section.data?.comparisons;
  const candidates = section.data?.candidates;
  const recommendation = section.data?.recommendation;
  const isDecisionMatrix =
    section.kind === "decision_matrix" && Array.isArray(comparisons) && comparisons.length > 0;
  const isCandidateSection =
    section.kind === "candidate_map" && Array.isArray(candidates) && candidates.length > 0;
  const isFinalRecommendation = section.kind === "final_recommendation";

  if (isDecisionMatrix) {
    return (
      <>
        {section.body && (
          <p className="text-[15px] leading-relaxed text-foreground/85">
            {section.body} <CitationList ids={section.sourceIds ?? []} onHover={onCitationHover} />
          </p>
        )}
        <DecisionMatrix
          candidates={Array.isArray(candidates) ? candidates : []}
          comparisons={comparisons}
          onCitationHover={onCitationHover}
        />
      </>
    );
  }

  if (isCandidateSection) {
    return (
      <>
        {section.body && (
          <p className="text-[15px] leading-relaxed text-foreground/85">
            {section.body} <CitationList ids={section.sourceIds ?? []} onHover={onCitationHover} />
          </p>
        )}
        <DecisionCandidateGrid candidates={candidates} onCitationHover={onCitationHover} />
      </>
    );
  }

  if (isFinalRecommendation) {
    return (
      <>
        <FinalRecommendationCard
          body={section.body}
          recommendation={recommendation}
          sourceIds={section.sourceIds ?? []}
          onCitationHover={onCitationHover}
        />
        {section.bullets.length > 0 && (
          <ul className="space-y-2 text-sm text-foreground/85">
            {section.bullets.map((item, i) => (
              <li key={`${section.id}-${i}`} className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-foreground/40" />
                <span>
                  {item.text} <CitationList ids={item.citations} onHover={onCitationHover} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </>
    );
  }

  return (
    <>
      {section.body && (
        <p className="text-[15px] leading-relaxed text-foreground/85">
          {section.body} <CitationList ids={section.sourceIds ?? []} onHover={onCitationHover} />
        </p>
      )}
      {section.bullets.length > 0 && (
        <ul className="space-y-2 text-sm text-foreground/85">
          {section.bullets.map((item, i) => (
            <li key={`${section.id}-${i}`} className="flex gap-2">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-foreground/40" />
              <span>
                {item.text} <CitationList ids={item.citations} onHover={onCitationHover} />
              </span>
            </li>
          ))}
        </ul>
      )}
      {section.quote && (
        <QuoteCard
          quote={section.quote}
          source={sources.find((s) => s.id === section.quote?.sourceId)}
        />
      )}
      {section.table.length > 0 && (
        <ComparisonTable rows={section.table} onCitationHover={onCitationHover} />
      )}
    </>
  );
}

function DecisionCandidateGrid({
  candidates,
  onCitationHover,
}: {
  candidates: DecisionCandidate[];
  onCitationHover?: (sourceId: number | string | null) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {candidates.slice(0, 5).map((candidate, index) => (
        <div
          key={`${candidate.name}-${index}`}
          className="glass rounded-2xl p-4"
          style={{ boxShadow: "var(--shadow-glass)" }}
        >
          <div className="flex items-center justify-between gap-3">
            <p className="text-base font-semibold">{candidate.name}</p>
            <span className="rounded-full bg-white/70 px-2.5 py-1 text-[10px] font-semibold text-muted-foreground">
              {candidate.sourceIds.length} sources
            </span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
            {candidate.matchReason}{" "}
            <CitationList ids={candidate.sourceIds} onHover={onCitationHover} />
          </p>
        </div>
      ))}
    </div>
  );
}

function DecisionMatrix({
  candidates,
  comparisons,
  onCitationHover,
}: {
  candidates: DecisionCandidate[];
  comparisons: DimensionComparison[];
  onCitationHover?: (sourceId: number | string | null) => void;
}) {
  const candidateNames = candidates.length
    ? candidates.map((candidate) => candidate.name)
    : Array.from(
        new Set(
          comparisons.flatMap((comparison) => comparison.values.map((value) => value.candidate)),
        ),
      ).slice(0, 5);
  const contradictory = comparisons.filter((comparison) => comparison.isContradictory);

  return (
    <div className="glass overflow-hidden rounded-2xl" style={{ boxShadow: "var(--shadow-glass)" }}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
            <tr className="border-b border-white/50">
              <th className="px-4 py-3 font-semibold">Candidate</th>
              {comparisons.map((comparison) => (
                <th key={comparison.dimension} className="px-4 py-3 font-semibold">
                  <span>{comparison.dimension}</span>
                  {comparison.isContradictory && (
                    <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] text-amber-700">
                      conflict
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {candidateNames.map((candidate) => (
              <tr key={candidate} className="border-b border-white/30 align-top last:border-0">
                <td className="px-4 py-4 font-semibold">{candidate}</td>
                {comparisons.map((comparison) => {
                  const value = comparison.values.find((item) => item.candidate === candidate);
                  return (
                    <td key={`${candidate}-${comparison.dimension}`} className="px-4 py-4">
                      {value ? (
                        <DecisionMatrixCell value={value} onCitationHover={onCitationHover} />
                      ) : (
                        <span className="text-xs text-muted-foreground">No direct evidence</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {contradictory.length > 0 && (
        <div className="border-t border-white/50 bg-white/35 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
          {contradictory.map((item) => (
            <p key={item.dimension}>
              <span className="font-semibold text-foreground/80">{item.dimension}: </span>
              {item.contradictionReason ||
                "Contradictory evidence needs source-level verification."}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function DecisionMatrixCell({
  value,
  onCitationHover,
}: {
  value: DimensionComparisonValue;
  onCitationHover?: (sourceId: number | string | null) => void;
}) {
  return (
    <div className="max-w-[240px]">
      <span
        className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${confidencePillClass(value.confidence)}`}
      >
        {value.confidence || "gray"}
      </span>
      <p className="mt-2 text-xs leading-relaxed text-foreground/80">{value.conclusion}</p>
      {value.condition && (
        <p className="mt-1 text-[11px] text-muted-foreground">Condition: {value.condition}</p>
      )}
      <div className="mt-2">
        <CitationList ids={value.sourceIds ?? []} onHover={onCitationHover} />
      </div>
    </div>
  );
}

function FinalRecommendationCard({
  body,
  recommendation,
  sourceIds,
  onCitationHover,
}: {
  body: string;
  recommendation?: DecisionRecommendation;
  sourceIds: number[];
  onCitationHover?: (sourceId: number | string | null) => void;
}) {
  return (
    <div className="rounded-3xl bg-gradient-to-br from-[#fff7df] via-white to-[#e8f7f1] p-5 shadow-[0_24px_80px_-42px_rgba(40,73,62,0.45)] ring-1 ring-white/75">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Final buy call
          </p>
          {recommendation?.primary && (
            <h3 className="mt-2 text-2xl font-bold tracking-tight">Buy {recommendation.primary}</h3>
          )}
        </div>
        {recommendation?.backup && (
          <span className="rounded-full bg-white/75 px-3 py-1 text-xs font-semibold text-foreground/70 ring-1 ring-black/5">
            Backup: {recommendation.backup}
          </span>
        )}
      </div>
      {body && (
        <p className="mt-4 text-[15px] leading-relaxed text-foreground/85">
          {body} <CitationList ids={sourceIds} onHover={onCitationHover} />
        </p>
      )}
      {recommendation?.conditions?.length ? (
        <div className="mt-4 grid gap-2 text-xs text-foreground/75 sm:grid-cols-2">
          {recommendation.conditions.slice(0, 4).map((condition, index) => (
            <div
              key={`${condition}-${index}`}
              className="rounded-2xl bg-white/65 p-3 ring-1 ring-white/70"
            >
              {condition}
            </div>
          ))}
        </div>
      ) : null}
      {recommendation?.notRecommended && (
        <p className="mt-4 rounded-2xl bg-rose-50/80 px-3 py-2 text-xs font-medium text-rose-700">
          Not recommended when: {recommendation.notRecommended}
        </p>
      )}
    </div>
  );
}

function confidencePillClass(confidence?: string) {
  if (confidence === "green") return "bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200";
  if (confidence === "yellow") return "bg-amber-100 text-amber-700 ring-1 ring-amber-200";
  return "bg-slate-100 text-slate-600 ring-1 ring-slate-200";
}

function QuoteCard({
  quote,
  source,
}: {
  quote: NonNullable<ResearchReport["sections"][number]["quote"]>;
  source?: Source;
}) {
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
  const dimensionColumns = getDimensionColumns(rows);
  if (dimensionColumns.length > 0) {
    return (
      <div
        className="glass overflow-x-auto rounded-2xl"
        style={{ boxShadow: "var(--shadow-glass)" }}
      >
        <table className="w-full min-w-[760px] text-sm">
          <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
            <tr className="border-b border-white/50">
              <th className="px-4 py-3 font-semibold">Candidate</th>
              {dimensionColumns.map((dimension) => (
                <th key={dimension.key} className="px-4 py-3 font-semibold">
                  {dimension.label}
                </th>
              ))}
              <th className="px-4 py-3 font-semibold">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name} className="border-b border-white/30 align-top last:border-0">
                <td className="px-4 py-3">
                  <div className="font-medium">{row.name}</div>
                  {row.signal && (
                    <div className="mt-1 max-w-[220px] text-xs normal-case tracking-normal text-muted-foreground">
                      {row.signal}
                    </div>
                  )}
                  {row.price && (
                    <div className="mt-2 text-[11px] font-medium text-muted-foreground">
                      {row.price}
                    </div>
                  )}
                </td>
                {dimensionColumns.map((column) => {
                  const dimension = getRowDimension(row, column.key);
                  return (
                    <td key={column.key} className="px-4 py-3">
                      <Stars n={scoreValue(dimension?.score, 3)} />
                      {dimension?.summary && (
                        <div className="mt-1 max-w-[210px] text-xs leading-relaxed text-muted-foreground">
                          {dimension.summary}
                        </div>
                      )}
                      <CitationList ids={dimension?.evidence ?? []} onHover={onCitationHover} />
                    </td>
                  );
                })}
                <td className="px-4 py-3">
                  <CitationList ids={row.evidence} onHover={onCitationHover} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

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
                {row.signal && (
                  <div className="mt-1 max-w-[220px] text-xs normal-case tracking-normal text-muted-foreground">
                    {row.signal}
                  </div>
                )}
              </td>
              <td className="px-4 py-3">
                <Stars n={scoreValue(row.support, row.lowLight, 3)} />
              </td>
              <td className="px-4 py-3">
                <Stars n={legacyRisk(row)} />
              </td>
              <td className="px-4 py-3">
                <Stars n={scoreValue(row.freshness, row.battery, 3)} />
              </td>
              <td className="px-4 py-3">
                <Stars n={scoreValue(row.confidence, row.camera, 3)} />
              </td>
              <td className="px-4 py-3">
                <CitationList ids={row.evidence} onHover={onCitationHover} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SourceItem({ source, highlighted }: { source: Source; highlighted?: boolean }) {
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
          #{source.id} {source.title}{" "}
          {source.url && <ExternalLink className="ml-1 inline h-3 w-3" />}
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
            <span
              key={badge}
              className="rounded-full bg-white/65 px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground ring-1 ring-black/5"
            >
              {badge}
            </span>
          ))}
          {typeof source.evidenceScore === "number" && (
            <span className="rounded-full bg-white/65 px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground ring-1 ring-black/5">
              E{source.evidenceScore}
            </span>
          )}
          {Boolean(source.citationCount) && (
            <span
              className="rounded-full px-1.5 py-0.5 text-[9px] font-semibold text-white"
              style={{ background: "linear-gradient(135deg, var(--violet), var(--indigo))" }}
            >
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

function Stars({ n }: { n: number }) {
  return (
    <span
      className="inline-flex gap-0.5 text-[11px]"
      style={{ color: "var(--violet)" }}
      aria-label={`${n}/5`}
    >
      {Array.from({ length: 5 }).map((_, i) => (
        <span key={i} className={i < n ? "" : "text-muted-foreground/30"}>
          {"\u2605"}
        </span>
      ))}
    </span>
  );
}
