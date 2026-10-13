/**
 * The essentials: the three things this project does, one card each, at the top of the home page.
 *
 * In plain words: 1) enroll people (tell the system who is known), 2) match photos (ask who is in a picture), 3) the open-set
 * analysis (prove it refuses strangers, even ones dressed like someone it knows). Each card shows a live status, ticks itself
 * from real data, and has one button. A viewer who only has a minute sees the whole point from here.
 */
import { CheckCircle2, Circle, FlaskConical, Play, ScanSearch, UserPlus } from "lucide-react";
import { Link } from "react-router-dom";
import { OutcomeBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EXAMPLE_ID, type OpenSetExampleState } from "@/features/demo/useOpenSetExample";
import { count } from "@/lib/format";
import { can } from "@/lib/present";
import type { Overview, Role } from "@/types/api";

/** Bring the example's card into view (gently, unless the person asked their system for less motion). */
export function showExample() {
  const target = document.getElementById(EXAMPLE_ID);
  const reduced = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  target?.scrollIntoView?.({ behavior: reduced ? "auto" : "smooth", block: "start" });
}

export function Essentials({ o, role, example }: { o: Overview; role: Role | undefined; example: OpenSetExampleState }) {
  const { identities, images } = o.gallery;
  const { run, start, busy } = example.runner;
  const info = example.query.data;
  const exampleReady = !!info?.available;
  const ran = run.phase === "done";
  const operator = can(role, "operator");

  const steps = [
    {
      done: identities > 0, icon: <UserPlus aria-hidden className="size-5" />, title: "Enroll people",
      what: "Tell the system who is known: add one to five photos of a person who agreed to it.",
      status: identities > 0 ? `${count(identities)} ${identities === 1 ? "person" : "people"} enrolled · ${count(images)} photos` : "No one is enrolled yet",
      action: <Link to="/gallery"><Button icon={<UserPlus aria-hidden className="size-4" />} disabled={!operator} title={operator ? undefined : "Requires the operator role"}>Enroll a person</Button></Link>,
    },
    {
      done: o.inference.requests > 0, icon: <ScanSearch aria-hidden className="size-5" />, title: "Match photos",
      what: "Upload any photo. The answer is one of three, with the scores and the reason behind it.",
      status: o.inference.requests > 0 ? `${count(o.inference.requests)} ${o.inference.requests === 1 ? "photo" : "photos"} checked so far` : identities === 0 ? "Enroll someone first: with nobody enrolled, every answer is UNKNOWN" : "No photo has been checked yet",
      action: <Link to="/match"><Button variant="primary" icon={<ScanSearch aria-hidden className="size-4" />}>Match a photo</Button></Link>,
    },
    {
      done: ran, icon: <FlaskConical aria-hidden className="size-5" />, title: "See the open-set analysis",
      what: "Run the built-in example: known people, strangers, and strangers dressed like someone enrolled. No setup needed.",
      status: ran ? "Example run: the results are below" : !example.query.isLoading && !exampleReady ? "Not available on this server" : "Not run yet",
      action: (
        <Button
          variant="primary" icon={<Play aria-hidden className="size-4" />} loading={busy} disabled={!exampleReady}
          title={exampleReady ? undefined : (info?.reason ?? "The example is not available")}
          onClick={() => { if (!ran) void start(); showExample(); }}
        >
          {ran ? "Show the results" : "Run the example"}
        </Button>
      ),
    },
  ];

  return (
    <Card aria-labelledby="start-title" className="mb-4">
      <CardHeader id="start-title" title="The essentials in three steps" description="Ticks appear by themselves when the real data shows a step is done." />
      <CardBody className="space-y-4">
        <ol className="grid gap-3 md:grid-cols-3">
          {steps.map((step, i) => (
            <li key={step.title} className="flex flex-col gap-2 rounded-md border border-line p-3.5">
              <div className="flex items-center gap-2.5">
                <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-tint text-brand-ink">{step.icon}</span>
                <p className="text-[15px] font-semibold"><span className="sr-only">{step.done ? "Done: " : "To do: "}</span>{i + 1}. {step.title}</p>
                {step.done ? <CheckCircle2 aria-hidden className="ml-auto size-5 shrink-0 text-ok" /> : <Circle aria-hidden className="ml-auto size-5 shrink-0 text-ink-3" />}
              </div>
              <p className="text-sm text-ink-2">{step.what}</p>
              <p className="text-xs text-ink-3">{step.status}</p>
              <div className="mt-auto pt-1">{step.action}</div>
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-md bg-surface-2 px-3.5 py-2.5 text-xs text-ink-2">
          <span className="font-medium">Every photo gets one of three answers:</span>
          <span className="inline-flex items-center gap-1.5"><OutcomeBadge outcome="accepted" short /> a person it knows</span>
          <span className="inline-flex items-center gap-1.5"><OutcomeBadge outcome="unknown" short /> no supported match (a stranger)</span>
          <span className="inline-flex items-center gap-1.5"><OutcomeBadge outcome="review_required" short /> not sure: a person should look</span>
        </div>
      </CardBody>
    </Card>
  );
}
