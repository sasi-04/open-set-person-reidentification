/**
 * VideoUpload: choose a prerecorded clip, say how often to sample it, and start the analysis.
 *
 * In plain words: the browser checks the file before anything is sent (type, size, and - by playing the
 * file's own header locally - how long it is), and tells you roughly how many frames will be analysed. The
 * server checks again from the real file contents; these early checks are a convenience, not the protection.
 * If the server cannot analyse video right now (no person detector) the form says so instead of failing later.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Film, Play, UploadCloud, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Feedback";
import { Field, Select, TextInput } from "@/components/ui/Form";
import { useToast } from "@/components/ui/Toast";
import { fileSize } from "@/lib/format";
import { api, keys } from "@/services/api";
import { describeError } from "@/services/http";
import type { RunDetail, VideoLimits } from "@/types/api";

/** A human-readable problem with a chosen file, or null if it looks acceptable. */
export function videoFileProblem(file: File, limits: VideoLimits): string | null {
  const dot = file.name.lastIndexOf(".");
  const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!limits.extensions.includes(extension)) return `"${file.name}" is not a supported video type. Use ${limits.extensions.join(", ")}.`;
  if (file.size === 0) return `"${file.name}" is empty.`;
  if (file.size > limits.max_megabytes * 1024 * 1024) return `"${file.name}" is ${fileSize(file.size)}; the limit is ${limits.max_megabytes} MB.`;
  return null;
}

const INTERVALS = ["0.5", "1", "2", "5", "10"];

export function VideoUpload({ limits, canRun, busy, onStarted }: { limits: VideoLimits; canRun: boolean; busy: boolean; onStarted: (run: RunDetail) => void }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const helpId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [every, setEvery] = useState("1");
  const [maxFrames, setMaxFrames] = useState("30");

  useEffect(() => {
    if (!file) return setPreviewUrl(null);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function choose(list: FileList | File[] | null) {
    const picked = list?.[0];
    if (!picked) return;
    const issue = videoFileProblem(picked, limits);
    setProblem(issue);
    setDuration(null);
    setFile(issue ? null : picked);
  }
  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (canRun && !busy) choose(event.dataTransfer.files);
  }

  const everyN = Number(every);
  const framesN = Number(maxFrames);
  const everyError = !Number.isFinite(everyN) || everyN < 0.1 || everyN > 60 ? "Between 0.1 and 60 seconds." : null;
  const framesError = !Number.isInteger(framesN) || framesN < 1 || framesN > limits.max_frames ? `A whole number between 1 and ${limits.max_frames}.` : null;
  const tooLong = duration !== null && duration > limits.max_seconds;
  const estimate = duration !== null && !everyError && !framesError ? Math.min(framesN, Math.floor(duration / everyN) + 1) : null;

  const start = useMutation({
    mutationFn: () => api.analyzeVideo(file as File, { everySeconds: everyN, maxFrames: framesN }),
    onSuccess: (run) => {
      toast.success("Video accepted. Progress appears on the right.");
      void queryClient.invalidateQueries({ queryKey: keys.videoJobs });
      void queryClient.invalidateQueries({ queryKey: keys.runs });
      onStarted(run);
      setFile(null);
    },
    onError: (e) => toast.error(describeError(e)),
  });

  if (!limits.detector_ready || !limits.embedding_ready) {
    return (
      <Notice tone="bad" title="Not runnable: a model is not loaded">
        {!limits.embedding_ready ? "The embedding model is not loaded. " : ""}{!limits.detector_ready ? "The person detector is not loaded, and video analysis needs it to find people in each frame. " : ""}
        Open Model &amp; System to see the reason, fix it (usually <code className="font-mono text-xs">scripts\download_weights.py</code>) and restart the server.
      </Notice>
    );
  }

  const blocked = !file || !!everyError || !!framesError || tooLong || !canRun || busy;
  return (
    <form onSubmit={(e) => e.preventDefault()} className="space-y-4" aria-label="Video analysis settings" noValidate>
      <div
        onDragOver={(e) => { e.preventDefault(); if (canRun && !busy) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={clsx("flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors", dragging ? "border-brand bg-brand-tint" : "border-line-strong bg-surface-2/50")}
      >
        <div className="flex size-10 items-center justify-center rounded-full bg-surface text-ink-3 shadow-card"><UploadCloud aria-hidden className="size-5" /></div>
        <p className="text-sm font-medium">Drag a video here</p>
        <p id={helpId} className="max-w-xs text-xs text-ink-3">or browse. {limits.extensions.join(", ")} · up to {limits.max_megabytes} MB and {limits.max_seconds} s.</p>
        <Button variant="secondary" size="sm" disabled={!canRun || busy} icon={<Film aria-hidden className="size-4" />} onClick={() => inputRef.current?.click()} aria-describedby={helpId}>Browse files</Button>
        <input ref={inputRef} type="file" className="sr-only" tabIndex={-1} aria-label="Choose a video file" accept={limits.extensions.join(",")}
          onChange={(e) => { choose(e.target.files); e.target.value = ""; }} />
      </div>
      {problem && <p role="alert" className="text-xs font-medium text-bad">{problem}</p>}

      {file && previewUrl && (
        <div className="space-y-2 rounded-md border border-line p-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0"><p className="truncate text-sm font-medium">{file.name}</p><p className="text-xs text-ink-3">{fileSize(file.size)}{duration !== null && ` · ${duration.toFixed(1)} s`}</p></div>
            <Button variant="ghost" size="sm" aria-label="Remove the chosen video" icon={<X aria-hidden className="size-4" />} onClick={() => { setFile(null); setDuration(null); }} />
          </div>
          <video src={previewUrl} controls muted preload="metadata" className="max-h-52 w-full rounded bg-black" onLoadedMetadata={(e) => setDuration(Number.isFinite(e.currentTarget.duration) ? e.currentTarget.duration : null)}>
            <track kind="captions" />
          </video>
          {tooLong && <p role="alert" className="text-xs font-medium text-bad">This clip is {duration?.toFixed(0)} s long; the server accepts at most {limits.max_seconds} s. Trim it first.</p>}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Take one frame every" hint="seconds" error={everyError}>
          <div className="flex gap-2">
            <Select aria-label="Common intervals" value={INTERVALS.includes(every) ? every : ""} onChange={(e) => e.target.value && setEvery(e.target.value)}>
              {!INTERVALS.includes(every) && <option value="">custom</option>}
              {INTERVALS.map((i) => <option key={i} value={i}>{i} s</option>)}
            </Select>
            <TextInput type="number" min={0.1} max={60} step={0.1} value={every} onChange={(e) => setEvery(e.target.value)} aria-label="Seconds between frames" className="max-w-24" />
          </div>
        </Field>
        <Field label="Stop after this many frames" hint={`At most ${limits.max_frames}`} error={framesError}>
          <TextInput type="number" min={1} max={limits.max_frames} step={1} value={maxFrames} onChange={(e) => setMaxFrames(e.target.value)} />
        </Field>
      </div>
      {estimate !== null && <p className="text-xs text-ink-3" aria-live="polite">About <b>{estimate}</b> frames will be analysed (an estimate from this file's length). Detection and matching take roughly a second or two per frame on a CPU.</p>}

      {!canRun && <Notice tone="info">Analysing video needs a signed-in role that may run queries.</Notice>}
      {busy && <Notice tone="info">Another job is already running. Wait for it to finish or cancel it.</Notice>}
      <Button variant="primary" disabled={blocked} loading={start.isPending} icon={<Play aria-hidden className="size-4" />} onClick={() => start.mutate()}>
        {start.isPending ? "Uploading…" : "Analyse video"}
      </Button>
      <p className="text-xs text-ink-3">The original video is deleted from the server as soon as it has been processed. Frame previews are kept for {limits.frame_previews_kept_hours} hours so you can look at them, then removed.</p>
    </form>
  );
}
