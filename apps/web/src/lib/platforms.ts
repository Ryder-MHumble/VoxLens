import type { PlatformId } from "@/lib/api";

const PLATFORM_LOGO_PATHS: Record<string, string> = {
  bilibili: "/logo/bilibili.png",
  douyin: "/logo/douyin.png",
  youtube: "/logo/youtube.png",
  xiaohongshu: "/logo/xiaohongshu.png",
  zhihu: "/logo/zhihu.png",
  kuaishou: "/logo/kuaishou.png",
  weibo: "/logo/weibo.png",
};

export function platformLogoSrc(platform?: string) {
  return PLATFORM_LOGO_PATHS[platform || ""] || PLATFORM_LOGO_PATHS.youtube;
}

export const PLATFORMS = [
  { id: "bilibili", name: "Bilibili", logo: platformLogoSrc("bilibili") },
  { id: "douyin", name: "Douyin", logo: platformLogoSrc("douyin") },
  { id: "youtube", name: "YouTube", logo: platformLogoSrc("youtube") },
  { id: "xiaohongshu", name: "Xiaohongshu", logo: platformLogoSrc("xiaohongshu") },
  { id: "zhihu", name: "Zhihu", logo: platformLogoSrc("zhihu") },
  { id: "kuaishou", name: "Kuaishou", logo: platformLogoSrc("kuaishou") },
  { id: "weibo", name: "Weibo", logo: platformLogoSrc("weibo") },
] as const;

export const DISPLAY_PLATFORMS = [...PLATFORMS] as const;

export const DEFAULT_RESEARCH_PLATFORMS = PLATFORMS.map((platform) => platform.id) as PlatformId[];
