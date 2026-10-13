/**
 * ReviewDialog: compare the query person with each candidate, side by side.
 *
 * In plain words: used when the outcome is "review required". It crops the query
 * person out of the uploaded image (with CSS, no canvas) and shows each candidate's
 * closest reference photo next to it. It only helps a person look - nothing is saved,
 * enrolled or merged by viewing it.
 */
import { AuthImage } from "@/components/ui/AuthImage";
import { Dialog } from "@/components/ui/Dialog";
import { Notice } from "@/components/ui/Feedback";
import { num } from "@/lib/format";
import type { PersonResult } from "@/types/api";

export function CroppedView({ src, box, size, className }: { src: string; box: number[] | null; size: { width: number; height: number } | null; className?: string }) {
  if (!box || !size) {
    return <img src={src} alt="Query person" className={className} />;
  }
  const [x1, y1, x2, y2] = box;
  const w = x2 - x1;
  const h = y2 - y1;
  const style = {
    aspectRatio: `${w} / ${h}`,
    backgroundImage: `url(${src})`,
    backgroundRepeat: "no-repeat",
    backgroundSize: `${(size.width / w) * 100}% ${(size.height / h) * 100}%`,
    backgroundPosition: `${size.width === w ? 0 : (x1 / (size.width - w)) * 100}% ${size.height === h ? 0 : (y1 / (size.height - h)) * 100}%`,
  };
  return <div role="img" aria-label="Query person (cropped from your upload)" style={style} className={className} />;
}

export function ReviewDialog({
  open,
  onOpenChange,
  person,
  imageUrl,
  size,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  person: PersonResult;
  imageUrl: string;
  size: { width: number; height: number } | null;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} size="lg" title="Review candidates" description="Compare the query person with each candidate. This view does not change anything.">
      <Notice tone="warn" title="A person must decide">
        {person.decision.reason} Compare clothing, build and accessories. Resemblance is not proof of identity.
      </Notice>
      <div className="mt-4 grid gap-4 sm:grid-cols-[minmax(0,10rem)_1fr]">
        <div>
          <p className="mb-1.5 text-xs font-semibold text-ink-3 uppercase">Query</p>
          <CroppedView src={imageUrl} box={person.box} size={size} className="w-full rounded-md border border-line bg-surface-2 object-contain" />
        </div>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {person.candidates.map((candidate) => (
            <li key={candidate.reference_id} className="rounded-md border border-line p-2">
              <AuthImage src={candidate.image_url} alt={`Closest reference of ${candidate.reference_id}`} fit="contain" className="aspect-[1/2] w-full rounded bg-surface-2" />
              <p className="mt-1.5 font-mono text-xs font-semibold break-all">#{candidate.rank} {candidate.reference_id}</p>
              <p className="text-xs text-ink-3">similarity {num(candidate.score)}</p>
            </li>
          ))}
        </ul>
      </div>
    </Dialog>
  );
}
