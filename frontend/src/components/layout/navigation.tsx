import { Film, FlaskConical, GitCompareArrows, LayoutDashboard, ScanSearch, SlidersHorizontal, Users } from "lucide-react";
import type { ReactNode } from "react";

export interface NavItem {
  to: string;
  label: string;
  title: string;
  icon: ReactNode;
}

const icon = "size-[18px]";

/** The seven screens (A-G), in the order they appear in the sidebar. */
export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Command Center", title: "Command Center", icon: <LayoutDashboard aria-hidden className={icon} /> },
  { to: "/gallery", label: "Identity Gallery", title: "Identity Gallery", icon: <Users aria-hidden className={icon} /> },
  { to: "/match", label: "Match Studio", title: "Match Studio", icon: <ScanSearch aria-hidden className={icon} /> },
  { to: "/video", label: "Video Explorer", title: "Video Explorer", icon: <Film aria-hidden className={icon} /> },
  { to: "/lookalike", label: "Lookalike Failure Lab", title: "Lookalike Failure Lab", icon: <GitCompareArrows aria-hidden className={icon} /> },
  { to: "/evaluation", label: "Evaluation Lab", title: "Evaluation Lab", icon: <FlaskConical aria-hidden className={icon} /> },
  { to: "/settings", label: "Model & System", title: "Model & System Settings", icon: <SlidersHorizontal aria-hidden className={icon} /> },
];

/** Pages reached from inside a screen rather than from the sidebar. */
const EXTRA_TITLES: Record<string, string> = { "/history": "Decision history", "/how-it-works": "How it works" };

export function titleFor(pathname: string): string {
  const extra = Object.entries(EXTRA_TITLES).find(([to]) => pathname.startsWith(to));
  if (extra) return extra[1];
  const match = [...NAV_ITEMS].reverse().find((item) => (item.to === "/" ? pathname === "/" : pathname.startsWith(item.to)));
  return match?.title ?? "Not found";
}
