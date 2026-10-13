import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ToastProvider } from "./components/ui/Toast";
import "./styles/index.css";

// After the application is updated, a browser tab that was already open still asks for the OLD screen files, which
// no longer exist. Vite reports that as "vite:preloadError"; reloading once fetches the new files. The guard stops
// a reload loop if something else is wrong (for example the server is down).
window.addEventListener("vite:preloadError", (event) => {
  event.preventDefault();
  try {
    if (sessionStorage.getItem("reloaded-after-update") === "1") return;
    sessionStorage.setItem("reloaded-after-update", "1");
  } catch {
    return; // no storage: do not risk a reload loop
  }
  window.location.reload();
});

// Data is fetched fresh when you navigate; failed requests are not silently retried,
// so an error is shown (with a "Try again" button) instead of hiding behind a spinner.
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 10_000 } },
});

// A page that has stayed up for a while is healthy: allow a future update to trigger its one-time reload again.
setTimeout(() => {
  try {
    sessionStorage.removeItem("reloaded-after-update");
  } catch {
    /* storage unavailable: nothing to clear */
  }
}, 15_000);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
