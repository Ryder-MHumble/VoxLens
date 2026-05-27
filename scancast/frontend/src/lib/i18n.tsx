import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "en" | "zh";

type Dict = Record<string, { en: string; zh: string }>;

const dict: Dict = {
  brand: { en: "VoxLens", zh: "VoxLens" },
  nav_results: { en: "Demo result", zh: "示例报告" },
  hero_a: { en: "Research beyond text", zh: "研究，不止文字" },
  hero_b1: {
    en: "VoxLens watches creator videos, comments and transcripts, then turns them into ",
    zh: "看完视频、评论和字幕，再把分散观点压缩成",
  },
  hero_b2: { en: "evidence you can verify", zh: "可验证的研究证据" },
  hero_b3: { en: ".", zh: "。" },
  placeholder: { en: "What do you want to research across videos?", zh: "你想跨平台研究什么问题？" },
  searching_across: { en: "Searching across", zh: "默认覆盖" },
  suggestion_title: { en: "Try one of these", zh: "可以先试试这些问题" },
  s1: { en: "Best camera phones under 5000 RMB", zh: "5000 元以内拍照最稳的手机" },
  s2: { en: "Is Vision Pro worth daily use?", zh: "Vision Pro 日常使用到底值不值得？" },
  s3: { en: "Which action camera should I buy in 2026?", zh: "2026 年运动相机怎么选？" },
  s4: { en: "AeroPress vs Hario V60: which to buy?", zh: "AeroPress 和 Hario V60 该买哪个？" },
  research_title: { en: "Research Results", zh: "研究报告" },
  re_research: { en: "Deep re-run", zh: "深度重跑" },
  outline: { en: "Outline", zh: "报告大纲" },
  sources: { en: "Sources", zh: "原始来源" },
  all: { en: "All", zh: "全部" },
  videos: { en: "videos", zh: "条视频" },
  platforms: { en: "platforms", zh: "个平台" },
  comments: { en: "comments", zh: "条评论" },
  follow_up: { en: "follow-up", zh: "追问" },
  follow_up_ph: { en: "Ask a follow-up...", zh: "继续追问，比如：只看差评里提到的问题..." },
  key_takeaways: { en: "Key Takeaways", zh: "核心结论" },
  loading: { en: "Starting DeepResearch...", zh: "正在启动 DeepResearch..." },
  streaming_badge: { en: "Streaming", zh: "生成中" },
  partial_badge: { en: "Evidence-limited", zh: "证据有限" },
  demo_badge: { en: "Demo fallback", zh: "示例回退" },
  live_badge: { en: "Live report", zh: "实时报告" },
  streaming_report: { en: "Collecting sources and preparing the report stream...", zh: "正在检索来源并准备流式报告..." },
  empty_report: { en: "No report sections yet.", zh: "暂无报告正文。" },
  error_title: { en: "Could not load report", zh: "报告加载失败" },
  retry: { en: "Retry", zh: "重试" },
  empty: { en: "No sources yet.", zh: "暂无来源。" },
  generated_at: { en: "Generated at", zh: "生成时间" },
};

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (k: keyof typeof dict) => string };

const I18nContext = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("zh");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = (localStorage.getItem("voxlens.lang") || localStorage.getItem("scancast.lang")) as Lang | null;
    if (saved === "en" || saved === "zh") setLangState(saved);
  }, []);

  const setLang = (l: Lang) => {
    setLangState(l);
    if (typeof window !== "undefined") localStorage.setItem("voxlens.lang", l);
  };

  const t = (k: keyof typeof dict) => dict[k][lang];

  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}
