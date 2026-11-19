import "./styles.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { ApiError } from "./api/client";
import { App } from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import { FeedbackProvider } from "./components/Feedback";
import { I18nProvider } from "./i18n";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      // Client errors (4xx) will not fix themselves; network and server errors may.
      retry: (failureCount, error) =>
        failureCount < 2 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
    },
    mutations: { retry: false },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing");

createRoot(root).render(
  <StrictMode>
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <FeedbackProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </FeedbackProvider>
      </QueryClientProvider>
    </I18nProvider>
  </StrictMode>,
);
