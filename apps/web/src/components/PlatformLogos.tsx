import { DISPLAY_PLATFORMS, platformLogoSrc } from "@/lib/platforms";

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
