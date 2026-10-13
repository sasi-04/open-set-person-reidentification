/**
 * Sidebar navigation.
 *
 * Desktop (>= 1024px): full sidebar with labels.
 * Tablet (768-1023px): icon rail (labels are in the tooltip and the accessible name).
 * Phone (< 768px): the same list is shown in a slide-over drawer opened from the top bar.
 *
 * There is ONE navigation list; CSS only decides whether the text labels are visible. (Two copies
 * would give screen readers two identical "Main" landmarks.)
 */
import clsx from "clsx";
import { NavLink } from "react-router-dom";
import { Brand } from "./Brand";
import { NAV_ITEMS } from "./navigation";

/** ``expanded`` = always show the labels (the phone drawer); otherwise labels appear from 1024px up. */
export function NavList({ onNavigate, expanded = false }: { onNavigate?: () => void; expanded?: boolean }) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5 px-3">
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          onClick={onNavigate}
          title={item.label}
          aria-label={item.label}
          className={({ isActive }) =>
            clsx(
              "relative flex min-h-10 items-center rounded-md text-sm font-medium transition-colors",
              expanded ? "gap-3 px-3" : "justify-center px-0 lg:justify-start lg:gap-3 lg:px-3",
              isActive ? "bg-nav-active text-nav-ink" : "text-nav-ink-2 hover:bg-nav-active hover:text-nav-ink",
            )
          }
        >
          {({ isActive }) => (
            <>
              {isActive && <span aria-hidden className="absolute top-2 bottom-2 left-0 w-0.5 rounded-full bg-brand" />}
              {item.icon}
              <span className={expanded ? undefined : "hidden lg:inline"}>{item.label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

export function SidebarFooter() {
  return (
    <p className="px-6 text-[11px] leading-snug text-nav-ink-2">
      <span className="font-medium text-nav-ink">Know when to match. Know when to reject.</span> Independent technical prototype responding to the
      Zed Digital PS-1 assignment; not an official Zed Digital product and not endorsed by them. Not a production surveillance or
      identity-verification service.
    </p>
  );
}

/** The always-visible sidebar for tablet and desktop. */
export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-dvh flex-col border-r border-nav-line bg-nav md:flex">
      <div className="flex h-16 items-center px-4 lg:px-6">
        <span className="lg:hidden">
          <Brand compact />
        </span>
        <span className="hidden lg:block">
          <Brand />
        </span>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        <NavList />
      </div>
      <div className="hidden pb-5 lg:block">
        <SidebarFooter />
      </div>
    </aside>
  );
}
