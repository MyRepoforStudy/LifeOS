import { useI18n, type Lang } from "../i18n";

const LANGS: Lang[] = ["ru", "en"];

export function LanguageSwitch() {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="segmented" role="group" aria-label={t("profile.language")} style={{ flex: "none" }}>
      {LANGS.map((option) => (
        <button key={option} type="button" aria-pressed={lang === option} onClick={() => setLang(option)}>
          {option.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
