import { describe, expect, it, vi } from "vitest";

import { ApiClient, type TokenStore } from "./client";

function memoryStore(initial: string | null = null): TokenStore & { value: string | null } {
  const store = {
    value: initial,
    getRefreshToken: () => store.value,
    setRefreshToken: (token: string | null) => {
      store.value = token;
    },
  };
  return store;
}

const noLock = <T>(_name: string, task: () => Promise<T>) => task();

function json(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function header(init: RequestInit | undefined, name: string): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.[name];
}

function tokens(n: number) {
  return { access_token: `access-${n}`, refresh_token: `refresh-${n}`, token_type: "bearer", expires_in: 900 };
}

describe("ApiClient", () => {
  it("refreshes once for parallel requests and retries them", async () => {
    let refreshCalls = 0;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return json(200, tokens(refreshCalls));
      }
      return header(init, "Authorization") === "Bearer access-1"
        ? json(200, { ok: url })
        : json(401, { error: { code: "invalid_token", message: "expired" } });
    });
    const store = memoryStore("refresh-0");
    const client = new ApiClient({ baseUrl: "", store, lock: noLock, fetch: fetchMock as unknown as typeof fetch });
    client.setSession({ ...tokens(0), access_token: "stale" });

    const results = await Promise.all(["/a", "/b", "/c"].map((path) => client.request("GET", path)));

    expect(results).toEqual([{ ok: "/a" }, { ok: "/b" }, { ok: "/c" }]);
    expect(refreshCalls).toBe(1);
    expect(store.value).toBe("refresh-1");
  });

  it("retries a keyed POST after a network error with the same Idempotency-Key", async () => {
    const keys: (string | undefined)[] = [];
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      keys.push(header(init, "Idempotency-Key"));
      if (keys.length === 1) throw new TypeError("Failed to fetch");
      return json(200, { done: true });
    });
    const client = new ApiClient({
      baseUrl: "",
      store: memoryStore(),
      lock: noLock,
      retryDelayMs: 1,
      fetch: fetchMock as unknown as typeof fetch,
    });

    const result = await client.request("POST", "/quests/1/complete", { auth: false, idempotencyKey: "key-1" });

    expect(result).toEqual({ done: true });
    expect(keys).toEqual(["key-1", "key-1"]);
  });

  it("does not repeat a POST without an Idempotency-Key", async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const client = new ApiClient({ baseUrl: "", store: memoryStore(), lock: noLock, retryDelayMs: 1, fetch: fetchMock });

    await expect(client.request("POST", "/quests", { auth: false, body: {} })).rejects.toMatchObject({
      code: "network_error",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("expires the session when the refresh token is rejected", async () => {
    const fetchMock = vi.fn(async () => json(401, { error: { code: "refresh_token_reused", message: "reused" } }));
    const store = memoryStore("revoked");
    const client = new ApiClient({ baseUrl: "", store, lock: noLock, fetch: fetchMock });
    const expired = vi.fn();
    client.onSessionExpired(expired);

    await expect(client.request("GET", "/player/profile")).rejects.toMatchObject({ code: "session_expired" });
    expect(expired).toHaveBeenCalledOnce();
    expect(store.value).toBeNull();
  });

  it("turns error bodies into ApiError with the server code", async () => {
    const fetchMock = vi.fn(async () => json(409, { error: { code: "already_completed", message: "done" } }));
    const client = new ApiClient({ baseUrl: "", store: memoryStore(), lock: noLock, fetch: fetchMock });

    await expect(client.request("POST", "/quests/1/complete", { auth: false })).rejects.toMatchObject({
      status: 409,
      code: "already_completed",
    });
  });
});
