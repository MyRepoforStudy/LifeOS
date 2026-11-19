import { useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { I18nContext, type I18n, type Lang, type Messages, type MessageKey, type Params } from "./context";
import { en } from "./en";
import { ru } from "./ru";

export type { Lang, Messages, MessageKey } from "./context";

const DICTIONARIES: Record<Lang, Messages> = { ru, en };
const LANG_KEY = "lifeos.lang";

function detectLang(): Lang {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved === "ru" || saved === "en") return saved;
  } catch {
    // ignore
  }
  return navigator.language.toLowerCase().startsWith("ru") ? "ru" : "en";
}

function lookup(messages: Messages, key: string): string | undefined {
  let node: unknown = messages;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

function format(template: string, params?: Params): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectLang);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      localStorage.setItem(LANG_KEY, next);
    } catch {
      // ignore
    }
    document.documentElement.lang = next;
  }, []);

  const value = useMemo<I18n>(() => {
    const messages = DICTIONARIES[lang];
    const t = (key: MessageKey, params?: Params) => format(lookup(messages, key) ?? key, params);
    const errorText = (error: unknown) => {
      if (!(error instanceof ApiError)) return messages.errors.generic;
      if (error.code === "validation_error" && Array.isArray(error.details)) {
        // Name the first invalid field when we know it, e.g. ["body", "email"].
        for (const detail of error.details as { loc?: unknown[] }[]) {
          const field = detail.loc?.[1];
          const text = typeof field === "string" ? lookup(messages, `errors.fields.${field}`) : undefined;
          if (text) return text;
        }
      }
      return lookup(messages, `errors.${error.code}`) ?? messages.errors.generic;
    };
    return { lang, locale: lang === "ru" ? "ru-RU" : "en-GB", setLang, t, errorText };
  }, [lang, setLang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}
