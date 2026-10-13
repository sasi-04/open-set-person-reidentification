/**
 * One example photo and what each matcher decided about it.
 *
 * In plain words: on the left the photo and the right answer; in the middle what the system (face + body) decided; on the right
 * what a clothes-only matcher would have decided. Every answer carries its badge (MATCH / UNKNOWN / REVIEW), whether it was
 * right, and the similarity it was based on, drawn against the number it needed to reach.
 */
import { AuthImage } from "@/components/ui/AuthImage";
import { Badge, OutcomeBadge } from "@/components/ui/Badge";
import { FACE_STATUS } from "@/lib/present";
import { ScoreBar } from "@/features/reid/ScoreBar";
import type { DemoCase, DemoCaseResult, DemoDecision } from "@/types/api";
import { VERDICT_META } from "./present";
import { plain } from "./summary";

export type RowState = "idle" | "waiting" | "done";

function ScoreLine({ decision }: { decision: DemoDecision }) {
  const byFace = decision.basis === "face" && decision.face_score !== null;
  const score = byFace ? decision.face_score : decision.top1_score;
  if (score === null || score === undefined) return null;
  const accepted = decision.outcome === "accepted";
  const tone = accepted ? (decision.verdict === "correct" ? "ok" : "bad") : "neutral";
  return (
    <div className="space-y-1">
      <p className="text-xs text-ink-2">
        {byFace ? "Face" : "Clothes and build"} similarity <span className="font-mono font-medium">{score.toFixed(2)}</span>
        {decision.threshold !== null && <span className="text-ink-3"> (needs {plain(decision.threshold)} to match)</span>}
        {byFace && decision.body_score !== null && <span className="text-ink-3"> · clothes {decision.body_score.toFixed(2)}</span>}
      </p>
      <ScoreBar score={score} threshold={decision.threshold} tone={tone} />
    </div>
  );
}

function Answer({ decision }: { decision: DemoDecision }) {
  const verdict = VERDICT_META[decision.verdict];
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <OutcomeBadge outcome={decision.outcome} short />
        <Badge tone={verdict.tone} icon={verdict.icon}>{verdict.label}</Badge>
      </div>
      {decision.accepted_label && <p className="text-xs text-ink-2">Named: <span className="font-medium text-ink">{decision.accepted_label}</span></p>}
      <ScoreLine decision={decision} />
      <details className="text-xs text-ink-3">
        <summary className="cursor-pointer select-none hover:text-ink">Why this answer</summary>
        <p className="mt-1 text-ink-2">{decision.reason}</p>
      </details>
    </div>
  );
}

function Cell({ label, decision, state }: { label: string; decision: DemoDecision | undefined; state: RowState }) {
  return (
    <div className="min-w-0">
      <p className="mb-1 text-[11px] font-semibold tracking-wide text-ink-3 uppercase lg:hidden">{label}</p>
      {decision ? <Answer decision={decision} /> : <p className="text-xs text-ink-3">{state === "waiting" ? "Analysing…" : "Not run yet"}</p>}
    </div>
  );
}

/** The correct answer in a few words (the server's longer sentence is in `item.expect.text`). */
function rightAnswer(item: DemoCase): string {
  const who = item.expect.person_label ?? "";
  if (item.expect.kind === "match") return `MATCH ${who}`;
  if (item.expect.kind === "unknown") return "UNKNOWN - this person was never enrolled";
  return `REVIEW - ${who} is enrolled, but no face can be checked`;
}

export const ROW_COLUMNS = "lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)]";

export function CaseRow({ item, result, state }: { item: DemoCase; result: DemoCaseResult | undefined; state: RowState }) {
  const face = result?.face ? FACE_STATUS[result.face.status] : null;
  return (
    <li className={`grid gap-3 py-3 ${ROW_COLUMNS}`} data-case={item.id}>
      <div className="flex min-w-0 gap-3">
        <AuthImage src={item.image_url} alt={`Example photo: ${item.title}`} className="h-24 w-[4.5rem] shrink-0 rounded-md border border-line object-top" />
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-medium">{item.title}</p>
          <p className="text-xs text-ink-3">{item.story}</p>
          <p className="text-xs text-ink-2"><span className="font-medium">Right answer:</span> {rightAnswer(item)}</p>
          {face && <Badge tone={face.tone}>{face.label}</Badge>}
        </div>
      </div>
      <Cell label="Face + body (this system)" decision={result?.face_body} state={state} />
      <Cell label="Clothes only (weaker matcher)" decision={result?.clothes_only} state={state} />
    </li>
  );
}
