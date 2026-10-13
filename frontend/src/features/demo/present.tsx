/**
 * How the example's verdicts and groups are shown.
 *
 * In plain words: every decision in the example is marked "right", "sent to a person", or one of the ways it can be wrong
 * (a stranger accepted, the wrong person named, a known person missed). Each verdict has a fixed icon, colour and wording;
 * colour is never the only signal.
 */
import { CheckCircle2, CircleAlert, Eye, ShieldAlert, UserX, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import type { Tone } from "@/lib/present";
import type { DemoVerdict } from "@/types/api";

export const VERDICT_META: Record<DemoVerdict, { label: string; tone: Tone; icon: ReactNode; wrong: boolean }> = {
  correct: { label: "Right answer", tone: "ok", icon: <CheckCircle2 aria-hidden className="size-3.5" />, wrong: false },
  review: { label: "Sent to a person", tone: "warn", icon: <Eye aria-hidden className="size-3.5" />, wrong: false },
  cautious: { label: "Not accepted (a person should look)", tone: "warn", icon: <Eye aria-hidden className="size-3.5" />, wrong: false },
  false_accept: { label: "Stranger accepted", tone: "bad", icon: <ShieldAlert aria-hidden className="size-3.5" />, wrong: true },
  wrong_person: { label: "Wrong person named", tone: "bad", icon: <XCircle aria-hidden className="size-3.5" />, wrong: true },
  missed: { label: "Known person missed", tone: "bad", icon: <UserX aria-hidden className="size-3.5" />, wrong: true },
  risky: { label: "Accepted on clothes alone", tone: "warn", icon: <CircleAlert aria-hidden className="size-3.5" />, wrong: true },
};

/** Short names of the example's groups, for row labels (the manifest's full titles are used everywhere else). */
export const GROUP_SHORT: Record<string, string> = {
  known: "Known people",
  no_face: "Known, no usable face",
  stranger: "Strangers",
  lookalike: "Strangers in the same clothes",
};

/** Colour of the dots in the score plot, by group. Position, not colour, carries the meaning; the colour only helps the eye. */
export const GROUP_DOT: Record<string, string> = {
  known: "bg-ok",
  no_face: "bg-info",
  stranger: "bg-neutral",
  lookalike: "bg-bad",
};
