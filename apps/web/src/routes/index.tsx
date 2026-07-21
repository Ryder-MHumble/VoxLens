import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { BrandMark } from "@/components/BrandMark";
import { LangToggle } from "@/components/LangToggle";
import { Orb } from "@/components/Orb";
import { PlatformLogos } from "@/components/PlatformLogos";
import { WebSearchIcon } from "@/components/WebSearchIcon";
import { useI18n } from "@/lib/i18n";

const Grainient = lazy(() =>
  import("@/components/Grainient").then((mod) => ({ default: mod.Grainient })),
);

type ResearchMode = "consumer" | "business";

export const Route = createFileRoute("/")({
  component: Landing,
  head: () => ({
    meta: [
      { title: "VoxLens Studio - 从视频里拿证据，不是拿答案" },
      {
        name: "description",
        content: "在可控环境中，把中文视频口播、字幕和评论转成可审计、可引用的研究证据。",
      },
    ],
  }),
});

function Landing() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const [mode, setMode] = useState<ResearchMode>("consumer");
  const heroRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!heroRef.current) return;
    const ctx = gsap.context(() => {
      gsap.from("[data-hero] > *", {
        y: 24,
        opacity: 0,
        duration: 0.9,
        ease: "power3.out",
        stagger: 0.09,
        delay: 0.15,
      });
    }, heroRef);
    return () => ctx.revert();
  }, []);

  const submit = () => {
    if (!value.trim()) return;
    navigate({ to: "/results", search: { q: value.trim(), mode } });
  };

  const modes = [
    {
      id: "consumer" as const,
      eyebrow: t("mode_consumer_eyebrow"),
      title: t("mode_consumer_title"),
      description: t("mode_consumer_desc"),
      note: t("mode_consumer_note"),
    },
    {
      id: "business" as const,
      eyebrow: t("mode_business_eyebrow"),
      title: t("mode_business_title"),
      description: t("mode_business_desc"),
      note: t("mode_business_note"),
    },
  ];

  const suggestions = {
    consumer: ["consumer_s1", "consumer_s2", "consumer_s3"] as const,
    business: ["business_s1", "business_s2", "business_s3"] as const,
  };

  return (
    <div ref={heroRef} className="relative flex min-h-screen flex-col">
      <Suspense fallback={null}>
        <Grainient
          className="home-grainient"
          timeSpeed={0.24}
          colorBalance={-0.08}
          warpStrength={0.78}
          warpFrequency={4.2}
          warpSpeed={1.28}
          warpAmplitude={58}
          blendAngle={-22}
          blendSoftness={0.18}
          rotationAmount={260}
          noiseScale={1.65}
          grainAmount={0.042}
          grainScale={2.1}
          grainAnimated
          contrast={1.08}
          gamma={1.04}
          saturation={1.1}
          centerY={0}
          zoom={0.96}
          color1="#F4F8FF"
          color2="#FFD2E7"
          color3="#BFE9FF"
        />
      </Suspense>
      <header className="flex items-center justify-between px-6 py-5 sm:px-10">
        <BrandMark />
        <div className="flex items-center gap-4">
          <LangToggle />
          <div className="hidden sm:block">
            <Orb size={44} />
          </div>
        </div>
      </header>

      <main className="flex flex-1 items-start justify-center px-6 pb-16 pt-8 sm:items-center sm:pb-20 sm:pt-0">
        <div data-hero className="w-full max-w-4xl text-center">
          <h1 className="font-display text-5xl font-normal leading-[1.02] tracking-tight text-foreground sm:text-[78px]">
            <span className="italic text-gradient-violet">{t("hero_a")}</span>
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-base font-light leading-relaxed tracking-tight text-muted-foreground sm:text-lg">
            {t("hero_b1")}
            <span className="font-display italic text-foreground/85">{t("hero_b2")}</span>
            {t("hero_b3")}
          </p>

          <div
            className="mx-auto mt-8 grid max-w-3xl gap-3 text-left sm:grid-cols-2"
            role="group"
            aria-label={t("mode_aria")}
          >
            {modes.map((item) => {
              const active = mode === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setMode(item.id)}
                  className={`glass rounded-3xl p-4 text-left transition hover:-translate-y-0.5 ${
                    active ? "ring-2 ring-violet/35" : "opacity-80 hover:opacity-100"
                  }`}
                  style={active ? { boxShadow: "var(--shadow-glass)" } : undefined}
                >
                  <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground/75">
                    {item.eyebrow}
                  </span>
                  <span className="mt-2 block text-base font-semibold tracking-tight text-foreground">
                    {item.title}
                  </span>
                  <span className="mt-2 block text-sm leading-relaxed text-muted-foreground">
                    {item.description}
                  </span>
                  <span className="mt-3 block text-xs font-medium text-foreground/75">
                    {item.note}
                  </span>
                </button>
              );
            })}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
            className="relative mx-auto mt-8 max-w-2xl"
          >
            <div className="search-shell glass flex items-center gap-3 rounded-full px-5 py-3.5 pr-3">
              <input
                ref={inputRef}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key !== "Enter") return;
                  e.preventDefault();
                  submit();
                }}
                placeholder={t(
                  mode === "consumer" ? "placeholder_consumer" : "placeholder_business",
                )}
                className="w-full bg-transparent text-[15px] text-foreground placeholder:text-muted-foreground/80 focus:outline-none"
              />
              <button
                type="submit"
                aria-label="Submit"
                className="search-icon-button grid h-10 w-10 shrink-0 place-items-center"
              >
                <WebSearchIcon className="h-5 w-5" />
              </button>
            </div>
          </form>

          <div className="mt-7 flex flex-wrap items-center justify-center gap-3 text-xs text-muted-foreground">
            <span>{t("searching_across")}</span>
            <PlatformLogos />
          </div>

          <div className="mt-10">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground/70">
              {t(mode === "consumer" ? "suggestion_consumer_title" : "suggestion_business_title")}
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
              {suggestions[mode].map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => {
                    setValue(t(k));
                    inputRef.current?.focus();
                  }}
                  className="glass rounded-full px-4 py-2 text-xs font-medium text-foreground/80 transition hover:-translate-y-0.5 hover:text-foreground"
                >
                  {t(k)}
                </button>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
