/**
 * Top bar: current module, backend/model readiness, device, theme and (only when access keys are on) role.
 */
import * as RadixDialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { CheckCircle2, CircleHelp, Cpu, Menu, Moon, ServerOff, Sun, TriangleAlert, X, XCircle } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { useSession } from "@/hooks/useSession";
import { useTheme } from "@/hooks/useTheme";
import { api, keys } from "@/services/api";
import { Brand } from "./Brand";
import { titleFor } from "./navigation";
import { NavList, SidebarFooter } from "./Sidebar";

/** Polls /api/readiness so the indicator reflects reality, including "the backend is not running". */
function ReadinessIndicator() {
  const { data, isError } = useQuery({ queryKey: keys.readiness, queryFn: api.readiness, refetchInterval: 15_000, retry: false });

  let tone = "text-ink-2";
  let icon = <CheckCircle2 aria-hidden className="size-4 text-ok" />;
  let text = "Checking";
  let detail = "Checking backend status";
  if (isError) {
    icon = <ServerOff aria-hidden className="size-4 text-bad" />;
    text = "Backend offline";
    detail = "The backend did not answer. Start it with the commands in the README.";
    tone = "text-bad";
  } else if (data?.status === "ready") {
    text = "Models ready";
    detail = "Embedding model and person detector are loaded.";
  } else if (data?.status === "degraded") {
    icon = <TriangleAlert aria-hidden className="size-4 text-warn" />;
    text = "Detector missing";
    detail = String(data.components.detector.error ?? "The person detector is not loaded: use crop mode.");
  } else if (data?.status === "not_ready") {
    icon = <XCircle aria-hidden className="size-4 text-bad" />;
    text = "Model not loaded";
    detail = String(data.components.embedding_model.error ?? "The embedding model is not loaded.");
    tone = "text-bad";
  }

  return (
    <Link to="/settings?tab=system" title={detail} className={clsx("flex h-9 items-center gap-1.5 rounded-full border border-line bg-surface px-3 text-xs font-medium hover:bg-surface-2", tone)}>
      {icon}
      <span className="hidden sm:inline">{text}</span>
      <span className="sr-only sm:hidden">{text}. {detail}</span>
    </Link>
  );
}

function DeviceChip() {
  const { data } = useQuery({ queryKey: keys.readiness, queryFn: api.readiness, refetchInterval: 15_000, retry: false });
  const device = data?.components.device as { type?: string; name?: string } | undefined;
  if (!device?.type || device.type === "unavailable") return null;
  const label = device.type === "cuda" ? "GPU" : "CPU";
  return (
    <span title={`Inference device: ${device.name ?? label}`} className="hidden h-9 items-center gap-1.5 rounded-full border border-line bg-surface px-3 text-xs font-medium text-ink-2 sm:flex">
      <Cpu aria-hidden className="size-4" />
      {label}
    </span>
  );
}

function MobileMenu() {
  const [open, setOpen] = useState(false);
  return (
    <RadixDialog.Root open={open} onOpenChange={setOpen}>
      <RadixDialog.Trigger asChild>
        <Button variant="ghost" aria-label="Open navigation menu" className="md:hidden !px-2.5">
          <Menu aria-hidden className="size-5" />
        </Button>
      </RadixDialog.Trigger>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-[var(--overlay)] md:hidden" />
        <RadixDialog.Content className="animate-fade-in fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col bg-nav py-3 md:hidden">
          <RadixDialog.Title className="sr-only">Navigation</RadixDialog.Title>
          <RadixDialog.Description className="sr-only">Choose a module</RadixDialog.Description>
          <div className="mb-2 flex h-12 items-center justify-between px-4">
            <Brand />
            <RadixDialog.Close asChild>
              <button type="button" aria-label="Close navigation menu" className="rounded-md p-2 text-nav-ink-2 hover:text-nav-ink">
                <X aria-hidden className="size-5" />
              </button>
            </RadixDialog.Close>
          </div>
          <div className="flex-1 overflow-y-auto">
            <NavList expanded onNavigate={() => setOpen(false)} />
          </div>
          <SidebarFooter />
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}

export function Topbar() {
  const { pathname } = useLocation();
  const { theme, toggle } = useTheme();
  const { role, authRequired } = useSession();
  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-2 border-b border-line bg-surface/95 px-3 backdrop-blur sm:px-6">
      <MobileMenu />
      <div className="min-w-0 flex-1">
        <p className="hidden text-[11px] font-medium tracking-wide text-ink-3 uppercase sm:block">OpenID Vision</p>
        <p className="truncate font-display text-[15px] leading-5 font-semibold sm:text-base" aria-live="polite">
          {titleFor(pathname)}
        </p>
      </div>
      <Link to="/how-it-works" title="A plain-language tour of what this system does" className="flex h-9 items-center gap-1.5 rounded-full border border-line bg-surface px-3 text-xs font-medium text-ink-2 hover:bg-surface-2">
        <CircleHelp aria-hidden className="size-4" />
        <span className="hidden sm:inline">How it works</span>
        <span className="sr-only sm:hidden">How it works</span>
      </Link>
      <ReadinessIndicator />
      <DeviceChip />
      <Button variant="secondary" onClick={toggle} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} className="!size-9 !px-0">
        {theme === "dark" ? <Sun aria-hidden className="size-4" /> : <Moon aria-hidden className="size-4" />}
      </Button>
      {authRequired && (
        <Link to="/settings" title="Your access role" className="hidden h-9 items-center rounded-full bg-ink px-3 text-xs font-medium text-canvas capitalize sm:flex">
          {role}
        </Link>
      )}
    </header>
  );
}
