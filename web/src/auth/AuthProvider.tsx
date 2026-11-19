import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, client } from "../api/endpoints";
import type { RegisterData } from "../api/types";

type Status = "loading" | "authenticated" | "anonymous" | "unreachable";

interface Auth {
  status: Status;
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => Promise<void>;
  retry: () => void;
}

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>(() => (client.hasStoredSession() ? "loading" : "anonymous"));
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!client.hasStoredSession()) {
      setStatus("anonymous");
      return;
    }
    let cancelled = false;
    setStatus("loading");
    client
      .restoreSession()
      .then((ok) => !cancelled && setStatus(ok ? "authenticated" : "anonymous"))
      .catch(() => !cancelled && setStatus("unreachable"));
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  useEffect(
    () =>
      client.onSessionExpired(() => {
        queryClient.clear();
        setStatus("anonymous");
      }),
    [queryClient],
  );

  const login = useCallback(async (email: string, password: string) => {
    client.setSession(await api.login(email, password));
    setStatus("authenticated");
  }, []);

  const register = useCallback(async (data: RegisterData) => {
    client.setSession(await api.register(data));
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = client.getRefreshToken();
    if (refreshToken) {
      await api.logout(refreshToken).catch(() => undefined);
    }
    client.clearSession();
    queryClient.clear();
    setStatus("anonymous");
  }, [queryClient]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  const value = useMemo(() => ({ status, login, register, logout, retry }), [status, login, register, logout, retry]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
