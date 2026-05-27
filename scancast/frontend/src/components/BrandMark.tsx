import { Link } from "@tanstack/react-router";
import { useI18n } from "@/lib/i18n";

export function BrandMark() {
  const { t } = useI18n();
  return (
    <Link to="/" className="group inline-flex items-center gap-2.5">
      <span className="relative grid h-9 w-9 place-items-center rounded-2xl bg-white/55 shadow-[0_10px_28px_-18px_rgba(121,91,255,0.8)] ring-1 ring-white/75 backdrop-blur-xl transition-transform duration-500 group-hover:-rotate-3 group-hover:scale-105">
        <img
          src="/brand/voxlens-mark.svg"
          alt=""
          width={32}
          height={32}
          className="h-8 w-8"
        />
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-foreground">
        {t("brand")}
      </span>
    </Link>
  );
}
