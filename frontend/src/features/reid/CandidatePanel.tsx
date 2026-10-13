/**
 * CandidatePanel: the ranked enrolled identities for the selected person.
 *
 * In plain words: ALL top candidates stay visible. If nothing was accepted, the panel
 * says "no supported match" and calls the first candidate the "closest candidate" - a
 * nearest neighbour is shown for transparency, never presented as an answer.
 */
import clsx from "clsx";
import { Eye } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { AuthImage } from "@/components/ui/AuthImage";
import { EmptyState, Notice } from "@/components/ui/Feedback";
import { num } from "@/lib/format";
import type { PersonResult } from "@/types/api";
import { ScoreBar } from "./ScoreBar";

export function CandidatePanel({ person, onReview }: { person: PersonResult; onReview: () => void }) {
  const { decision, candidates } = person;
  const noSupportedMatch = decision.outcome !== "accepted";

  if (decision.outcome === "processing_error") {
    return <Notice tone="bad" title="No candidates">The crop could not be processed, so nothing was compared with the gallery.</Notice>;
  }
  if (candidates.length === 0) {
    return (
      <EmptyState title="The gallery is empty">
        There is nobody to match against. Enroll an authorised identity in the Identity Gallery first. Any query will be reported as unknown until then.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-3">
      {noSupportedMatch && (
        <Notice tone={decision.outcome === "review_required" ? "warn" : "info"} title={decision.outcome === "review_required" ? "Needs a person to review" : "No supported match"}>
          {decision.outcome === "review_required"
            ? "The candidates below are possibilities, not answers. Compare them before deciding."
            : `No enrolled identity reached the acceptance threshold (${num(decision.accept_threshold)}${decision.basis === "face" ? ", compared by face" : ""}). The candidates below are shown for transparency only.`}
        </Notice>
      )}

      <ol className="space-y-2" aria-label="Ranked candidates">
        {candidates.map((candidate) => {
          const isAccepted = decision.accepted_reference_id === candidate.reference_id;
          // With face matching a person can be scored by face or by body; each is compared with its own threshold.
          const threshold = decision.matching_mode === "face_body" ? (candidate.basis === "face" ? decision.face_threshold : decision.body_threshold) : decision.accept_threshold;
          const below = threshold !== null && candidate.score < threshold;
          const both = candidate.face_score !== null || candidate.body_score !== null;
          return (
            <li
              key={candidate.reference_id}
              aria-current={isAccepted ? "true" : undefined}
              className={clsx("flex gap-3 rounded-md border p-2.5", isAccepted ? "border-ok bg-ok-bg/50" : "border-line")}
            >
              <AuthImage src={candidate.image_url} alt={`Closest reference image of ${candidate.reference_id}`} className="h-20 w-10 shrink-0 rounded sm:h-24 sm:w-12" />
              <div className="min-w-0 flex-1 space-y-1.5">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-xs font-semibold text-ink-3">#{candidate.rank}</span>
                  <span className="font-mono text-sm font-semibold break-all">{candidate.reference_id}</span>
                  {isAccepted && <Badge tone="ok" className="tracking-wide uppercase">Match</Badge>}
                  {!isAccepted && candidate.rank === 1 && noSupportedMatch && <Badge tone="neutral">Closest candidate (not a match)</Badge>}
                  {below && <Badge tone="neutral">Below threshold</Badge>}
                </div>
                {candidate.label && <p className="truncate text-xs text-ink-3">{candidate.label}</p>}
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <ScoreBar score={candidate.score} threshold={threshold} accepted={isAccepted} />
                  </div>
                  <span className="w-12 text-right text-sm font-semibold tabular">{num(candidate.score)}</span>
                </div>
                {decision.matching_mode === "face_body" && both && (
                  <p className="text-xs text-ink-2">
                    <span>{candidate.basis === "face" ? "Scored by face" : "Scored by body (no face on file)"}</span>
                    {" · "}Face <b className="tabular">{candidate.face_score !== null ? num(candidate.face_score) : "—"}</b>
                    {" · "}Body <b className="tabular">{candidate.body_score !== null ? num(candidate.body_score) : "—"}</b>
                  </p>
                )}
                <div className="flex items-center justify-between text-xs text-ink-3">
                  <span>{candidate.n_images ?? "?"} reference {candidate.n_images === 1 ? "image" : "images"}</span>
                  <Link className="underline" to={`/gallery?ref=${encodeURIComponent(candidate.reference_id)}`}>
                    View entry
                  </Link>
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      {decision.outcome === "review_required" && (
        <Button variant="primary" className="w-full" icon={<Eye aria-hidden className="size-4" />} onClick={onReview}>
          Review candidates
        </Button>
      )}
    </div>
  );
}
