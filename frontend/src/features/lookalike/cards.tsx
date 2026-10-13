/**
 * The small building blocks of the Lookalike Failure Lab: a dataset photo, a look-alike pair, a mistake.
 *
 * In plain words: everything is shown as the actual photos next to the actual numbers. A pair of two
 * DIFFERENT people is called a "different-identity comparison"; a pair of the same person is a "genuine"
 * one. In a mistake card the measured facts ("Observed") and the ideas about why it happened ("Possible
 * causes - hypotheses, not proven") live in two separate blocks, so a reader can never mistake a guess
 * for a finding.
 */
import clsx from "clsx";
import { FlaskConical, Palette } from "lucide-react";
import { AuthImage } from "@/components/ui/AuthImage";
import { Badge } from "@/components/ui/Badge";
import { num } from "@/lib/format";
import { QUALITY_FLAGS } from "@/lib/present";
import { api } from "@/services/api";
import { ScoreBar } from "@/features/reid/ScoreBar";
import type { HardGenuinePair, LabFailure, LabPair } from "@/types/api";

/** A photo from the experiment's dataset, served only because the experiment recorded it. */
export function LabImage({ runId, refPath, alt, className }: { runId: string; refPath: string | null; alt: string; className?: string }) {
  return <AuthImage src={refPath ? api.labImageUrl(runId, refPath) : null} alt={alt} fit="contain" className={clsx("rounded border border-line bg-surface-2", className)} />;
}

function Camera({ camera }: { camera: number | null }) {
  return camera === null ? null : <span className="text-ink-3">camera {camera}</span>;
}

const MODEL_NAME: Record<string, string> = { baseline: "Baseline", improved: "Improved" };

/** Two different people who look alike to the model. */
export function PairCard({ runId, pair, thresholds }: { runId: string; pair: LabPair; thresholds: Record<string, number> }) {
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-lg border border-line bg-surface p-3 shadow-card" aria-label={`Look-alike pair ${pair.rank}: person ${pair.identity_a} and person ${pair.identity_b}`}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold text-ink-3">#{pair.rank} · different people · {pair.split} split</span>
        <div className="flex flex-wrap gap-1.5">
          {pair.similar_clothing_proxy && <Badge tone="info" icon={<Palette aria-hidden className="size-3" />} className="!whitespace-normal">Similar clothing colours</Badge>}
        </div>
      </header>

      <div className="grid grid-cols-2 gap-2">
        {([["A", pair.identity_a, pair.image_a, pair.camera_a], ["B", pair.identity_b, pair.image_b, pair.camera_b]] as const).map(([side, id, ref, camera]) => (
          <figure key={side} className="min-w-0 space-y-1">
            <LabImage runId={runId} refPath={ref} alt={`Person ${id}, photo ${side}`} className="aspect-[1/2] max-h-60 w-full" />
            <figcaption className="text-xs"><span className="font-mono font-semibold">{id}</span> <Camera camera={camera} /></figcaption>
          </figure>
        ))}
      </div>

      <div className="space-y-2">
        {Object.entries(pair.by_model).map(([name, view]) => {
          const falseAccept = view.decision === "false_accept";
          return (
            <div key={name} className="space-y-1">
              <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-xs">
                <span className="font-medium">{MODEL_NAME[name] ?? name}: similarity <b className="tabular">{num(view.similarity)}</b></span>
                {falseAccept ? <Badge tone="bad" className="!whitespace-normal">Would be ACCEPTED (false accept)</Badge> : <Badge tone="ok" className="!whitespace-normal">Correctly rejected</Badge>}
              </div>
              <ScoreBar score={view.similarity} threshold={thresholds[name] ?? null} tone={falseAccept ? "bad" : "neutral"} />
            </div>
          );
        })}
        <p className="text-xs text-ink-3">
          Model similarity and clothing-colour similarity ({num(pair.clothing_colour_similarity, 2)}) are measured separately: look-alike embeddings do not prove identical clothing.
        </p>
      </div>
    </article>
  );
}

/** Two photos of the SAME person that the model finds hard to connect. */
export function HardGenuineCard({ runId, pair, threshold }: { runId: string; pair: HardGenuinePair; threshold: number }) {
  const rejected = pair.decision === "false_reject";
  return (
    <article className="flex min-w-0 flex-col gap-2 rounded-lg border border-line bg-surface p-3 shadow-card" aria-label={`Same person ${pair.identity}, two photos`}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold text-ink-3">same person <span className="font-mono">{pair.identity}</span></span>
        {rejected ? <Badge tone="warn" className="!whitespace-normal">Would be rejected (false reject)</Badge> : <Badge tone="ok">Accepted</Badge>}
      </header>
      <div className="grid grid-cols-2 gap-2">
        {([[pair.image_a, pair.camera_a], [pair.image_b, pair.camera_b]] as const).map(([ref, camera], i) => (
          <figure key={i} className="min-w-0 space-y-1">
            <LabImage runId={runId} refPath={ref} alt={`Person ${pair.identity}, photo ${i + 1}`} className="aspect-[1/2] max-h-48 w-full" />
            <figcaption className="text-xs"><Camera camera={camera} /></figcaption>
          </figure>
        ))}
      </div>
      <p className="text-xs">similarity <b className="tabular">{num(pair.similarity)}</b></p>
      <ScoreBar score={pair.similarity} threshold={threshold} tone={rejected ? "bad" : "ok"} />
    </article>
  );
}

const CATEGORY_TONE = { incorrect_acceptance: "bad", wrong_identity_accepted: "bad", genuine_rejected: "warn" } as const;

function Fact({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-1 text-xs last:border-0">
      <dt className="text-ink-3">{term}</dt>
      <dd className="text-right font-medium tabular">{children}</dd>
    </div>
  );
}

/** One real mistake of the matcher, with what was measured and what might explain it. */
export function FailureCard({ runId, failure }: { runId: string; failure: LabFailure }) {
  const o = failure.observed;
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-lg border border-line bg-surface p-3 shadow-card" aria-label={`${failure.category_label} ${failure.id}`}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <Badge tone={CATEGORY_TONE[failure.category]} className="!whitespace-normal">{failure.category_label}</Badge>
        <span className="font-mono text-xs text-ink-3">{failure.id}</span>
      </header>

      <div className="grid grid-cols-2 gap-2">
        <figure className="min-w-0 space-y-1">
          <LabImage runId={runId} refPath={failure.query.ref} alt={`Query photo of ${failure.query.is_known ? `enrolled person ${failure.query.identity}` : "a stranger"}`} className="aspect-[1/2] max-h-52 w-full" />
          <figcaption className="text-xs"><b>Query</b> · {failure.query.is_known ? <>enrolled <span className="font-mono">{failure.query.identity}</span></> : <>stranger <span className="font-mono">{failure.query.identity}</span></>} <Camera camera={failure.query.camera} /></figcaption>
        </figure>
        <figure className="min-w-0 space-y-1">
          <LabImage runId={runId} refPath={failure.matched.ref} alt={`Enrolled photo of ${failure.matched.identity} that matched best`} className="aspect-[1/2] max-h-52 w-full" />
          <figcaption className="text-xs"><b>Matcher picked</b> · <span className="font-mono">{failure.matched.identity}</span> <Camera camera={failure.matched.camera} /></figcaption>
        </figure>
      </div>

      <section aria-label="Observed measurements">
        <h4 className="mb-1 text-xs font-semibold tracking-wide text-ink-2 uppercase">Observed (measured)</h4>
        <dl>
          <Fact term="Outcome">{o.outcome === "accepted" ? "MATCH" : o.outcome === "review_required" ? "REVIEW" : "UNKNOWN"}</Fact>
          <Fact term="Similarity to the pick">{num(o.top1_score)} <span className="font-normal text-ink-3">(threshold {num(o.threshold)}, {o.score_minus_threshold >= 0 ? "+" : "−"}{Math.abs(o.score_minus_threshold).toFixed(3)})</span></Fact>
          <Fact term="Lead over the runner-up">{o.margin === null ? "—" : num(o.margin)}{o.min_margin !== null && <span className="font-normal text-ink-3"> (rule: ≥ {num(o.min_margin)})</span>}</Fact>
          {failure.query.is_known && <Fact term="True person ranked">{o.true_identity_rank ? `#${o.true_identity_rank}` : "—"}{o.true_identity_score !== null && <span className="font-normal text-ink-3"> (score {num(o.true_identity_score)})</span>}</Fact>}
          <Fact term="Image quality">{o.quality_flags.length ? o.quality_flags.map((f) => QUALITY_FLAGS[f] ?? f).join(", ") : "no problems flagged"} <span className="font-normal text-ink-3">(sharpness {o.sharpness.toFixed(0)})</span></Fact>
          <Fact term="Clothing-colour similarity">{o.clothing_colour_similarity === null ? "—" : num(o.clothing_colour_similarity, 2)}</Fact>
        </dl>
      </section>

      <section aria-label="Possible causes, not proven">
        <h4 className="mb-1 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ink-2 uppercase"><FlaskConical aria-hidden className="size-3.5" />Possible causes <span className="font-normal text-ink-3 normal-case">· hypotheses, not proven</span></h4>
        <ul className="space-y-1.5">
          {failure.possible_causes.map((c) => (
            <li key={c.cause} className="rounded-md bg-surface-2 p-2 text-xs">
              <p className="font-medium">{c.text}</p>
              <p className="mt-0.5 text-ink-3">Evidence: {c.evidence}</p>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}
