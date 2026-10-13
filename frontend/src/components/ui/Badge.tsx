/**
 * Badges: small status labels.
 *
 * In plain words: a badge always shows an icon AND text, never colour alone, so it
 * reads correctly in grayscale, for colour-blind readers, and in forced-colours mode.
 */
import clsx from "clsx";
import type { ReactNode } from "react";
import { OUTCOME_META, POLICY_META, TONE_CLASSES, type Tone } from "@/lib/present";
import type { Outcome, PolicyStatus } from "@/types/api";

export function Badge({ tone = "neutral", icon, children, className }: { tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <span className={clsx("badge inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap", TONE_CLASSES[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

export function OutcomeBadge({ outcome, short = false }: { outcome: Outcome; short?: boolean }) {
  const meta = OUTCOME_META[outcome];
  return (
    <Badge tone={meta.tone} icon={meta.icon} className="tracking-wide uppercase">
      {short ? meta.short : meta.label}
    </Badge>
  );
}

export function PolicyBadge({ status }: { status: PolicyStatus }) {
  const meta = POLICY_META[status];
  return (
    <Badge tone={meta.tone} icon={meta.icon}>
      {meta.label}
    </Badge>
  );
}
