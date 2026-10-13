/**
 * ComparePanel: the query person next to the closest enrolled reference photo.
 *
 * In plain words: the numbers say HOW alike two pictures are; this lets a person SEE them. The query
 * crop is cut out of the uploaded image with CSS (nothing is re-uploaded), and the reference is the
 * enrolled photo that matched best. The similarity under the pictures is a retrieval score, never a
 * probability, and the caption says whether it passed the threshold - a close look-alike is shown
 * exactly like a genuine match, so a person can judge for themselves.
 */
import { AuthImage } from "@/components/ui/AuthImage";
import { OutcomeBadge } from "@/components/ui/Badge";
import { num } from "@/lib/format";
import type { PersonResult } from "@/types/api";
import { CroppedView } from "./ReviewDialog";

export function ComparePanel({ person, imageUrl, size }: { person: PersonResult; imageUrl: string; size: { width: number; height: number } | null }) {
  const best = person.candidates[0];
  if (!best) return null;
  const { decision } = person;
  const passes = decision.accept_threshold !== null && best.score >= decision.accept_threshold;
  return (
    <figure className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="min-w-0 space-y-1.5">
          <p className="text-xs font-semibold text-ink-3 uppercase">Query</p>
          <CroppedView src={imageUrl} box={person.box} size={size} className="max-h-72 w-full rounded-md border border-line bg-surface-2 object-contain" />
        </div>
        <div className="min-w-0 space-y-1.5">
          <p className="text-xs font-semibold text-ink-3 uppercase">Closest enrolled reference</p>
          <AuthImage src={best.image_url} alt={`Closest reference image of ${best.reference_id}`} fit="contain" className="aspect-[1/2] max-h-72 w-full rounded-md border border-line bg-surface-2" />
        </div>
      </div>
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-2">
        <span>
          <span className="font-mono font-semibold">{best.reference_id}</span> · similarity <b className="tabular">{num(best.score)}</b>{" "}
          {decision.accept_threshold !== null && <>{passes ? "reaches" : "is below"} the threshold {num(decision.accept_threshold)}</>}
        </span>
        <OutcomeBadge outcome={decision.outcome} short />
      </figcaption>
      <p className="text-xs text-ink-3">Similarity is a retrieval score, not a probability. Resemblance is not proof of identity - compare clothing and build yourself.</p>
    </figure>
  );
}
