/** Platform logos are loaded as remote image assets, not inlined SVG. */
const PLATFORMS = [
  { id: "bilibili", name: "Bilibili", logo: "https://www.bilibili.com/favicon.ico" },
  { id: "douyin", name: "Douyin", logo: "https://www.douyin.com/favicon.ico" },
  { id: "youtube", name: "YouTube", logo: "https://www.youtube.com/favicon.ico" },
  { id: "xiaohongshu", name: "Xiaohongshu", logo: "https://www.xiaohongshu.com/favicon.ico" },
  { id: "zhihu", name: "Zhihu", logo: "https://static.zhihu.com/heifetz/favicon.ico" },
  { id: "kuaishou", name: "Kuaishou", logo: "https://www.kuaishou.com/favicon.ico" },
  { id: "weibo", name: "Weibo", logo: "https://weibo.com/favicon.ico" },
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
          <img
            src={p.logo}
            alt={p.name}
            width={size}
            height={size}
            loading="lazy"
            className="block object-contain"
            style={{ width: size, height: size }}
          />
        </span>
      ))}
    </div>
  );
}

export { DISPLAY_PLATFORMS, PLATFORMS };
