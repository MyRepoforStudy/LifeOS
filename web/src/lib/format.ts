export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "");
  return letters.join("") || "?";
}

/** "2026-11-19" (a local date from the API) without shifting it through UTC. */
export function parseLocalDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year ?? 1970, (month ?? 1) - 1, day ?? 1);
}

export function formatDay(value: string, locale: string): string {
  const date = value.length === 10 ? parseLocalDate(value) : new Date(value);
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }).format(date);
}

/** "17 December", with the year when it is not the current one. */
export function formatLongDay(value: string, locale: string): string {
  const date = value.length === 10 ? parseLocalDate(value) : new Date(value);
  const options: Intl.DateTimeFormatOptions = { day: "numeric", month: "long" };
  if (date.getFullYear() !== new Date().getFullYear()) options.year = "numeric";
  return new Intl.DateTimeFormat(locale, options).format(date);
}

export function formatDateTime(value: string, locale: string): string {
  const date = new Date(value);
  const sameDay = new Date().toDateString() === date.toDateString();
  return new Intl.DateTimeFormat(
    locale,
    sameDay ? { hour: "2-digit", minute: "2-digit" } : { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" },
  ).format(date);
}

export function formatNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(value);
}

/** Value for <input type="datetime-local"> from an ISO string, in the browser's zone. */
export function toDateTimeInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function fromDateTimeInput(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}
