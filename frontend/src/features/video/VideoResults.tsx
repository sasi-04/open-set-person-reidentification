/**
 * VideoResults: what the matcher decided in every sampled frame of one video.
 *
 * In plain words: a timeline of the sampled frames (each marked M = match, U = unknown, R = review, - = nobody
 * found), a viewer that draws the detected people on the selected frame with their decisions, and the exact
 * numbers per person. Frames are judged independently - the page says so at the top and never connects one
 * frame's person to another's, because no tracking is done.
 */
import { Download, Trash2 } from "lucide-react";
import clsx from "clsx";
import { useState } from "react";
import { AuthImage } from "@/components/ui/AuthImage";
import { Badge, OutcomeBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, DefinitionList, Stat } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { Notice } from "@/components/ui/Feedback";
import { useToast } from "@/components/ui/Toast";
import { DetectionPreview, type BoxOverlay } from "@/features/reid/DetectionPreview";
import { useBlobUrl } from "@/hooks/useBlobUrl";
import { count, ms, num, pct } from "@/lib/format";
import { FACE_STATUS, OUTCOME_META, QUALITY_FLAGS } from "@/lib/present";
import { api } from "@/services/api";
import { describeError, saveBlob } from "@/services/http";
import type { Outcome, RunDetail, VideoFrame, VideoResult } from "@/types/api";

type FrameKind = Outcome | "none";
const PRIORITY: Outcome[] = ["review_required", "accepted", "processing_error", "unknown"];
const SEGMENT: Record<FrameKind, { letter: string; label: string; classes: string }> = {
  accepted: { letter: "M", label: "MATCH", classes: "bg-ok-bg text-ok border-ok/40" },
  unknown: { letter: "U", label: "UNKNOWN", classes: "bg-neutral-bg text-neutral border-line-strong" },
  review_required: { letter: "R", label: "REVIEW", classes: "bg-warn-bg text-warn border-warn/40" },
  processing_error: { letter: "!", label: "ERROR", classes: "bg-bad-bg text-bad border-bad/40" },
  none: { letter: "–", label: "nobody found", classes: "bg-surface-2 text-ink-3 border-dashed border-line-strong" },
};

function frameKind(frame: VideoFrame): FrameKind {
  return PRIORITY.find((o) => frame.people.some((p) => p.outcome === o)) ?? "none";
}
const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;

function FrameStage({ jobId, frame, activePerson, onPerson }: { jobId: string; frame: VideoFrame; activePerson: number; onPerson: (i: number) => void }) {
  const { url, loading } = useBlobUrl(frame.thumbnail ? api.videoFrameUrl(jobId, frame.index) : null);
  const overlays: BoxOverlay[] = frame.people.map((p, i) => {
    const meta = OUTCOME_META[p.outcome];
    return {
      key: i, box: p.box, tone: meta.tone, selected: i === activePerson, onSelect: () => onPerson(i),
      label: `#${i + 1} ${meta.short}${p.top1_score != null ? ` ${p.top1_score.toFixed(2)}` : ""}`,
      ariaLabel: `Person ${i + 1} in this frame: ${meta.label}. Show details.`,
    };
  });
  if (!frame.thumbnail) {
    return <Notice tone="info" title="Preview not available">This frame's picture was not stored or has expired (previews are kept for a limited time). The decisions below are still recorded.</Notice>;
  }
  if (!url) return <div aria-busy={loading} aria-label="Loading the frame" className="skeleton h-64 w-full" />;
  return <DetectionPreview src={url} alt={`Sampled frame ${frame.index + 1} at ${clock(frame.time_seconds)}`} size={{ width: frame.width, height: frame.height }} overlays={overlays} />;
}

export function VideoResults({ job, result, onDeleted }: { job: RunDetail; result: VideoResult; onDeleted: () => void }) {
  const toast = useToast();
  const [selected, setSelected] = useState(0);
  const [activePerson, setActivePerson] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);

  const frame = result.frames[Math.min(selected, result.frames.length - 1)];
  const person = frame.people[Math.min(activePerson, Math.max(frame.people.length - 1, 0))];
  const o = result.summary.outcomes;
  const v = result.metadata.video;

  async function download(format: "json" | "frames_csv") {
    setBusy(format);
    try {
      saveBlob(await api.videoExport(job.run_id, format), `video-${job.run_id.slice(0, 8)}.${format === "json" ? "json" : "frames.csv"}`);
      toast.success("Export downloaded.");
    } catch (failure) {
      toast.error(describeError(failure));
    } finally {
      setBusy(null);
    }
  }
  async function remove() {
    setBusy("delete");
    try {
      await api.deleteVideo(job.run_id);
      toast.success("The job and its frame previews were deleted.");
      setConfirm(false);
      onDeleted();
    } catch (failure) {
      toast.error(describeError(failure));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <Notice tone="info" title="Frame-by-frame re-identification, not tracking">{result.notes[0]}</Notice>
      {result.notes.slice(1).map((n, i) => <Notice key={n} tone={i === 0 ? "info" : "warn"}>{n}</Notice>)}

      <Card aria-labelledby="video-summary-title">
        <CardHeader
          id="video-summary-title" title={result.metadata.original_name}
          description={`${v.width}×${v.height} · ${v.fps ? `${v.fps} fps` : "frame rate unknown"} · ${v.duration_seconds !== null ? `${v.duration_seconds.toFixed(1)} s` : "length unknown"} · every ${result.metadata.sampling.every_seconds} s`}
          action={
            <div className="flex flex-wrap gap-2" role="group" aria-label="Export or delete this analysis">
              <Button size="sm" loading={busy === "json"} icon={<Download aria-hidden className="size-3.5" />} onClick={() => void download("json")}>JSON</Button>
              <Button size="sm" loading={busy === "frames_csv"} icon={<Download aria-hidden className="size-3.5" />} onClick={() => void download("frames_csv")}>CSV per person</Button>
              <Button size="sm" variant="danger" icon={<Trash2 aria-hidden className="size-3.5" />} onClick={() => setConfirm(true)}>Delete</Button>
            </div>
          }
        />
        <CardBody className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat label="Frames analysed" value={count(result.summary.frames_processed)} hint={`of up to ${result.metadata.sampling.max_frames}`} />
            <Stat label="People detected" value={count(result.summary.people_detected)} hint="across all frames" />
            <Stat label="MATCH" value={count(o.accepted ?? 0)} hint="decisions" />
            <Stat label="UNKNOWN" value={count(o.unknown ?? 0)} hint={`${count(o.review_required ?? 0)} REVIEW`} />
            <Stat label="Per frame, median" value={ms(result.summary.latency_ms.processing_per_frame.p50)} hint={`p95 ${ms(result.summary.latency_ms.processing_per_frame.p95)}`} definition={result.summary.latency_ms.note} />
          </div>
          <p className="text-xs text-ink-3">Policy v{result.metadata.policy.version} ({result.metadata.policy.status}) · threshold {num(result.metadata.policy.accept_threshold)} · {result.metadata.model.name} on {result.metadata.model.device} · analysed in {result.summary.wall_seconds} s{result.summary.frames_per_second_processed ? ` (${result.summary.frames_per_second_processed} frames/s processed - not real time)` : ""}.</p>
        </CardBody>
      </Card>

      <Card aria-labelledby="timeline-title">
        <CardHeader id="timeline-title" title="Timeline of sampled frames" description="Select a frame. M = match, U = unknown, R = review, – = nobody found. A frame shows its most significant decision." />
        <CardBody className="space-y-3">
          <ol className="flex flex-wrap gap-1.5" aria-label="Sampled frames">
            {result.frames.map((f, i) => {
              const k = frameKind(f);
              return (
                <li key={f.index}>
                  <button type="button" aria-pressed={i === selected} title={`${clock(f.time_seconds)} - ${SEGMENT[k].label}`} aria-label={`Frame ${i + 1} at ${clock(f.time_seconds)}: ${SEGMENT[k].label}`}
                    onClick={() => { setSelected(i); setActivePerson(0); }}
                    className={clsx("flex h-11 min-w-11 flex-col items-center justify-center rounded-md border px-1 text-[10px] leading-tight", SEGMENT[k].classes, i === selected && "ring-2 ring-ink ring-offset-1 ring-offset-surface")}>
                    <span className="text-sm font-bold">{SEGMENT[k].letter}</span>
                    <span className="tabular">{f.time_seconds.toFixed(f.time_seconds % 1 ? 1 : 0)}s</span>
                  </button>
                </li>
              );
            })}
          </ol>
          <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Frame previews">
            {result.frames.map((f, i) => f.thumbnail && (
              <button key={f.index} type="button" onClick={() => { setSelected(i); setActivePerson(0); }} aria-label={`Show frame ${i + 1}`} tabIndex={-1}
                className={clsx("shrink-0 overflow-hidden rounded border-2", i === selected ? "border-brand" : "border-transparent opacity-80 hover:opacity-100")}>
                <AuthImage src={api.videoFrameUrl(job.run_id, f.index)} alt="" className="h-16 w-24" />
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
        <Card aria-labelledby="frame-title" className="min-w-0">
          <CardHeader id="frame-title" title={`Frame ${frame.index + 1} · ${clock(frame.time_seconds)}`}
            description={`video frame #${frame.frame_number} · decode ${ms(frame.timings_ms.decode_ms)} · detect ${ms(frame.timings_ms.detect_ms)} · embed ${ms(frame.timings_ms.embed_ms)} · match ${ms(frame.timings_ms.match_ms)}`} />
          <CardBody className="space-y-3">
            <FrameStage jobId={job.run_id} frame={frame} activePerson={activePerson} onPerson={setActivePerson} />
            {frame.people.length === 0 && <p className="text-sm text-ink-3">The person detector found nobody in this frame, so there was nothing to match.</p>}
          </CardBody>
        </Card>

        <Card aria-labelledby="people-title" className="min-w-0">
          <CardHeader id="people-title" title="Decisions in this frame" description="Select a box or a row to see why." />
          <CardBody className="space-y-3">
            {frame.people.length === 0 ? <p className="text-sm text-ink-3">No people.</p> : (
              <ul className="space-y-2">
                {frame.people.map((p, i) => (
                  <li key={p.index}>
                    <button type="button" onClick={() => setActivePerson(i)} aria-pressed={i === activePerson}
                      className={clsx("flex w-full flex-wrap items-center justify-between gap-2 rounded-md border p-2.5 text-left text-sm", i === activePerson ? "border-ink bg-surface-2" : "border-line hover:bg-surface-2")}>
                      <span className="flex items-center gap-2"><span className="text-xs font-semibold text-ink-3">#{i + 1}</span><OutcomeBadge outcome={p.outcome} short /></span>
                      <span className="text-xs tabular">{p.accepted_reference_id ?? p.top1_reference_id ?? "—"}{p.top1_score != null && ` · ${p.top1_score.toFixed(3)}`}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {person && (
              <div className="space-y-2 rounded-md border border-line p-3 text-sm">
                <p>{person.reason}</p>
                <DefinitionList items={[
                  { term: "Closest enrolled", value: person.top1_reference_id ?? "—" },
                  { term: person.basis === "face" ? "Face similarity" : "Similarity", value: person.top1_score != null ? <span className="tabular">{num(person.top1_score)}</span> : "—" },
                  ...(person.face_status ? [
                    { term: "Face", value: FACE_STATUS[person.face_status]?.label ?? person.face_status },
                    ...(person.top1_body_score != null ? [{ term: "Body similarity", value: <span className="tabular">{num(person.top1_body_score)}</span> }] : []),
                  ] : []),
                  { term: "Margin to runner-up", value: person.margin != null ? <span className="tabular">{num(person.margin)}</span> : "—" },
                  { term: "Detector confidence", value: <span className="tabular">{num(person.detector_score, 2)}</span> },
                ]} />
                {(person.quality_flags.length > 0 || person.blocking_reason) && (
                  <div className="flex flex-wrap gap-1.5">
                    {person.blocking_reason && <Badge tone="bad">{person.blocking_reason}</Badge>}
                    {person.quality_flags.map((f) => <Badge key={f} tone="warn">{QUALITY_FLAGS[f] ?? f}</Badge>)}
                  </div>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      <Card aria-labelledby="seen-title">
        <CardHeader id="seen-title" title="Enrolled identities with a MATCH decision" description="Decisions grouped by name after the fact. A gap between frames says nothing about where the person was." />
        <CardBody>
          {result.summary.identities_seen.length === 0 ? <p className="text-sm text-ink-3">No frame produced a MATCH decision.</p> : (
            <div className="overflow-x-auto rounded-md border border-line">
              <table className="w-full min-w-[30rem] text-left text-sm">
                <caption className="sr-only">Identities with at least one MATCH decision</caption>
                <thead className="bg-surface-2 text-xs text-ink-3"><tr>{["Reference ID", "Label", "Frames", "First", "Last", "Best similarity"].map((h) => <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
                <tbody className="divide-y divide-line tabular">
                  {result.summary.identities_seen.map((s) => (
                    <tr key={s.reference_id}><td className="px-3 py-2 font-mono font-semibold">{s.reference_id}</td><td className="px-3 py-2">{s.label ?? "—"}</td><td className="px-3 py-2">{s.frames}</td><td className="px-3 py-2">{clock(s.first_seen_seconds)}</td><td className="px-3 py-2">{clock(s.last_seen_seconds)}</td><td className="px-3 py-2">{pct(s.best_score, 1)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Delete this video analysis?" confirmLabel="Delete analysis" loading={busy === "delete"} onConfirm={() => void remove()}
        consequences="The recorded decisions and the stored frame previews are removed. The original video was already deleted after processing." />
    </div>
  );
}
