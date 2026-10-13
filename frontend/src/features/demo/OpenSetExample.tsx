/**
 * The open-set example, on the home page.
 *
 * In plain words: this is the project's argument in one click. It enrolls three example people in a private, temporary
 * gallery, then shows the system 13 photos it has never seen - known people, strangers, and strangers dressed like an
 * enrolled person - and lays out what it decided, whether that was right, and what a clothes-only matcher would have done.
 * The photos are public-domain portraits shipped with the project. Nothing is saved and the real gallery is never touched.
 */
import { FlaskConical, Play, RotateCw } from "lucide-react";
import { Link } from "react-router-dom";
import { AuthImage } from "@/components/ui/AuthImage";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState, Notice, Skeleton } from "@/components/ui/Feedback";
import { Progress } from "@/components/ui/Progress";
import { REFERENCE_FACE_STATUS } from "@/lib/present";
import type { DemoInfo, DemoPerson } from "@/types/api";
import { Analysis } from "./Analysis";
import { CaseRow, ROW_COLUMNS, type RowState } from "./CaseRow";
import { Comparison } from "./Comparison";
import { plain } from "./summary";
import { EXAMPLE_ID, type OpenSetExampleState } from "./useOpenSetExample";

function People({ people }: { people: DemoPerson[] }) {
  return (
    <ul className="grid gap-3 md:grid-cols-3">
      {people.map((person) => (
        <li key={person.id} className="flex gap-3 rounded-md border border-line p-3">
          <div className="flex shrink-0 gap-1.5">
            {person.photos.map((photo) => (
              <div key={photo.url} className="space-y-1">
                <AuthImage src={photo.url} alt={`${person.label}, enrolled photo`} className="h-20 w-14 rounded border border-line object-top" />
                {photo.face_status && <p className="text-center text-[10px] leading-tight text-ink-3">{REFERENCE_FACE_STATUS[photo.face_status]?.label ?? photo.face_status}</p>}
              </div>
            ))}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium">{person.label}</p>
            <p className="text-xs text-ink-3">{person.note}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function RunBar({ state, info }: { state: OpenSetExampleState; info: DemoInfo }) {
  const { run, start, busy } = state.runner;
  const done = Object.keys(run.results).length;
  if (run.phase === "preparing") return <Progress value={0.02} label="Building the example gallery" />;
  if (run.phase === "running") return <Progress value={done / info.cases.length} label={`Analysing photo ${Math.min(done + 1, info.cases.length)} of ${info.cases.length}`} />;
  if (run.phase === "error") return null;
  return (
    <Button
      variant="primary" icon={run.phase === "done" ? <RotateCw aria-hidden className="size-4" /> : <Play aria-hidden className="size-4" />}
      onClick={() => void start()} disabled={busy}
    >
      {run.phase === "done" ? "Run it again" : "Run the example"}
    </Button>
  );
}

export function OpenSetExample({ state }: { state: OpenSetExampleState }) {
  const { query, runner } = state;
  const { run } = runner;
  const info = query.data;

  let body;
  if (query.isLoading) {
    body = <div aria-busy="true" aria-label="Loading the example"><Skeleton className="h-40" /></div>;
  } else if (query.isError || !info) {
    body = <ErrorState error={query.error} onRetry={() => void query.refetch()} title="The example could not be loaded" />;
  } else if (!info.available) {
    body = (
      <Notice tone="warn" title="The example is not available on this server">
        {info.reason ?? "Its photos or face models are missing."} The rest of the application works without it.
      </Notice>
    );
  } else {
    const done = Object.keys(run.results).length;
    const people = run.people ?? info.people;
    const rules = run.rules ?? info.rules;
    const stateFor = (id: string): RowState => (run.results[id] ? "done" : run.phase === "running" || run.phase === "preparing" ? "waiting" : "idle");
    body = (
      <div className="space-y-6">
        <ol className="grid gap-3 text-sm md:grid-cols-3">
          {[
            ["1", "Enroll three example people", "A private, temporary gallery. Nothing is saved; your real gallery is untouched."],
            ["2", `Show ${info.cases.length} photos it has never seen`, "People it knows, strangers, and strangers dressed exactly like an enrolled person."],
            ["3", "Compare two matchers", "This system (face + body) against one that looks only at clothes and build."],
          ].map(([n, title, text]) => (
            <li key={n} className="flex gap-3">
              <span aria-hidden className="flex size-6 shrink-0 items-center justify-center rounded-full bg-brand-tint text-xs font-semibold text-brand-ink">{n}</span>
              <div><p className="font-medium">{title}</p><p className="text-xs text-ink-3">{text}</p></div>
            </li>
          ))}
        </ol>

        <div className="flex flex-wrap items-center gap-3">
          <RunBar state={state} info={info} />
          {(run.phase === "preparing" || run.phase === "running") && (
            <p role="status" className="text-sm text-ink-2">
              {run.phase === "preparing" ? "Building the example gallery…" : `Analysing photo ${Math.min(done + 1, info.cases.length)} of ${info.cases.length}…`}
            </p>
          )}
          {run.phase === "done" && run.totalMs !== null && <p role="status" className="text-xs text-ink-3">Done: {info.cases.length} photos in {(run.totalMs / 1000).toFixed(1)} s, on this computer.</p>}
          {rules && (
            <Badge tone="neutral" className="ml-auto">
              Rules: face line {plain(rules.face_threshold)} · clothes line {plain(rules.body_threshold)} · {rules.policy_status}
            </Badge>
          )}
        </div>
        {run.phase === "error" && <ErrorState error={run.error} onRetry={() => void runner.start()} title="The example stopped" />}

        {run.phase === "done" && rules && (
          <>
            <Comparison cases={info.cases} results={run.results} />
            <Analysis cases={info.cases} results={run.results} rules={rules} />
          </>
        )}

        <section aria-labelledby="enrolled-title">
          <h3 id="enrolled-title" className="mb-2 text-sm font-semibold">Who the system knows <span className="font-normal text-ink-3">(the example gallery)</span></h3>
          <People people={people} />
        </section>

        <section aria-labelledby="photos-title">
          <h3 id="photos-title" className="text-sm font-semibold">The {info.cases.length} photos, and what each matcher decided</h3>
          <div aria-hidden className={`mt-2 hidden gap-3 border-b border-line pb-2 text-[11px] font-semibold tracking-wide text-ink-3 uppercase lg:grid ${ROW_COLUMNS}`}>
            <span>Photo and right answer</span><span>Face + body (this system)</span><span>Clothes only (weaker matcher)</span>
          </div>
          {info.groups.map((group) => {
            const items = info.cases.filter((c) => c.group === group.id);
            if (!items.length) return null;
            return (
              <div key={group.id} className="mt-3">
                <h4 className="text-[13px] font-semibold">{group.title}</h4>
                <p className="text-xs text-ink-3">{group.blurb}</p>
                <ul className="divide-y divide-line">
                  {items.map((item) => <CaseRow key={item.id} item={item} result={run.results[item.id]} state={stateFor(item.id)} />)}
                </ul>
              </div>
            );
          })}
        </section>

        <p className="text-xs text-ink-3">
          {info.disclaimer} <Link to="/how-it-works" className="font-medium underline">How the decision works</Link>
        </p>
      </div>
    );
  }

  return (
    <Card id={EXAMPLE_ID} aria-labelledby="example-title" className="scroll-mt-20">
      <CardHeader
        id="example-title"
        title={<span className="inline-flex items-center gap-2"><FlaskConical aria-hidden className="size-4 text-brand-ink" />Open-set example: does it refuse strangers?</span>}
        description="One click, public-domain photos, nothing saved. This is the analysis the project is about."
      />
      <CardBody>{body}</CardBody>
    </Card>
  );
}
