/** The page frame: sidebar + top bar + the routed screen. */
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell() {
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[72px_minmax(0,1fr)] lg:grid-cols-[256px_minmax(0,1fr)]">
      {/* Lets keyboard users jump past the navigation. */}
      <a href="#main" className="sr-only z-50 rounded-md bg-ink px-3 py-2 text-canvas focus:not-sr-only focus:fixed focus:top-2 focus:left-2">
        Skip to main content
      </a>
      <Sidebar />
      <div className="flex min-h-dvh min-w-0 flex-col">
        <Topbar />
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1400px] flex-1 px-3 py-5 outline-none sm:px-6 sm:py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
