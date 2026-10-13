/**
 * Analysis: the open-set picture and a "what if" for the face threshold.
 *
 * In plain words: two plots show where every example photo scored. On the FACE plot the known people sit far to the right and every
 * stranger far to the left, so one line separates them. On the CLOTHES plot strangers dressed like an enrolled person sit
 * on the same side as people the system should accept - no line can separate them. Under the plots, a slider lets you move
 * the face line yourself and see when a stranger would start to be let in, or a known person would start to be missed.
 * Everything is drawn from the numbers the server measured; the slider only counts them.
 */
import { RotateCcw } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import type { DemoCase, DemoCaseResult, DemoRules } from "@/types/api";
import { GROUP_SHORT } from "./present";
import { ScoreStrip, type StripRow } from "./ScoreStrip";
import { faceGap, whatIfFace } from "./summary";

type Results = Record<string, DemoCaseResult | undefined>;

function rowsFor(cases: DemoCase[], results: Results, groups: string[], score: (r: DemoCaseResult) => number | null): StripRow[] {
  return groups.map((group) => ({
    id: group,
    label: GROUP_SHORT[group] ?? group,
    dots: cases.filter((c) => c.group === group).flatMap((c) => {
      const result = results[c.id];
      const value = result ? score(result) : null;
      return value === null ? [] : [{ id: c.id, score: value, title: c.title }];
    }),
  }));
}

const range = (values: number[]) => (values.length ? { min: Math.min(...values), max: Math.max(...values) } : null);

export function Analysis({ cases, results, rules }: { cases: DemoCase[]; results: Results; rules: DemoRules }) {
  const [line, setLine] = useState(rules.face_threshold);
  const faceRows = rowsFor(cases, results, ["known", "stranger", "lookalike"], (r) => r.face_body.face_score);
  const bodyRows = rowsFor(cases, results, ["known", "no_face", "stranger", "lookalike"], (r) => r.clothes_only.body_score);

  const gap = faceGap(cases, results);
  const known = range(bodyRows.find((r) => r.id === "known")?.dots.map((d) => d.score) ?? []);
  const same = range(bodyRows.find((r) => r.id === "lookalike")?.dots.map((d) => d.score) ?? []);
  const what = whatIfFace(cases, results, line);
  const isSystem = Math.abs(line - rules.face_threshold) < 0.0005;
  const strangersLetIn = what.strangerAccepted > 0;
  const knownMissed = what.knownAccepted < what.knownTotal;

  return (
    <div className="space-y-5">
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-2">
          <ScoreStrip
            title="Face similarity"
            explain="Each dot is one photo. Its place is how alike the face in the photo is to the closest enrolled face (0 = nothing alike, 1 = identical). A photo to the right of the dashed line has a face that passes."
            rows={faceRows} threshold={line} thresholdLabel={isSystem ? "Face line" : "Your line"} reviewBand={isSystem ? rules.face_review_band : undefined}
          />
          <p className="text-xs text-ink-2">
            {gap.lowestKnown !== null && gap.highestStranger !== null
              ? gap.lowestKnown > gap.highestStranger
                ? <>Every known person scored at least <b>{gap.lowestKnown.toFixed(2)}</b>; every stranger with a visible face scored at most <b>{gap.highestStranger.toFixed(2)}</b>. The line sits in that gap, so the face separates them.</>
                : <>Known people (lowest <b>{gap.lowestKnown.toFixed(2)}</b>) and strangers (highest <b>{gap.highestStranger.toFixed(2)}</b>) overlap on these photos, so no single line separates them perfectly.</>
              : "Photos without a usable face have no face score and are not drawn."}
          </p>
        </div>
        <div className="space-y-2">
          <ScoreStrip
            title="Clothing and build similarity"
            explain="Same scale, but measuring clothes and build instead of the face. A clothes-only matcher accepts everything to the right of the dashed line."
            rows={bodyRows} threshold={rules.body_threshold} thresholdLabel="Clothes line"
          />
          <p className="text-xs text-ink-2">
            {known && same
              ? same.min > known.max
                ? <>Strangers in the same clothes scored <b>{same.min.toFixed(2)}–{same.max.toFixed(2)}</b>, <i>higher</i> than the known people in new clothes (<b>{known.min.toFixed(2)}–{known.max.toFixed(2)}</b>). Clothing points at the wrong people, so no clothing line can separate them.</>
                : <>Strangers in the same clothes scored {same.min.toFixed(2)}–{same.max.toFixed(2)} and known people {known.min.toFixed(2)}–{known.max.toFixed(2)}: they overlap, so clothing cannot tell them apart.</>
              : "Clothing similarity is drawn for every photo the system could read."}
          </p>
        </div>
      </div>

      <div className="rounded-md border border-line bg-surface-2 p-3.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label htmlFor="face-line" className="text-sm font-semibold">Try it: move the face line</label>
          <Button size="sm" variant="ghost" icon={<RotateCcw aria-hidden className="size-3.5" />} disabled={isSystem} onClick={() => setLine(rules.face_threshold)}>
            Back to the system&apos;s {rules.face_threshold.toFixed(3)}
          </Button>
        </div>
        <input
          id="face-line" type="range" min={0.05} max={0.9} step={0.005} value={line}
          onChange={(e) => setLine(Number(e.target.value))}
          aria-valuetext={`Face line ${line.toFixed(3)}`}
          className="mt-2 w-full accent-[var(--brand)]"
        />
        <p className="mt-1 text-sm" aria-live="polite">
          With the line at <b className="font-mono">{line.toFixed(3)}</b>: known people recognised <b>{what.knownAccepted} of {what.knownTotal}</b> · strangers wrongly accepted{" "}
          <b className={strangersLetIn ? "text-bad" : "text-ok"}>{what.strangerAccepted} of {what.strangerTotal}</b>.
        </p>
        <p className="mt-1 text-xs text-ink-3">
          {strangersLetIn
            ? "Too low: strangers start getting in. Lowering the line buys recognition at the price of false accepts."
            : knownMissed
              ? "Too high: known people start being missed. Raising the line buys safety at the price of missed people."
              : "Anywhere in this gap works on these photos. The system's own line also keeps an “ask a person” band just below it."}
          {" "}Counts only photos with a usable face; the system&apos;s real rule adds that band and the clothes-based checks.
        </p>
      </div>
    </div>
  );
}
