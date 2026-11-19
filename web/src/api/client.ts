import type { TokenPair } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; details?: unknown };
}

/** Where the refresh token lives between visits. The access token stays in memory. */
export interface TokenStore {
  getRefreshToken(): string | null;
  setRefreshToken(token: string | null): void;
}

const REFRESH_KEY = "lifeos.refresh_token";

export const browserTokenStore: TokenStore = {
  getRefreshToken() {
    try {
      return localStorage.getItem(REFRESH_KEY);
    } catch {
      return null;
    }
  },
  setRefreshToken(token) {
    try {
      if (token) localStorage.setItem(REFRESH_KEY, token);
      else localStorage.removeItem(REFRESH_KEY);
    } catch {
      // Storage can be unavailable (private mode); the session then lasts one visit.
    }
  },
};

/** Runs `task` exclusively across browser tabs (Web Locks API when available). */
export type Lock = <T>(name: string, task: () => Promise<T>) => Promise<T>;

const browserLock: Lock = (name, task) => {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  return locks ? (locks.request(name, task) as Promise<Awaited<ReturnType<typeof task>>>) : task();
};

type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  body?: unknown;
  query?: Query;
  /** Lets a POST be retried safely: the server replays the first response. */
  idempotencyKey?: string;
  auth?: boolean;
}

export interface ApiClientOptions {
  baseUrl?: string;
  store?: TokenStore;
  fetch?: typeof fetch;
  lock?: Lock;
  retryDelayMs?: number;
}

type RefreshResult = "ok" | "invalid" | "network";

const MAX_NETWORK_RETRIES = 2;

function buildQuery(query: Query | undefined): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class ApiClient {
  private accessToken: string | null = null;
  private refreshing: Promise<RefreshResult> | null = null;
  private readonly listeners = new Set<() => void>();
  private readonly baseUrl: string;
  private readonly store: TokenStore;
  private readonly fetchImpl: typeof fetch;
  private readonly lock: Lock;
  private readonly retryDelayMs: number;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "/api/v1";
    this.store = options.store ?? browserTokenStore;
    this.fetchImpl = options.fetch ?? ((input, init) => fetch(input, init));
    this.lock = options.lock ?? browserLock;
    this.retryDelayMs = options.retryDelayMs ?? 400;
  }

  /** Called when the session cannot be renewed and the user has to log in again. */
  onSessionExpired(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  hasStoredSession(): boolean {
    return this.accessToken !== null || this.store.getRefreshToken() !== null;
  }

  setSession(tokens: TokenPair): void {
    this.accessToken = tokens.access_token;
    this.store.setRefreshToken(tokens.refresh_token);
  }

  clearSession(): void {
    this.accessToken = null;
    this.store.setRefreshToken(null);
  }

  getRefreshToken(): string | null {
    return this.store.getRefreshToken();
  }

  /** Get an access token from the stored refresh token (on app start). */
  async restoreSession(): Promise<boolean> {
    if (this.accessToken) return true;
    const result = await this.refresh();
    if (result === "network") throw new ApiError(0, "network_error", "Network error");
    return result === "ok";
  }

  async request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
    const auth = options.auth ?? true;
    if (auth && !this.accessToken) await this.renew();

    let { response, token } = await this.send(method, path, options, auth);
    if (auth && response.status === 401) {
      // Another request may already have renewed the token while this one was in flight.
      if (!this.accessToken || this.accessToken === token) await this.renew();
      ({ response } = await this.send(method, path, options, auth));
      if (response.status === 401) this.expire();
    }
    return this.parse<T>(response);
  }

  /** One refresh at a time: the server revokes all tokens if a rotated one is reused. */
  refresh(): Promise<RefreshResult> {
    if (!this.refreshing) {
      this.refreshing = this.lock("lifeos-token-refresh", () => this.doRefresh()).finally(() => {
        this.refreshing = null;
      });
    }
    return this.refreshing;
  }

  private async renew(): Promise<void> {
    const result = await this.refresh();
    if (result === "network") throw new ApiError(0, "network_error", "Network error");
    if (result === "invalid") {
      this.expire();
      throw new ApiError(401, "session_expired", "Session expired");
    }
  }

  private async doRefresh(): Promise<RefreshResult> {
    // Read inside the lock: another tab may have just rotated the token.
    const refreshToken = this.store.getRefreshToken();
    if (!refreshToken) return "invalid";
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      return "network";
    }
    if (response.ok) {
      this.setSession((await response.json()) as TokenPair);
      return "ok";
    }
    if (response.status === 401 || response.status === 422) {
      this.clearSession();
      return "invalid";
    }
    return "network";
  }

  private expire(): void {
    this.clearSession();
    for (const listener of this.listeners) listener();
  }

  private async send(
    method: string,
    path: string,
    options: RequestOptions,
    auth: boolean,
  ): Promise<{ response: Response; token: string | null }> {
    const token = auth ? this.accessToken : null;
    const headers: Record<string, string> = { Accept: "application/json" };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;
    if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
    const init: RequestInit = {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    };
    const url = `${this.baseUrl}${path}${buildQuery(options.query)}`;
    // Reads and keyed writes are safe to repeat after a network error.
    const retryable = method === "GET" || Boolean(options.idempotencyKey);
    for (let attempt = 0; ; attempt++) {
      try {
        return { response: await this.fetchImpl(url, init), token };
      } catch (error) {
        if (!retryable || attempt >= MAX_NETWORK_RETRIES) {
          throw new ApiError(0, "network_error", "Network error", error);
        }
        await delay(this.retryDelayMs * (attempt + 1));
      }
    }
  }

  private async parse<T>(response: Response): Promise<T> {
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    let data: unknown;
    try {
      data = text ? JSON.parse(text) : undefined;
    } catch {
      data = undefined;
    }
    if (response.ok) return data as T;
    const error = (data as ErrorBody | undefined)?.error;
    if (!error) {
      // Every API error carries {"error": {...}}. Anything else came from something in
      // between (dev proxy, missing route, crashed server): say the API is unavailable.
      const unavailable = response.status === 404 || response.status >= 500;
      throw new ApiError(
        response.status,
        unavailable ? "api_unavailable" : `http_${response.status}`,
        response.statusText || "Request failed",
      );
    }
    throw new ApiError(
      response.status,
      error?.code ?? `http_${response.status}`,
      error?.message ?? (response.statusText || "Request failed"),
      error?.details,
    );
  }
}
