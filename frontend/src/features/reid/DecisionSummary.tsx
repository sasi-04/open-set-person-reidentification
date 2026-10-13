/**
 * DecisionSummary: the outcome for one person, with the real numbers behind it.
 *
 * In plain words: this panel never shows a "confidence %" made up from a similarity.
 * It shows the similarity, the threshold it was compared with, the margin to the
 * runner-up, and - only if a calibration was applied - a separately labelled calibrated
 * confidence. An unknown or review outcome looks like exactly that; it is never dressed
 * up as a success.
 */
import { Link } from "react-router-dom";
import { Badge, OutcomeBadge, PolicyBadge } from "@/components/ui/Badge";
import { InfoTip } from "@/components/ui/InfoTip";
import { num, ms, pct } from "@/lib/format";
import { OUTCOME_META, QUALITY_FLAGS } from "@/lib/present";
import type { PersonResult, PredictResponse, PolicyStatus } from "@/types/api";
import { ScoreBar } from "./ScoreBar";

function Metric({ label, children, tip }: { label: string; children: React.ReactNode; tip?: string }) {
  return (
    <div className="rounded-md bg-surface-2 p-3">
      <div className="flex items-center gap-1.5 text-xs text-ink-3">
        {label}
        {tip && <InfoTip label={`About ${label}`}>{tip}</InfoTip>}
      </div>
      <div className="mt-0.5 text-sm font-medium">{children}</div>
    </div>
  );
}

export function DecisionSummary({ person, response, total }: { person: PersonResult; response: PredictResponse; total: number }) {
  const decision = person.decision;
  const meta = OUTCOME_META[decision.outcome];
  const hasScore = decision.top1_score !== null;
  const accepted = decision.outcome === "accepted";
  const byFace = decision.matching_mode === "face_body" && decision.basis === "face";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <OutcomeBadge outcome={decision.outcome} />
        {total > 1 && <span className="text-xs text-ink-3">Person {person.index + 1} of {total}</span>}
      </div>

      <div className="space-y-1.5">
        <p className="text-sm">{decision.reason}</p>
        <p className="text-xs text-ink-3">{meta.blurb}</p>
      </div>

      {accepted && decision.accepted_reference_id && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-ok/40 bg-ok-bg p-3 text-sm">
          <div>
            <div className="text-xs text-ok">Selected reference ID</div>
            <div className="font-mono font-semibold break-all">{decision.accepted_reference_id}</div>
          </div>
          <Link className="text-sm font-medium underline" to={`/gallery?ref=${encodeURIComponent(decision.accepted_reference_id)}`}>
            View gallery entry
          </Link>
        </div>
      )}

      {hasScore && (
        <div>
          <div className="mb-1.5 flex items-end justify-between text-sm">
            <span className="flex items-center gap-1.5 font-medium">
              {byFace ? "Face similarity" : "Similarity"}
              <InfoTip label="About similarity">
                {byFace
                  ? "Cosine similarity between the face in the query and the closest enrolled face (−1 to 1). It is a retrieval score, not a probability. The face decides whenever a usable face is visible."
                  : "Cosine similarity between the query embedding and the closest enrolled identity (−1 to 1). It is a retrieval score, not a probability."}
              </InfoTip>
            </span>
            <span className="font-display text-xl font-semibold tabular">{num(decision.top1_score)}</span>
          </div>
          <ScoreBar score={decision.top1_score as number} threshold={decision.accept_threshold} accepted={accepted} />
          <p className="mt-1 text-xs text-ink-3">The black tick marks the acceptance threshold ({num(decision.accept_threshold)}).</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <Metric label={byFace ? "Face threshold" : "Threshold"} tip={byFace ? "The best face similarity must reach this value for the face to support a MATCH." : "The top-1 similarity must reach this value to be accepted."}>
          <span className="tabular">{num(decision.accept_threshold)}</span> <PolicyBadge status={decision.policy_status as PolicyStatus} />
        </Metric>
        <Metric label="Margin (top-1 − top-2)" tip="How far the best candidate leads the runner-up. A small margin means an ambiguous match.">
          <span className="tabular">{num(decision.margin)}</span>
          {decision.min_margin !== null && <span className="text-xs font-normal text-ink-3"> (min {num(decision.min_margin, 2)})</span>}
        </Metric>
        <Metric label="Calibrated confidence" tip="Estimated chance that an accepted match is correct, from a fitted calibration model. Shown only when one has been applied.">
          {decision.calibrated_confidence !== null ? pct(decision.calibrated_confidence) : <span className="text-ink-3">Not available</span>}
        </Metric>
        <Metric label="Detector confidence" tip="How sure the person detector is that this box contains a person. Unrelated to identity.">
          {person.detector_score !== null ? <span className="tabular">{num(person.detector_score, 2)}</span> : <span className="text-ink-3">n/a (no detection)</span>}
        </Metric>
        <Metric label="Model">{response.model.architecture}</Metric>
        <Metric label="Inference time" tip="Measured on the server for the whole request (detection, embedding, retrieval, decision).">
          <span className="tabular">{ms(response.timings_ms.total_ms)}</span>
        </Metric>
      </div>

      {(decision.quality_flags.length > 0 || person.quality?.blocking_reason) && (
        <div className="flex flex-wrap gap-1.5">
          {person.quality?.blocking_reason && <Badge tone="bad">{person.quality.blocking_reason}</Badge>}
          {decision.quality_flags.map((flag) => (
            <Badge key={flag} tone="warn">
              {QUALITY_FLAGS[flag] ?? flag}
            </Badge>
          ))}
        </div>
      )}

      <p className="text-xs text-ink-3">
        Policy v{decision.policy_version} · request <span className="font-mono">{response.request_id}</span>
      </p>
      {response.notes.map((note) => (
        <p key={note} className="text-xs text-ink-3">{note}</p>
      ))}
    </div>
  );
}
