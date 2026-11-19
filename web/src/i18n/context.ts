import { createContext } from "react";

import type { ru } from "./ru";

type Shape<T> = { [K in keyof T]: T[K] extends string ? string : Shape<T[K]> };
type Leaves<T, Prefix extends string = ""> = {
  [K in keyof T & (string | number)]: T[K] extends string ? `${Prefix}${K}` : Leaves<T[K], `${Prefix}${K}.`>;
}[keyof T & (string | number)];

export type Messages = Shape<typeof ru>;
export type MessageKey = Leaves<typeof ru>;
export type Lang = "ru" | "en";
export type Params = Record<string, string | number>;

export interface I18n {
  lang: Lang;
  locale: string;
  setLang: (lang: Lang) => void;
  t: (key: MessageKey, params?: Params) => string;
  /** Localized text for an API error, naming the invalid field when known. */
  errorText: (error: unknown) => string;
}

// Kept in its own module so that hot reloading the provider does not create a
// second context object while components still hold the first one.
export const I18nContext = createContext<I18n | null>(null);
