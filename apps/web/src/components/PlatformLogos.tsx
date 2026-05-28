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

export function PlatformLogoImage({
  platform,
  size,
  alt = "",
  className = "",
}: {
  platform?: string;
  size: number;
  alt?: string;
  className?: string;
}) {
  const width = platform === "youtube" ? Math.round(size * 1.55) : size;
  return (
    <img
      src={platformLogoSrc(platform)}
      alt={alt}
      width={width}
      height={size}
      data-platform-logo={platform || "unknown"}
      className={`platform-logo-image ${className}`.trim()}
      decoding="async"
      style={{ width, height: size }}
    />
  );
}

const PLATFORMS = [
  { id: "bilibili", name: "Bilibili", logo: platformLogoSrc("bilibili") },
  { id: "douyin", name: "Douyin", logo: platformLogoSrc("douyin") },
  { id: "youtube", name: "YouTube", logo: platformLogoSrc("youtube") },
  { id: "xiaohongshu", name: "Xiaohongshu", logo: platformLogoSrc("xiaohongshu") },
  { id: "zhihu", name: "Zhihu", logo: platformLogoSrc("zhihu") },
  { id: "kuaishou", name: "Kuaishou", logo: platformLogoSrc("kuaishou") },
  { id: "weibo", name: "Weibo", logo: platformLogoSrc("weibo") },
] as const;

const DISPLAY_PLATFORMS = [
  ...PLATFORMS,
] as const;

export function PlatformLogos({ size = 18 }: { size?: number }) {
  return (
    <div className="flex items-center gap-3">
      {DISPLAY_PLATFORMS.map((p) => (
        <span
          key={p.id}
          title={p.name}
          className="inline-flex items-center justify-center opacity-80 grayscale-[18%] transition hover:-translate-y-0.5 hover:opacity-100 hover:grayscale-0"
        >
          <PlatformLogoImage platform={p.id} size={size} alt={p.name} />
        </span>
      ))}
    </div>
  );
}

export { DISPLAY_PLATFORMS, PLATFORMS };
