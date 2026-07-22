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
  const heroRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const heroTitle = t("hero_a");

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
    navigate({ to: "/results", search: { q: value.trim() } });
  };

  const suggestions = ["consumer_s1", "consumer_s2", "business_s1", "business_s2"] as const;

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

      <main className="flex flex-1 items-center justify-center px-6 pb-24">
        <div data-hero className="w-full max-w-3xl text-center">
          <h1 className="font-display text-[34px] font-normal leading-[1.02] tracking-tight text-foreground sm:text-[64px] md:text-[72px]">
            <span className="italic text-gradient-violet">{heroTitle}</span>
          </h1>
          <p className="mx-auto mt-5 max-w-lg text-sm font-light leading-relaxed tracking-tight text-muted-foreground sm:text-base">
            {t("hero_b1")}
            <span className="font-display italic text-foreground/85">{t("hero_b2")}</span>
            {t("hero_b3")}
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
            className="relative mx-auto mt-12 max-w-2xl"
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
                placeholder={t("placeholder")}
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

          <div className="mx-auto mt-12 flex max-w-3xl flex-wrap items-center justify-center gap-2">
            {suggestions.map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => {
                  setValue(t(k));
                  inputRef.current?.focus();
                }}
                className="glass max-w-full rounded-full px-4 py-2 text-xs font-medium text-foreground/80 transition hover:-translate-y-0.5 hover:text-foreground"
              >
                {t(k)}
              </button>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
