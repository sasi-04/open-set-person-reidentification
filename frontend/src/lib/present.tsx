/**
 * How outcomes, policy statuses and quality flags are presented.
 *
 * In plain words: the decision outcomes each get a fixed icon, colour tone and wording.
 * Colour is never the only signal - every badge carries an icon and text. A rejected query
 * is described neutrally ("no supported match"); the interface never implies wrongdoing.
 *
 * Names: the product speaks of MATCH, UNKNOWN and REVIEW (plus PROCESSING ERROR when the input
 * could not be handled at all). The API keeps its stable codes - ``accepted``, ``unknown``,
 * ``review_required``, ``processing_error`` - and this table is the one place that translates
 * them, so a code reviewer can see both vocabularies side by side.
 */
import { AlertTriangle, CheckCircle2, CircleHelp, Eye, FlaskConical, ShieldCheck, ShieldQuestion } from "lucide-react";
import type { ReactNode } from "react";
import type { Outcome, PolicyStatus, Role } from "@/types/api";

export type Tone = "ok" | "warn" | "neutral" | "bad" | "info" | "brand";

export const OUTCOME_META: Record<Outcome, { label: string; short: string; tone: Tone; icon: ReactNode; blurb: string }> = {
  accepted: {
    label: "Match",
    short: "Match",
    tone: "ok",
    icon: <CheckCircle2 aria-hidden className="size-4" />,
    blurb: "A supported enrolled identity passed the acceptance rule. A nearest neighbour alone is never a match.",
  },
  unknown: {
    label: "Unknown",
    short: "Unknown",
    tone: "neutral",
    icon: <CircleHelp aria-hidden className="size-4" />,
    blurb: "No enrolled identity satisfies the acceptance rule (no supported match). This is not a finding about the person.",
  },
  review_required: {
    label: "Review",
    short: "Review",
    tone: "warn",
    icon: <Eye aria-hidden className="size-4" />,
    blurb: "The evidence is ambiguous or the image quality is inadequate: a person should look.",
  },
  processing_error: {
    label: "Processing error",
    short: "Error",
    tone: "bad",
    icon: <AlertTriangle aria-hidden className="size-4" />,
    blurb: "The input could not be processed reliably.",
  },
};

export const POLICY_META: Record<PolicyStatus, { label: string; tone: Tone; icon: ReactNode }> = {
  unvalidated: { label: "Unvalidated", tone: "warn", icon: <ShieldQuestion aria-hidden className="size-3.5" /> },
  experimental: { label: "Experimental", tone: "info", icon: <FlaskConical aria-hidden className="size-3.5" /> },
  calibrated: { label: "Calibrated", tone: "ok", icon: <ShieldCheck aria-hidden className="size-3.5" /> },
};

export const QUALITY_FLAGS: Record<string, string> = {
  low_resolution: "Low resolution",
  unusual_aspect_ratio: "Unusual shape",
  blurry: "Blurry",
  cut_off_by_frame: "Cut off by frame",
  uncertain_detection: "Uncertain detection",
};

/** Why a face could not be used (the backend's flag names, in plain words). */
export const FACE_FLAGS: Record<string, string> = {
  face_small: "Face too small",
  face_blurry: "Face out of focus",
  face_turned: "Face turned away",
  face_low_confidence: "Face not clear",
};

/** What the face analysis concluded about the query picture. */
export const FACE_STATUS: Record<string, { label: string; tone: Tone }> = {
  usable: { label: "Face found and usable", tone: "ok" },
  unusable: { label: "Face found but not usable", tone: "warn" },
  no_face: { label: "No face found", tone: "neutral" },
  not_used: { label: "Face matching off", tone: "neutral" },
};

/** The status of the face in one enrolled reference picture. */
export const REFERENCE_FACE_STATUS: Record<string, { label: string; tone: Tone }> = {
  ready: { label: "Face on file", tone: "ok" },
  weak: { label: "Face unusable", tone: "warn" },
  no_face: { label: "No face found", tone: "neutral" },
  stale: { label: "Face out of date", tone: "warn" },
  failed: { label: "Face analysis failed", tone: "bad" },
  not_analysed: { label: "Faces not analysed", tone: "neutral" },
};

export const ROLE_LEVEL: Record<Role, number> = { viewer: 1, operator: 2, admin: 3 };
export const can = (role: Role | undefined, needed: Role): boolean => !!role && ROLE_LEVEL[role] >= ROLE_LEVEL[needed];

export const TONE_CLASSES: Record<Tone, string> = {
  ok: "bg-ok-bg text-ok",
  warn: "bg-warn-bg text-warn",
  neutral: "bg-neutral-bg text-neutral",
  bad: "bg-bad-bg text-bad",
  info: "bg-info-bg text-info",
  brand: "bg-brand-tint text-brand-ink",
};
