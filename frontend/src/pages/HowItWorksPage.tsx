/**
 * How it works: a plain-language tour of the system, inside the application.
 *
 * In plain words: this page exists so that anyone - a juror, a manager, a colleague who never saw the code - can
 * understand what OpenID Vision does and, just as important, what it cannot do, without leaving the application. It
 * explains with words and two small illustrations. The only numbers shown are the live thresholds read from the
 * backend (so they can never disagree with the real settings); no accuracy figure is hard-coded here - those live in
 * the reports, with their sources, and are quoted in docs/JURY_GUIDE.md.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileSearch, Layers, ScanFace, ScanSearch, ShieldCheck, ThumbsUp, UserRoundSearch } from "lucide-react";
import { Link } from "react-router-dom";
import { OutcomeBadge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { num } from "@/lib/format";
import { api, keys } from "@/services/api";

/** Two people in the SAME clothes but with different faces: the reason a clothing-only matcher is not enough. Illustration only. */
function SameClothesDifferentFace() {
  const person = (x: number, face: "a" | "b") => (
    <g transform={`translate(${x} 0)`}>
      <rect x="32" y="74" width="56" height="70" rx="10" className="fill-info" opacity="0.85" />
      <rect x="38" y="144" width="18" height="52" rx="6" className="fill-ink-2" />
      <rect x="64" y="144" width="18" height="52" rx="6" className="fill-ink-2" />
      <circle cx="60" cy="48" r="26" className="fill-surface-2 stroke-ink-2" strokeWidth="2" />
      {face === "a" ? (
        <>
          <circle cx="51" cy="44" r="3" className="fill-ink" />
          <circle cx="69" cy="44" r="3" className="fill-ink" />
          <path d="M50 58 Q60 66 70 58" fill="none" className="stroke-ink" strokeWidth="2.5" strokeLinecap="round" />
          <path d="M60 46 L58 54 L62 54" fill="none" className="stroke-ink-3" strokeWidth="1.5" />
        </>
      ) : (
        <>
          <ellipse cx="48" cy="43" rx="4" ry="2.5" className="fill-ink" />
          <ellipse cx="72" cy="43" rx="4" ry="2.5" className="fill-ink" />
          <path d="M52 60 L68 60" className="stroke-ink" strokeWidth="2.5" strokeLinecap="round" />
          <path d="M60 46 L56 56 L64 56" fill="none" className="stroke-ink-3" strokeWidth="1.5" />
        </>
      )}
    </g>
  );
  return (
    <svg viewBox="0 0 330 210" role="img" aria-label="Illustration: two different people wearing the same blue jacket. The jackets look identical; the faces are different." className="mx-auto h-auto w-full max-w-sm">
      {person(10, "a")}
      {person(200, "b")}
      <path d="M118 112 H182" className="stroke-ok" strokeWidth="3" strokeDasharray="6 5" />
      <text x="150" y="104" textAnchor="middle" className="fill-ok text-[11px] font-semibold">clothes: alike</text>
      <path d="M118 48 H182" className="stroke-bad" strokeWidth="3" />
      <text x="150" y="40" textAnchor="middle" className="fill-bad text-[11px] font-semibold">faces: different</text>
    </svg>
  );
}

const STEPS = [
  { icon: <UserRoundSearch aria-hidden className="size-5" />, title: "Find the people", text: "A detector draws a box around every person in the photo." },
  { icon: <ShieldCheck aria-hidden className="size-5" />, title: "Check the picture quality", text: "Too blurry, too small or cut off by the frame? The system then refuses to pretend it is sure." },
  { icon: <ScanFace aria-hidden className="size-5" />, title: "Find and judge the face", text: "Is there a face, is it big and sharp enough, is it facing the camera? If not, it is not used - and the screen says why." },
  { icon: <Layers aria-hidden className="size-5" />, title: "Make two fingerprints", text: "The face becomes 128 numbers; the whole person (clothing, build) becomes 512 numbers. Similar pictures give similar numbers." },
  { icon: <FileSearch aria-hidden className="size-5" />, title: "Compare with everyone enrolled", text: "Each enrolled person gets a face score and a body score. Higher means more alike (from -1 to 1; not a percentage)." },
  { icon: <ThumbsUp aria-hidden className="size-5" />, title: "Decide with a written rule", text: "MATCH, UNKNOWN or REVIEW - the rule is versioned, and the reason is printed in plain words." },
  { icon: <ScanSearch aria-hidden className="size-5" />, title: "Record what happened", text: "Scores, the rule version and the reason are saved so any decision can be explained and exported later." },
];

export default function HowItWorksPage() {
  const config = useQuery({ queryKey: keys.config, queryFn: api.config });
  const policy = config.data?.policy;
  const faceOn = policy?.matching_mode === "face_body";
  const live = (value: number | null | undefined) => (value === null || value === undefined ? "—" : num(value));

  return (
    <>
      <PageHeader title="How it works" description="A plain-language tour: what the system looks at, how it decides, and what it can and cannot do. No code needed." />

      <div className="grid gap-4 xl:grid-cols-2">
        <Card aria-labelledby="idea-title" className="xl:col-span-2">
          <CardHeader id="idea-title" title="The idea in one minute" />
          <CardBody className="space-y-3 text-sm leading-6">
            <p>
              Imagine a security guard who only checks <b>uniforms</b>. Anyone in the right jacket walks in - including a stranger in a look-alike one.
              That is how many person re-identification systems fail: they compare clothing and build, so a <b>different person who dresses the same</b> is
              accepted.
            </p>
            <p>
              OpenID Vision behaves like a careful guard: it looks at the <b>face first</b> and the <b>body and clothing second</b>. It says <b>MATCH</b> only
              when the evidence is strong, <b>UNKNOWN</b> to somebody it has never seen, and <b>REVIEW</b> - "ask a human" - when it is not sure.
              That is the PS-1 problem: <em>open-set</em> identification, where the person in front of the camera may not be enrolled at all.
            </p>
          </CardBody>
        </Card>

        <Card aria-labelledby="answers-title">
          <CardHeader id="answers-title" title="The three answers" description="Every result is exactly one of these (or a processing error if the picture could not be used)." />
          <CardBody>
            <ul className="space-y-3">
              <li className="flex items-start gap-3"><OutcomeBadge outcome="accepted" /><span className="text-sm">"This is enrolled person X." The evidence passed the rule. <i>The door opens.</i></span></li>
              <li className="flex items-start gap-3"><OutcomeBadge outcome="unknown" /><span className="text-sm">"Nobody enrolled is supported by the evidence." <i>The door stays shut.</i> This is a statement about the evidence, never an accusation: unknown people are not saved, grouped or tracked.</span></li>
              <li className="flex items-start gap-3"><OutcomeBadge outcome="review_required" /><span className="text-sm">"I am not sure - a person should look." Blurry photo, face too small, a borderline score, or no face visible. <i>The guard calls a supervisor.</i></span></li>
            </ul>
          </CardBody>
        </Card>

        <Card aria-labelledby="why-title">
          <CardHeader id="why-title" title="Why clothing alone is not enough" description="Illustration only - not a measurement." action={<Link to="/" className="inline-flex items-center gap-1 text-sm font-medium underline">See it with real photos: run the example <ArrowRight aria-hidden className="size-4" /></Link>} />
          <CardBody className="space-y-3">
            <SameClothesDifferentFace />
            <p className="text-sm">
              A clothing-based model sees these two people as nearly the same. Their faces are clearly different. So the rule is: <b>when a usable face is visible, the
              face decides</b> - similar clothing can never turn a face that does not match into a MATCH.
            </p>
          </CardBody>
        </Card>

        <Card aria-labelledby="steps-title" className="xl:col-span-2">
          <CardHeader id="steps-title" title="What happens to one photo" description="You can watch these steps happen in Match Studio: the Evidence card shows steps 3 to 5." action={<Link to="/match" className="inline-flex items-center gap-1 text-sm font-medium underline">Open Match Studio <ArrowRight aria-hidden className="size-4" /></Link>} />
          <CardBody>
            <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" aria-label="Processing steps">
              {STEPS.map((step, i) => (
                <li key={step.title} className="flex gap-3 rounded-md border border-line p-3">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-tint text-brand-ink">{step.icon}</span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold"><span className="text-ink-3">{i + 1}.</span> {step.title}</p>
                    <p className="mt-0.5 text-xs text-ink-3">{step.text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </CardBody>
        </Card>

        <Card aria-labelledby="who-title">
          <CardHeader id="who-title" title="Who decides, and when" description={faceOn ? "The active policy uses face + body." : "The active policy is body-only; switch to Face + body in Model & System."} />
          <CardBody className="overflow-x-auto">
            <table className="w-full min-w-[26rem] text-left text-sm">
              <caption className="sr-only">Which evidence decides in each situation</caption>
              <thead className="text-xs text-ink-3"><tr><th scope="col" className="py-1.5 pr-3 font-medium">Situation</th><th scope="col" className="py-1.5 pr-3 font-medium">What decides</th><th scope="col" className="py-1.5 font-medium">Typical result</th></tr></thead>
              <tbody className="divide-y divide-line">
                <tr><th scope="row" className="py-2 pr-3 font-medium">Clear face, enrolled person</th><td className="py-2 pr-3">the <b>face</b></td><td className="py-2"><OutcomeBadge outcome="accepted" short /></td></tr>
                <tr><th scope="row" className="py-2 pr-3 font-medium">Clear face, stranger (even in the same clothes)</th><td className="py-2 pr-3">the <b>face</b></td><td className="py-2"><OutcomeBadge outcome="unknown" short /></td></tr>
                <tr><th scope="row" className="py-2 pr-3 font-medium">Face score borderline</th><td className="py-2 pr-3">the face, but too close to call</td><td className="py-2"><OutcomeBadge outcome="review_required" short /></td></tr>
                <tr><th scope="row" className="py-2 pr-3 font-medium">No usable face (back view, far away, blurred)</th><td className="py-2 pr-3">the <b>body</b> - weaker evidence, so a person is asked</td><td className="py-2"><OutcomeBadge outcome="review_required" short /></td></tr>
              </tbody>
            </table>
          </CardBody>
        </Card>

        <Card aria-labelledby="numbers-title">
          <CardHeader id="numbers-title" title="Reading the numbers" description="Read live from the active policy." />
          <CardBody className="space-y-3 text-sm">
            <p><b>Similarity</b> says how alike two fingerprints are, from -1 to 1. It is a <b>score, not a probability</b>: 0.9 does not mean "90 % sure".</p>
            <p><b>Threshold</b> is the score a match must reach. Higher means stricter: fewer strangers get in, but more real matches go to review.</p>
            <ul className="space-y-1.5 rounded-md bg-surface-2 p-3">
              <li>Face threshold for an automatic MATCH: <b className="tabular">{live(policy?.face_accept_threshold)}</b>{faceOn ? "" : " (not in use: body-only policy)"}</li>
              <li>Face review band just below it: <b className="tabular">{live(policy?.face_review_band)}</b></li>
              <li>Body (clothing and build) threshold: <b className="tabular">{live(policy?.accept_threshold)}</b></li>
              <li>Policy status: <b>{policy?.status ?? "—"}</b> - {policy?.status === "calibrated" ? "selected on held-out data" : "a starting value that has not been calibrated on this system's own cameras"}</li>
            </ul>
            <p className="text-xs text-ink-3">The reasons behind the default numbers, and everything that was measured, are in <code className="font-mono">docs/FACE_AND_BODY_MATCHING.md</code>.</p>
          </CardBody>
        </Card>

        <Card aria-labelledby="limits-title">
          <CardHeader id="limits-title" title="What it cannot do - said up front" />
          <CardBody>
            <ul className="list-disc space-y-1.5 pl-5 text-sm">
              <li>It is <b>not</b> a phone's Face ID: there is no depth sensor, and no check that a real person (not a photograph) is present.</li>
              <li>Twins and close look-alikes can still score high. That is what the review band and the Lookalike Failure Lab are for.</li>
              <li>Masks, sunglasses, strong angles, low light and tiny faces make faces unusable - the system says so instead of guessing.</li>
              <li>Accuracy has been measured on a standard public face test, which is easy; other cameras, lighting and groups of people have <b>not</b> been measured.</li>
              <li>It is a research prototype: no live cameras, no tracking, one local user.</li>
            </ul>
          </CardBody>
        </Card>

        <Card aria-labelledby="data-title">
          <CardHeader id="data-title" title="Your data and consent" />
          <CardBody>
            <ul className="list-disc space-y-1.5 pl-5 text-sm">
              <li>Only <b>enrolled, consenting</b> people are ever matched. Enrolment needs an explicit confirmation.</li>
              <li>A <b>face fingerprint is biometric data</b>. It is stored on this computer only, until the person is deleted.</li>
              <li>Deleting a person removes their photos, face and body fingerprints. Query photos expire after 24 hours.</li>
              <li>Nothing is sent to any outside service. There is no scraping and no camera feed.</li>
            </ul>
            <p className="mt-3 text-xs text-ink-3">Manage this in <Link to="/gallery" className="underline">Identity Gallery</Link> and <Link to="/settings" className="underline">Model &amp; System</Link>.</p>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
