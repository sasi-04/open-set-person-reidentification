/**
 * Light/dark theme. The graphite (dark) look is the default (set in index.html before the first paint); a person's
 * own choice is remembered on this device (if storage is allowed) and wins.
 */
import { useCallback, useSyncExternalStore } from "react";

const KEY = "reid-theme";
type Theme = "light" | "dark";

function current(): Theme {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

const listeners = new Set<() => void>();

export function useTheme() {
  const theme = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    current,
    () => "light" as Theme,
  );

  const setTheme = useCallback((next: Theme) => {
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* storage blocked: the theme still applies for this visit */
    }
    listeners.forEach((l) => l());
  }, []);

  return { theme, setTheme, toggle: () => setTheme(theme === "dark" ? "light" : "dark") };
}
