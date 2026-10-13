/**
 * Match Studio (screen C): the query-to-gallery workflow.
 *
 *   left   query image + processing controls
 *   centre detection preview (boxes you can select), then the query next to its closest reference
 *   right  decision (MATCH / UNKNOWN / REVIEW), ranked candidates, exports
 *
 * On narrow screens these stack in that order. All logic lives in useReid(); this file
 * only arranges the pieces. The decision itself always comes from the backend - the page
 * never decides anything.
 */
import { AlertTriangle, ScanSearch } from "lucide-react";
import { useState } from "react";
import { OutcomeBadge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, Notice } from "@/components/ui/Feedback";
import { PageHeader } from "@/components/ui/PageHeader";
import { CandidatePanel } from "@/features/reid/CandidatePanel";
import { ComparePanel } from "@/features/reid/ComparePanel";
import { DecisionSummary } from "@/features/reid/DecisionSummary";
import { DetectionPreview, type BoxOverlay } from "@/features/reid/DetectionPreview";
import { EvidencePanel } from "@/features/reid/EvidencePanel";
import { QueryPanel } from "@/features/reid/QueryPanel";
import { ResultActions } from "@/features/reid/ResultActions";
import { ReviewDialog } from "@/features/reid/ReviewDialog";
import { useReid } from "@/features/reid/useReid";
import { useFileLimits } from "@/hooks/useLimits";
import { num } from "@/lib/format";
import { OUTCOME_META, QUALITY_FLAGS } from "@/lib/present";
import clsx from "clsx";

export default function MatchStudioPage() {
  const reid = useReid();
  const limits = useFileLimits();
  const [reviewOpen, setReviewOpen] = useState(false);
  const { result, person, detections, image } = reid;

  // One overlay per person: after a result they show the outcome, before it they let you pick who to match.
  // With face matching, the face the matcher found is drawn too (a small box; it is only a marker, not selectable).
  const faceOverlays: BoxOverlay[] = result
    ? result.people.flatMap((p, i) =>
        p.face?.box
          ? [{
              key: 1000 + i, box: p.face.box, label: p.face.status === "usable" ? "face" : "face (not usable)",
              tone: p.face.status === "usable" ? "info" as const : "warn" as const, selected: false,
              ariaLabel: `Face found for person ${i + 1}: ${p.face.status === "usable" ? "usable" : "not usable"}`,
            }]
          : [],
      )
    : [];
  const overlays: BoxOverlay[] = result
    ? [...result.people.flatMap((p, i) => {
        const box = reid.boxFor(i);
        if (!box) return [];
        const meta = OUTCOME_META[p.decision.outcome];
        return [{
          key: i, box, label: `#${i + 1} · ${meta.short}`, tone: meta.tone, selected: i === reid.activePerson,
          ariaLabel: `Person ${i + 1}: ${meta.label}. Show details.`, onSelect: () => reid.setActivePerson(i),
        }];
      }), ...faceOverlays]
    : (detections ?? []).map((d, i) => ({
        key: i, box: d.box, label: `#${i + 1} · detector ${d.detector_score.toFixed(2)}`, tone: "pending" as const, selected: reid.selected === i,
        ariaLabel: `Person ${i + 1}, detector confidence ${d.detector_score.toFixed(2)}. ${reid.selected === i ? "Selected for matching." : "Select for matching."}`,
        onSelect: () => reid.setSelected(i),
      }));

  return (
    <>
      <PageHeader
        title="Match Studio"
        description="Detect a person, compare their face and body with the enrolled gallery, and see why the system decided MATCH, UNKNOWN or REVIEW."
      />
      {/* grid-cols-[minmax(0,1fr)]: on a phone the single column must be allowed to shrink to the screen, or one wide child stretches every card. */}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[320px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)_400px]">
        <div className="space-y-4">
          <QueryPanel
            image={image} limits={limits} onChoose={reid.chooseFile} onReset={reid.reset}
            asCrop={reid.asCrop} onAsCrop={reid.setAsCrop} matchAll={reid.matchAll} onMatchAll={reid.setMatchAll}
            mode={reid.mode} detecting={reid.detecting} matching={reid.matching} onDetect={reid.detect} onRun={reid.run}
          />
        </div>

        <div className="min-w-0 space-y-4">
        <Card aria-labelledby="preview-title" className="min-w-0">
          <CardHeader id="preview-title" title="Detection preview" description="The number on a box is the detector's confidence that it is a person, not an identity score." />
          <CardBody className="space-y-3">
            {!image ? (
              <EmptyState icon={<ScanSearch aria-hidden className="size-5" />} title="No image yet">
                Upload a query image on the left. Boxes drawn here come from the real person detector.
              </EmptyState>
            ) : (
              <>
                <DetectionPreview
                  src={image.url} alt="Uploaded query" size={reid.imageSize} overlays={overlays} busy={reid.detecting || reid.matching}
                />
                {overlays.length > 1 && (
                  <p className="text-xs text-ink-3">{result ? "Select a box to see that person's decision." : "Select the person to match, or tick “Match everyone”."}</p>
                )}
                {!result && detections && detections.length > 0 && (
                  <ul className="flex flex-wrap gap-2" aria-label="People found">
                    {detections.map((d, i) => (
                      <li key={d.index}>
                        <button
                          type="button" aria-pressed={reid.selected === i} onClick={() => reid.setSelected(i)}
                          className={clsx("rounded-full border px-3 py-1 text-xs", reid.selected === i ? "border-ink bg-surface-2 font-semibold" : "border-line-strong hover:bg-surface-2")}
                        >
                          Person {i + 1} · detector {num(d.detector_score, 2)}
                          {d.quality.flags.length > 0 && <span className="text-warn"> · {d.quality.flags.map((f) => QUALITY_FLAGS[f] ?? f).join(", ")}</span>}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </CardBody>
        </Card>

        {person && result && image && !reid.error && person.candidates.length > 0 && (
          <Card aria-labelledby="compare-title">
            <CardHeader id="compare-title" title="Query versus closest reference" description="The same two pictures the similarity score was computed from." />
            <CardBody><ComparePanel person={person} imageUrl={image.url} size={reid.imageSize} /></CardBody>
          </Card>
        )}
        </div>

        <div className="space-y-4 lg:col-span-2 xl:col-span-1">
          <Card aria-labelledby="decision-title">
            <CardHeader id="decision-title" title="Decision" description="Outcome under the active decision policy." />
            <CardBody aria-live="polite">
              {reid.matching && <p role="status" className="text-sm text-ink-3">Matching…</p>}
              {!reid.matching && reid.error && (
                <div className="space-y-2">
                  <OutcomeBadge outcome="processing_error" />
                  <p className="flex gap-2 text-sm"><AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-bad" />{reid.error}</p>
                  <p className="text-xs text-ink-3">{OUTCOME_META.processing_error.blurb}</p>
                </div>
              )}
              {!reid.matching && !reid.error && person && result && <DecisionSummary person={person} response={result} total={result.people.length} />}
              {!reid.matching && !reid.error && !person && (
                <p className="text-sm text-ink-3">Run re-identification to see the outcome. A nearest neighbour is never accepted automatically: its similarity must pass the configured threshold.</p>
              )}
            </CardBody>
          </Card>

          {person && result && image && !reid.error && result.matching_mode === "face_body" && person.decision.matching_mode === "face_body" && (
            <Card aria-labelledby="evidence-title">
              <CardHeader id="evidence-title" title="Evidence" description="Face, body and colour cues, side by side. The face decides when a usable face is visible." />
              <CardBody><EvidencePanel person={person} imageUrl={image.url} /></CardBody>
            </Card>
          )}

          {person && result && !reid.error && (
            <>
              <Card aria-labelledby="candidates-title">
                <CardHeader id="candidates-title" title="Ranked candidates" description="Enrolled identities, most similar first." />
                <CardBody>
                  <CandidatePanel person={person} onReview={() => setReviewOpen(true)} />
                </CardBody>
              </Card>
              <Card aria-labelledby="actions-title">
                <CardHeader id="actions-title" title="Export and next steps" description="The decision record is generated by the backend from what it saved for this request." />
                <CardBody>
                  <ResultActions response={result} onNewQuery={reid.newQuery} onClear={reid.reset} />
                </CardBody>
              </Card>
              {image && (
                <ReviewDialog open={reviewOpen} onOpenChange={setReviewOpen} person={person} imageUrl={image.url} size={reid.imageSize} />
              )}
            </>
          )}
          {!person && !reid.error && image && !reid.matching && (
            <Notice tone="info">This is a research prototype for authorised test images. Results are for evaluation, not for enforcement decisions.</Notice>
          )}
        </div>
      </div>
    </>
  );
}
