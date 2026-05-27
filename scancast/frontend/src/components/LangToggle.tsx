import { useI18n } from "@/lib/i18n";

export function LangToggle() {
  const { lang, setLang } = useI18n();
  return (
    <div className="glass inline-flex items-center rounded-full p-1 text-xs font-medium">
      {(["en", "zh"] as const).map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => setLang(l)}
          className={`relative rounded-full px-3 py-1 transition-colors ${
            lang === l ? "text-white" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {lang === l && (
            <span
              className="absolute inset-0 rounded-full"
              style={{
                background: "linear-gradient(135deg, oklch(0.68 0.2 300), oklch(0.6 0.2 260))",
              }}
            />
          )}
          <span className="relative">{l === "en" ? "EN" : "中"}</span>
        </button>
      ))}
    </div>
  );
}
