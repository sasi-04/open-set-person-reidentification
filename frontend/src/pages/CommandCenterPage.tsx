/**
 * Command Center (screen A): the home page.
 *
 * In plain words: this is what an interviewer sees first, so it leads with the three essentials - enroll people, match photos,
 * and the open-set analysis (a built-in example you can run with one click, with its results right here) - and only then the
 * live system status. Every status figure comes from the backend at the moment you open the page; a figure with nothing behind
 * it shows "Not evaluated" or an empty state - never an invented zero or a demo number. The example uses public-domain
 * photos in a private, temporary gallery and saves nothing.
 */
import { useQuery } from "@tanstack/react-query";
import {
  Activity, CheckCircle2, Circle, CircleHelp, Cpu, Database, Eye, FlaskConical, Gauge, Images, ShieldCheck, Target, Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, OutcomeBadge, PolicyBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, DefinitionList, Stat } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { PageHeader } from "@/components/ui/PageHeader";
import { OpenSetExample } from "@/features/demo/OpenSetExample";
import { useOpenSetExample } from "@/features/demo/useOpenSetExample";
import { Essentials } from "@/features/home/Essentials";
import { useSession } from "@/hooks/useSession";
import { count, dateTime, ms, pct, timeAgo } from "@/lib/format";
import { api, keys } from "@/services/api";
import type { Outcome, Overview, Readiness, RunSummary } from "@/types/api";

const RUN_TONE = { succeeded: "ok", failed: "bad", cancelled: "neutral", running: "info", queued: "info" } as const;
const KIND_LABEL = { evaluation: "Evaluation", calibration: "Calibration", lookalike: "Look-alike experiment", video: "Video" } as const;

/** Where a finished experiment can be opened. */
function runLink(run: RunSummary): string {
  return run.kind === "lookalike" ? `/lookalike?run=${run.run_id}` : `/evaluation?run=${run.run_id}`;
}

function RunRow({ run }: { run: RunSummary }) {
  return (
    <li className="flex items-center justify-between gap-3 py-2.5">
      <div className="min-w-0">
        <Link to={runLink(run)} className="block truncate text-sm font-medium text-ink hover:underline">{KIND_LABEL[run.kind]} · {run.dataset}</Link>
        <p className="text-xs text-ink-3">{timeAgo(run.created_at)}{run.dataset_kind !== "benchmark" && " · smoke test (not a benchmark)"}</p>
      </div>
      <Badge tone={RUN_TONE[run.status]}>{run.status === "running" ? `Running ${pct(run.progress, 0)}` : run.status}</Badge>
    </li>
  );
}

/** The two steps beyond the essentials, for a technical reader who wants measured numbers on a benchmark dataset. */
function GoDeeper({ o }: { o: Overview }) {
  const steps = [
    { done: o.recent_runs.length > 0, text: "Run an experiment on a labelled dataset", why: "Measure false accepts at a fixed recall, and look for look-alike failures. Needs a dataset in datasets/.", to: "/lookalike", cta: "Open the Lookalike Failure Lab" },
    { done: o.policy.status === "calibrated", text: "Calibrate the decision threshold", why: "Until a calibration is applied the threshold is an unvalidated starting value.", to: "/evaluation", cta: "Open the Evaluation Lab" },
  ];
  if (steps.every((s) => s.done)) return null;
  return (
    <Card aria-labelledby="deeper-title" className="mb-4">
      <CardHeader id="deeper-title" title="Going deeper" description="For measured numbers on a labelled benchmark dataset. These tick themselves too." />
      <CardBody>
        <ol className="grid gap-3 md:grid-cols-2">
          {steps.map((step, i) => (
            <li key={step.text} className="flex gap-3 rounded-md border border-line p-3">
              {step.done ? <CheckCircle2 aria-hidden className="mt-0.5 size-5 shrink-0 text-ok" /> : <Circle aria-hidden className="mt-0.5 size-5 shrink-0 text-ink-3" />}
              <div className="min-w-0 space-y-1">
                <p className="text-sm font-medium"><span className="sr-only">{step.done ? "Done: " : "To do: "}</span>{i + 1}. {step.text}</p>
                <p className="text-xs text-ink-3">{step.why}</p>
                {!step.done && <Link to={step.to} className="inline-block text-xs font-medium underline">{step.cta}</Link>}
              </div>
            </li>
          ))}
        </ol>
      </CardBody>
    </Card>
  );
}

/** What the system holds, how it has been used and how far its decisions can be trusted (all read from the backend). */
function LiveStatus({ o, readiness }: { o: Overview; readiness: Readiness | undefined }) {
  const latest = o.latest_evaluation;
  const outcomes = o.inference.outcomes;
  const embedding = readiness?.components.embedding_model as Record<string, unknown> | undefined;
  const device = readiness?.components.device as { type?: string; name?: string } | undefined;
  const ready = readiness?.status;

  return (
    <section aria-labelledby="status-title" className="mt-8">
      <div className="mb-3">
        <h2 id="status-title" className="text-lg leading-7 font-semibold">Live system status</h2>
        <p className="mt-0.5 max-w-3xl text-sm text-ink-3">What the system holds, how it has been used and how far its decisions can be trusted. Every figure is read from the backend; definitions are on the (i) icons.</p>
      </div>
      <GoDeeper o={o} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat icon={<ShieldCheck aria-hidden className="size-4" />} label="Models" value={ready === "ready" ? "Ready" : ready === "degraded" ? "Degraded" : ready === "not_ready" ? "Not ready" : "Checking"} tone={ready === "ready" ? "default" : "muted"}
          hint={embedding?.ok ? `${String(embedding.architecture)}${o.readiness.face_models ? " + face models" : ""}` : ready ? "See Model & System" : "Contacting the backend"} definition="Whether the body embedding model, the person detector and (when installed) the face models are loaded and answering." />
        <Stat icon={<Cpu aria-hidden className="size-4" />} label="Inference device" value={device?.type ? (device.type === "cuda" ? "GPU" : "CPU") : "—"} tone={device?.type ? "default" : "muted"} hint={device?.name && device.type === "cuda" ? device.name : "CUDA is optional"} />
        <Stat icon={<Users aria-hidden className="size-4" />} label="Enrolled identities" value={count(o.gallery.identities)} hint={`${count(o.gallery.images)} reference images`} />
        <Stat icon={<Activity aria-hidden className="size-4" />} label="Queries processed" value={count(o.inference.requests)} hint={`${count(o.inference.people_processed)} people decided, all time`} definition="Requests that completed. Failed requests (for example unreadable files) are not stored." />

        <Stat icon={<CheckCircle2 aria-hidden className="size-4" />} label="MATCH" value={count(outcomes.accepted ?? 0)} hint={o.inference.acceptance_rate === null ? "No decisions yet" : `${pct(o.inference.acceptance_rate)} of decided people`} definition={o.inference.acceptance_rate_definition} tone={o.inference.people_processed === 0 ? "muted" : "default"} />
        <Stat icon={<CircleHelp aria-hidden className="size-4" />} label="UNKNOWN" value={count(outcomes.unknown ?? 0)} hint="No supported match" definition="People whose outcome was UNKNOWN: no enrolled identity satisfied the acceptance rule. Not a finding about the person." tone={o.inference.people_processed === 0 ? "muted" : "default"} />
        <Stat icon={<Eye aria-hidden className="size-4" />} label="REVIEW" value={count(outcomes.review_required ?? 0)} hint="Ambiguous or low quality" definition="People sent to a human because the ranking was ambiguous or the image quality was inadequate." tone={o.inference.people_processed === 0 ? "muted" : "default"} />
        <Stat icon={<Gauge aria-hidden className="size-4" />} label="Average latency" value={ms(o.inference.average_latency_ms)} tone={o.inference.average_latency_ms === null ? "muted" : "default"} hint={o.inference.average_latency_ms === null ? "No requests yet" : o.inference.latency_window} definition="Mean server-side pipeline time per request (detection, embedding, retrieval, decision)." />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" aria-labelledby="runs-title">
          <CardHeader id="runs-title" title="Recent experiment activity" description="Evaluations, calibrations and look-alike experiments, newest first." action={<Link to="/evaluation" className="text-sm font-medium underline">Evaluation Lab</Link>} />
          <CardBody>
            {o.recent_runs.length === 0 ? (
              <EmptyState icon={<FlaskConical aria-hidden className="size-5" />} title="No experiment has been run" action={<Link to="/lookalike"><Button variant="primary" size="sm">Open the Lookalike Failure Lab</Button></Link>}>
                Experiments measure false accepts against recall on identity-disjoint splits. Install a dataset (see the card on the right), then start one.
              </EmptyState>
            ) : (
              <ul className="divide-y divide-line">{o.recent_runs.map((run) => <RunRow key={run.run_id} run={run} />)}</ul>
            )}
          </CardBody>
        </Card>

        <Card aria-labelledby="system-title">
          <CardHeader id="system-title" title="Threshold and policy" action={<Link to="/settings" className="text-sm font-medium underline">Details</Link>} />
          <CardBody className="space-y-3">
            <DefinitionList
              items={[
                { term: "Decision policy", value: <span className="inline-flex flex-wrap items-center gap-1.5">v{o.policy.version} <PolicyBadge status={o.policy.status} /></span> },
                { term: "Matching", value: o.policy.matching_mode === "face_body"
                    ? (o.policy.face_matching_active ? <span>Face + body (the face decides when it is visible)</span> : <span className="text-warn">Face + body requested, but the face models are not loaded: body only</span>)
                    : "Body only (clothing and build)" },
                ...(o.policy.matching_mode === "face_body" && o.policy.face_accept_threshold != null ? [{ term: "Face threshold", value: o.policy.face_accept_threshold.toFixed(3) }] : []),
                { term: o.policy.matching_mode === "face_body" ? "Body threshold" : "Threshold", value: o.policy.accept_threshold.toFixed(3) },
                { term: "Minimum margin", value: o.policy.min_margin === null ? "Not used" : o.policy.min_margin.toFixed(3) },
                { term: "Person detector", value: o.readiness.detector ? "Loaded" : <span className="text-warn">Missing (crop mode only)</span> },
              ]}
            />
            {o.policy.status !== "calibrated" ? (
              <p className="rounded-md bg-warn-bg p-2.5 text-xs text-warn">This threshold has not been calibrated on held-out data. Run a calibration in the Evaluation Lab before trusting MATCH / UNKNOWN decisions.</p>
            ) : (
              <p className="rounded-md bg-ok-bg p-2.5 text-xs text-ok">Calibrated on held-out calibration people for a stated target.</p>
            )}
          </CardBody>
        </Card>

        <Card className="xl:col-span-2" aria-labelledby="activity-title">
          <CardHeader id="activity-title" title="Recent decisions" action={<Link to="/history" className="text-sm font-medium underline">All decisions</Link>} />
          <CardBody>
            {o.recent_requests.length === 0 ? (
              <EmptyState icon={<Activity aria-hidden className="size-5" />} title="No queries yet" action={<Link to="/match"><Button variant="primary" size="sm">Run your first query</Button></Link>}>
                Match Studio requests appear here with their outcomes and timings.
              </EmptyState>
            ) : (
              <ul className="divide-y divide-line">
                {o.recent_requests.map((r) => (
                  <li key={r.request_id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                    <div>
                      <p className="text-sm font-medium">{r.n_people} {r.n_people === 1 ? "person" : "people"} · {ms(r.total_ms)}</p>
                      <p className="text-xs text-ink-3">{timeAgo(r.created_at)} · <span className="font-mono">{r.request_id}</span></p>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {([...new Set(r.outcomes)] as Outcome[]).map((out) => <OutcomeBadge key={out} outcome={out} short />)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <div className="space-y-4">
          <Card aria-labelledby="latest-title">
            <CardHeader id="latest-title" title="Latest benchmark evaluation" />
            <CardBody className="space-y-2">
              <div className="grid grid-cols-2 gap-3">
                <Stat icon={<Target aria-hidden className="size-4" />} label="False accepts" value={latest.far !== null ? pct(latest.far, 2) : "Not evaluated"} tone={latest.far === null ? "muted" : "default"} hint={latest.far !== null ? latest.dataset : undefined} definition={`False Accept Rate: strangers wrongly accepted ÷ all strangers. ${latest.definition}`} />
                <Stat icon={<Images aria-hidden className="size-4" />} label="Recall" value={latest.recall !== null ? pct(latest.recall) : "Not evaluated"} tone={latest.recall === null ? "muted" : "default"} hint={latest.recall !== null ? "DIR@1" : undefined} definition={`Enrolled people accepted AND correctly named ÷ all enrolled people. ${latest.definition}`} />
              </div>
              {latest.note && <p className="text-xs text-ink-3">{latest.note}</p>}
            </CardBody>
          </Card>

          <Card aria-labelledby="datasets-title">
            <CardHeader id="datasets-title" title="Dataset availability" />
            <CardBody>
              {o.datasets.length === 0 ? (
                <EmptyState icon={<Database aria-hidden className="size-5" />} title="No dataset installed">
                  Download Market-1501 (research use) and unpack it into <code className="font-mono text-xs">datasets/market1501</code>. See the README, “Dataset acquisition”.
                </EmptyState>
              ) : (
                <ul className="space-y-2.5">
                  {o.datasets.map((d) => (
                    <li key={d.name} className="text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-1.5">
                        <span className="font-medium">{d.name}</span>
                        {d.kind === "benchmark" ? <Badge tone="ok">Benchmark</Badge> : <Badge tone="warn">Smoke test only</Badge>}
                      </div>
                      <p className="text-xs text-ink-3">{d.available ? `${count(d.identities)} identities · ${count(d.images)} images` : d.problems.join(" ")}</p>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
      <p className="mt-4 text-xs text-ink-3">Last refreshed {dateTime(new Date().toISOString())}. Evaluation figures count only runs on datasets marked “benchmark”.</p>
    </section>
  );
}

export default function CommandCenterPage() {
  const { role } = useSession();
  const overview = useQuery({ queryKey: keys.overview, queryFn: api.overview });
  const readiness = useQuery({ queryKey: keys.readiness, queryFn: api.readiness, retry: false });
  const example = useOpenSetExample();

  let top;
  let status = null;
  if (overview.isLoading) {
    top = (
      <div className="grid gap-3 md:grid-cols-3" aria-busy="true" aria-label="Loading the command center">
        {Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-44" />)}
      </div>
    );
  } else if (overview.isError || !overview.data) {
    top = <ErrorState error={overview.error} onRetry={() => void overview.refetch()} title="The command center could not be loaded" />;
  } else {
    top = <Essentials o={overview.data} role={role} example={example} />;
    status = <LiveStatus o={overview.data} readiness={readiness.data} />;
  }

  return (
    <>
      <PageHeader
        title="Command Center"
        description="Start here. Enroll people, match photos, and watch the system refuse strangers - even strangers dressed like someone it knows."
      />
      {top}
      <OpenSetExample state={example} />
      {status}
    </>
  );
}
