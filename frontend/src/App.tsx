/**
 * Application routes.
 *
 * In plain words: seven screens (A-G), all inside the common frame (AppShell):
 *   A Command Center   B Identity Gallery   C Match Studio   D Video Explorer
 *   E Lookalike Failure Lab   F Evaluation Lab   G Model & System Settings
 * plus "Decision history" (reached from inside Match Studio) and "How it works" (a plain-language tour, reached from the top bar). If the server was started with access keys
 * switched on, a key screen comes first; by default it does not. Screens are loaded on demand so the first
 * page opens quickly. Old addresses (/reidentify, /model) still work and forward to their new home.
 */
import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { Spinner } from "@/components/ui/Feedback";
import { ConnectScreen } from "@/features/auth/ConnectScreen";
import { SessionProvider } from "@/hooks/useSession";

const CommandCenterPage = lazy(() => import("@/pages/CommandCenterPage"));
const GalleryPage = lazy(() => import("@/pages/GalleryPage"));
const MatchStudioPage = lazy(() => import("@/pages/MatchStudioPage"));
const VideoPage = lazy(() => import("@/pages/VideoPage"));
const LookalikePage = lazy(() => import("@/pages/LookalikePage"));
const EvaluationPage = lazy(() => import("@/pages/EvaluationPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const HistoryPage = lazy(() => import("@/pages/HistoryPage"));
const HowItWorksPage = lazy(() => import("@/pages/HowItWorksPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));

function Screen({ children }: { children: ReactNode }) {
  return <Suspense fallback={<Spinner label="Loading screen" />}>{children}</Suspense>;
}

export default function App() {
  return (
    <SessionProvider fallback={(problem) => <ConnectScreen {...problem} />}>
      <Routes>
        <Route element={<AppShell />}>
          {/* Each screen loads on demand; the sidebar and top bar stay on screen while it does. */}
          <Route index element={<Screen><CommandCenterPage /></Screen>} />
          <Route path="gallery" element={<Screen><GalleryPage /></Screen>} />
          <Route path="match" element={<Screen><MatchStudioPage /></Screen>} />
          <Route path="video" element={<Screen><VideoPage /></Screen>} />
          <Route path="lookalike" element={<Screen><LookalikePage /></Screen>} />
          <Route path="evaluation" element={<Screen><EvaluationPage /></Screen>} />
          <Route path="settings" element={<Screen><SettingsPage /></Screen>} />
          <Route path="history" element={<Screen><HistoryPage /></Screen>} />
          <Route path="how-it-works" element={<Screen><HowItWorksPage /></Screen>} />
          <Route path="reidentify" element={<Navigate to="/match" replace />} />
          <Route path="model" element={<Navigate to="/settings?tab=model" replace />} />
          <Route path="*" element={<Screen><NotFoundPage /></Screen>} />
        </Route>
      </Routes>
    </SessionProvider>
  );
}
