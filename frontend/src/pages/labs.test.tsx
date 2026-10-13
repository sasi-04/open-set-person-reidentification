/**
 * Tests for the screens added for the PS-1 brief: Video Explorer, the Lookalike Failure Lab, the threshold
 * sandbox, the system-health tab, the command center and the Match Studio comparison/export.
 * As elsewhere: the real application, a pretend server, and assertions about what a person would see.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { evaluationResult, finishedRun, labRun, overview, predictResponse, readiness, sandboxInfo, sandboxResult, videoJob, videoLimits } from "@/test/fixtures";
import { imageFile, mockApi, renderApp } from "@/test/utils";
import type { RunDetail } from "@/types/api";

beforeAll(async () => {
  await Promise.all([
    import("@/pages/CommandCenterPage"), import("@/pages/MatchStudioPage"), import("@/pages/VideoPage"), import("@/pages/LookalikePage"),
    import("@/pages/EvaluationPage"), import("@/pages/SettingsPage"),
  ]);
}, 120_000);

beforeEach(() => {
  HTMLAnchorElement.prototype.click = vi.fn(); // downloads are triggered through a link click; jsdom cannot navigate
});

const market = { name: "market1501", layout: "market1501", kind: "benchmark", description: "", license_note: "", identities: 1501, images: 32000, cameras: 6, available: true, problems: [] };
/** The list endpoints return runs WITHOUT their (large) result; this mirrors that. */
const summary = (run: RunDetail) => {
  const { result, config, ...rest } = run;
  void result, config;
  return rest;
};
// a string body: the newer Node/undici cannot read jsdom's own Blob type, but it reads text fine and hands back a real Blob
const jpeg = () => new Response("jpeg", { headers: { "Content-Type": "image/jpeg" } });
const video = (name = "lobby.mp4", size = 4096) => {
  const file = new File([new Uint8Array(8)], name, { type: "video/mp4" });
  Object.defineProperty(file, "size", { value: size });
  return file;
};

// ======================================================================================= branding
describe("OpenID Vision identity", () => {
  it("names the product, carries the tagline and says it is not an official Zed Digital product", async () => {
    mockApi();
    renderApp("/");
    expect((await screen.findAllByText(/Identity verification lab/i)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Know when to match\. Know when to reject\./).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/not an official Zed Digital product/i).length).toBeGreaterThan(0);
  });

  it("offers the seven screens in order, and no dead links", async () => {
    mockApi();
    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("aria-label"))).toEqual(["Command Center", "Identity Gallery", "Match Studio", "Video Explorer", "Lookalike Failure Lab", "Evaluation Lab", "Model & System"]);
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/", "/gallery", "/match", "/video", "/lookalike", "/evaluation", "/settings"]);
  });

  it("forwards the old addresses to their new home", async () => {
    mockApi();
    renderApp("/reidentify");
    expect(await screen.findByRole("heading", { level: 1, name: "Match Studio" })).toBeInTheDocument();
  });
});

// ================================================================================ Command Center
describe("Command Center", () => {
  it("guides a first run with steps that tick themselves from real data", async () => {
    mockApi();
    renderApp("/");
    expect(await screen.findByText("The essentials in three steps")).toBeInTheDocument();
    expect(screen.getAllByText(/To do:/).length).toBe(5); // three essentials + two "going deeper" steps
    expect(screen.getByText("MATCH")).toBeInTheDocument();
    expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
    expect(screen.getByText("REVIEW")).toBeInTheDocument();
  });

  it("ticks completed steps and links each experiment to the screen that can open it", async () => {
    const lab = summary(labRun());
    const evaluation = summary(finishedRun());
    mockApi({ "GET /api/overview": () => overview({
      gallery: { identities: 2, images: 6 },
      inference: { requests: 3, people_processed: 3, outcomes: { accepted: 1, unknown: 1, review_required: 1 }, unknown_or_rejected: 1, acceptance_rate: 0.3333, acceptance_rate_definition: "x", average_latency_ms: 900, latency_window: "w" },
      recent_runs: [lab, evaluation] as never,
    }) });
    renderApp("/");
    expect((await screen.findAllByText(/Done:/)).length).toBe(3); // enrolled, matched, an experiment has run (the example has not)
    expect(screen.getByRole("link", { name: /Look-alike experiment · market1501/ })).toHaveAttribute("href", `/lookalike?run=${lab.run_id}`);
    expect(screen.getByRole("link", { name: /Evaluation · market1501/ })).toHaveAttribute("href", `/evaluation?run=${evaluation.run_id}`);
  });
});

// =================================================================================== Match Studio
describe("Match Studio extras", () => {
  it("shows the query next to its closest reference and offers the backend's decision record", async () => {
    const api = mockApi({
      "POST /api/reid/predict": () => predictResponse("accepted"),
      "GET /api/reid/history/req123/export": () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
    });
    renderApp("/match");
    await userEvent.upload(await screen.findByLabelText("Choose an image file"), imageFile("query.png"));
    await userEvent.click(screen.getByRole("checkbox", { name: /already a person crop/i }));
    await userEvent.click(screen.getByRole("button", { name: /run re-identification/i }));
    expect(await screen.findByText("Query versus closest reference")).toBeInTheDocument();
    expect(screen.getByText(/Similarity is a retrieval score, not a probability/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /decision record \(json\)/i }));
    await waitFor(() => expect(api.called("GET", "/api/reid/history/req123/export")).toHaveLength(1));
    expect(api.called("GET", "/api/reid/history/req123/export")[0].search).toContain("format=json");
    await userEvent.click(screen.getByRole("button", { name: /decision record \(csv\)/i }));
    await waitFor(() => expect(api.called("GET", "/api/reid/history/req123/export")).toHaveLength(2));
    expect(screen.getByRole("link", { name: /decision history/i })).toHaveAttribute("href", "/history");
  });
});

// ================================================================================ Video Explorer
describe("Video Explorer", () => {
  it("states its scope: frame-by-frame, not tracking", async () => {
    mockApi();
    renderApp("/video");
    expect(await screen.findByText("Scope")).toBeInTheDocument();
    expect(screen.getAllByText(/not a multi-object tracker/i).length).toBeGreaterThan(0);
    expect(screen.getByText("No video analysed yet")).toBeInTheDocument();
  });

  it("refuses files that are not videos, or are too large, before sending anything", async () => {
    const api = mockApi();
    renderApp("/video");
    const input = (await screen.findByLabelText("Choose a video file")) as HTMLInputElement;
    await userEvent.upload(input, new File(["hello"], "notes.txt", { type: "text/plain" }), { applyAccept: false });
    expect(await screen.findByRole("alert")).toHaveTextContent(/not a supported video type/i);
    await userEvent.upload(input, video("huge.mp4", 500 * 1024 * 1024), { applyAccept: false });
    expect(await screen.findByRole("alert")).toHaveTextContent(/limit is 100 MB/i);
    expect(screen.getByRole("button", { name: /analyse video/i })).toBeDisabled();
    expect(api.called("POST", "/api/video/analyze")).toHaveLength(0);
  });

  it("sends the chosen file and sampling to the backend and shows the job's real progress", async () => {
    const queued = videoJob({ status: "running", progress: 0.4, stage: "Frame 2 of about 5", result: null });
    let accepted = false; // the job exists on the server only after the upload was accepted
    const api = mockApi({
      "POST /api/video/analyze": () => { accepted = true; return queued; },
      [`GET /api/video/jobs/${queued.run_id}`]: () => queued,
      "GET /api/video/jobs": () => ({ items: accepted ? [summary(queued)] : [], total: accepted ? 1 : 0 }),
    });
    renderApp("/video");
    await userEvent.upload(await screen.findByLabelText("Choose a video file"), video("lobby.mp4"));
    const seconds = screen.getByLabelText("Seconds between frames");
    await userEvent.clear(seconds);
    await userEvent.type(seconds, "2");
    const frames = screen.getByLabelText(/stop after this many frames/i);
    await userEvent.clear(frames);
    await userEvent.type(frames, "5");
    await userEvent.click(screen.getByRole("button", { name: /analyse video/i }));

    await waitFor(() => expect(api.called("POST", "/api/video/analyze")).toHaveLength(1));
    const form = api.called("POST", "/api/video/analyze")[0].body as FormData;
    expect(form.get("every_seconds")).toBe("2");
    expect(form.get("max_frames")).toBe("5");
    expect((form.get("video") as File).name).toBe("lobby.mp4");
    expect(await screen.findByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
    expect(screen.getAllByText(/Frame 2 of about 5/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /^cancel$/i })).toBeEnabled();
  });

  it("cancels a running job through the backend", async () => {
    const running = videoJob({ status: "running", progress: 0.2, stage: "Frame 1 of about 5", result: null });
    const api = mockApi({
      [`GET /api/video/jobs/${running.run_id}`]: () => running,
      "GET /api/video/jobs": () => ({ items: [summary(running)], total: 1 }),
      [`POST /api/video/jobs/${running.run_id}/cancel`]: () => ({ ...running, cancel_requested: true }),
    });
    renderApp("/video");
    await userEvent.click(await screen.findByRole("button", { name: /^cancel$/i }));
    await waitFor(() => expect(api.called("POST", `/api/video/jobs/${running.run_id}/cancel`)).toHaveLength(1));
  });

  it("shows every frame's decision on a timeline, and the details of the frame you pick", async () => {
    const job = videoJob();
    mockApi({
      [`GET /api/video/jobs/${job.run_id}`]: () => job,
      "GET /api/video/jobs": () => ({ items: [summary(job)], total: 1 }),
      [`GET /api/video/jobs/${job.run_id}/frames/0`]: jpeg,
    });
    renderApp("/video");
    expect(await screen.findByText(/Frame-by-frame re-identification, not tracking/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Frame 1 at 0:00.0: MATCH" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Frame 2 at 0:01.0: UNKNOWN" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Frame 3 at 0:02.0: nobody found" })).toBeInTheDocument();

    // frame 1: the real reason and numbers, and an overlay on the real frame picture
    expect(await screen.findByText(/Accepted: 'p-red' scored 0.91/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Person 1 in this frame: Match/i })).toBeInTheDocument();
    // frame 3: nobody was found - the screen says so instead of inventing a decision
    await userEvent.click(screen.getByRole("button", { name: /Frame 3 at/ }));
    expect(await screen.findByText(/detector found nobody in this frame/i)).toBeInTheDocument();
    // the grouped summary is explicitly not tracking
    const seen = screen.getByRole("table", { name: /identities with at least one match decision/i });
    expect(within(seen).getByText("p-red")).toBeInTheDocument();
    expect(screen.getByText(/A gap between frames says nothing about where the person was/)).toBeInTheDocument();
  });

  it("says plainly when a frame preview has expired but keeps the recorded decisions", async () => {
    const job = videoJob();
    (job.result as { frames: { thumbnail: string | null }[] }).frames[0].thumbnail = null;
    mockApi({ [`GET /api/video/jobs/${job.run_id}`]: () => job, "GET /api/video/jobs": () => ({ items: [summary(job)], total: 1 }) });
    renderApp("/video");
    expect(await screen.findByText("Preview not available")).toBeInTheDocument();
    expect(screen.getByText(/Accepted: 'p-red'/)).toBeInTheDocument();
  });

  it("asks for confirmation before deleting an analysis", async () => {
    const job = videoJob();
    const api = mockApi({
      [`GET /api/video/jobs/${job.run_id}`]: () => job, "GET /api/video/jobs": () => ({ items: [summary(job)], total: 1 }),
      [`GET /api/video/jobs/${job.run_id}/frames/0`]: jpeg,
      [`DELETE /api/video/jobs/${job.run_id}`]: () => new Response(null, { status: 204 }),
    });
    renderApp("/video");
    await userEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog", { name: /delete this video analysis/i });
    expect(api.called("DELETE", `/api/video/jobs/${job.run_id}`)).toHaveLength(0); // nothing is sent before confirming
    await userEvent.click(within(dialog).getByRole("button", { name: /delete analysis/i }));
    await waitFor(() => expect(api.called("DELETE", `/api/video/jobs/${job.run_id}`)).toHaveLength(1));
  });

  it("exports the decisions as JSON and CSV", async () => {
    const job = videoJob();
    const api = mockApi({
      [`GET /api/video/jobs/${job.run_id}`]: () => job, "GET /api/video/jobs": () => ({ items: [summary(job)], total: 1 }),
      [`GET /api/video/jobs/${job.run_id}/frames/0`]: jpeg, [`GET /api/video/jobs/${job.run_id}/export`]: () => new Response("a,b", { status: 200 }),
    });
    renderApp("/video");
    await userEvent.click(await screen.findByRole("button", { name: /csv per person/i }));
    await waitFor(() => expect(api.called("GET", `/api/video/jobs/${job.run_id}/export`)).toHaveLength(1));
    expect(api.called("GET", `/api/video/jobs/${job.run_id}/export`)[0].search).toContain("format=frames_csv");
  });

  it("reports a failed job with the backend's reason", async () => {
    const failed = videoJob({ status: "failed", result: null, error: "The video could not be opened for processing." });
    mockApi({ [`GET /api/video/jobs/${failed.run_id}`]: () => failed, "GET /api/video/jobs": () => ({ items: [summary(failed)], total: 1 }) });
    renderApp("/video");
    expect(await screen.findByText("The video job failed")).toBeInTheDocument();
    expect(screen.getAllByText(/could not be opened for processing/).length).toBeGreaterThan(0);
  });

  it("says it cannot run - and why - when the person detector is not loaded", async () => {
    mockApi({ "GET /api/video/limits": () => videoLimits({ detector_ready: false }) });
    renderApp("/video");
    expect(await screen.findByText("Not runnable: a model is not loaded")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /analyse video/i })).not.toBeInTheDocument();
  });
});

// ============================================================================ Lookalike Failure Lab
describe("Lookalike Failure Lab", () => {
  it("explains how the lab works", async () => {
    mockApi();
    renderApp("/lookalike");
    const steps = await screen.findByRole("list", { name: /how the lab works/i });
    expect(within(steps).getAllByRole("listitem")).toHaveLength(4);
    expect(screen.getByText("No experiment yet")).toBeInTheDocument();
  });

  it("is honestly 'not runnable' - and says what to install - when there is no dataset", async () => {
    mockApi();
    renderApp("/lookalike");
    expect(await screen.findByText("Not runnable yet: no labelled dataset is installed")).toBeInTheDocument();
    expect(screen.getByText(/Market-1501/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run look-alike experiment/i })).not.toBeInTheDocument();
  });

  it("is 'not runnable' when the embedding model is not loaded", async () => {
    mockApi({
      "GET /api/evaluation/datasets": () => [market],
      "GET /api/readiness": () => ({ ...readiness, status: "not_ready", components: { ...readiness.components, embedding_model: { ok: false, error: "Weights file is missing." } } }),
    });
    renderApp("/lookalike");
    expect(await screen.findByText("Not runnable: the embedding model is not loaded")).toBeInTheDocument();
    expect(screen.getAllByText(/Weights file is missing/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /run look-alike experiment/i })).toBeDisabled();
  });

  it("starts an experiment with the chosen settings and sends the checkpoint's name, never a path", async () => {
    const api = mockApi({
      "GET /api/evaluation/datasets": () => [market],
      "GET /api/evaluation/checkpoints": () => [{ name: "market_seed1.pt", dataset: "market1501", seed: 1, trained_people: 600, training_images: 9000, validated: false, size_mb: 8, modified: "2026-10-12T10:00:00Z" }],
      "POST /api/lookalike/run": () => labRun({ status: "queued", result: null, progress: 0 }),
    });
    renderApp("/lookalike");
    await screen.findByRole("option", { name: /market_seed1\.pt/ });
    await userEvent.selectOptions(screen.getByLabelText("Improved model (optional)"), "market_seed1.pt");
    expect(screen.getByText("Not yet validated")).toBeInTheDocument(); // a checkpoint is never presented as proven
    await userEvent.click(screen.getByRole("button", { name: /run look-alike experiment/i }));
    await waitFor(() => expect(api.called("POST", "/api/lookalike/run")).toHaveLength(1));
    expect(api.called("POST", "/api/lookalike/run")[0].body).toMatchObject({
      dataset: "market1501", mining_split: "test", seed: 1, finetuned_checkpoint: "market_seed1.pt", target: { mode: "fixed_recall", target_recall: 0.9 },
    });
    expect(await screen.findByText(/experiment started/i)).toBeInTheDocument();
  });

  it("explains that no checkpoint exists instead of offering a fake one", async () => {
    mockApi({ "GET /api/evaluation/datasets": () => [market] });
    renderApp("/lookalike");
    expect(await screen.findByText("None trained")).toBeInTheDocument();
  });

  function withResult(run = labRun()) {
    return mockApi({
      "GET /api/evaluation/datasets": () => [market],
      "GET /api/lookalike/runs": () => ({ items: [summary(run)], total: 1 }),
      [`GET /api/lookalike/runs/${run.run_id}`]: () => run,
      [`GET /api/evaluation/runs/${run.run_id}/sandbox`]: () => sandboxInfo(),
      [`POST /api/evaluation/runs/${run.run_id}/sandbox`]: ({ body }) => sandboxResult((body as { threshold: number }).threshold, (body as { split: "calibration" | "test" }).split),
      [`GET /api/lookalike/runs/${run.run_id}/export`]: () => new Response("x", { status: 200 }),
    });
  }

  it("shows the headline with both stranger rates and what kind of dataset it was", async () => {
    withResult();
    renderApp("/lookalike");
    expect(await screen.findByText("What this experiment found")).toBeInTheDocument();
    expect(screen.getByText("Hard strangers accepted")).toBeInTheDocument();
    expect(screen.getByText("Strangers accepted, all pairs")).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument(); // the hard-pair rate
    expect(screen.getByText("0.040%")).toBeInTheDocument(); // the realistic all-pairs rate
    expect(screen.getByText("Calibration target reached")).toBeInTheDocument();
    expect(screen.getByText("Baseline only")).toBeInTheDocument();
  });

  it("lists look-alike pairs with their decision, and filters them", async () => {
    withResult();
    renderApp("/lookalike");
    const first = await screen.findByRole("article", { name: /Look-alike pair 1: person 0042 and person 0101/ });
    expect(within(first).getByText("Would be ACCEPTED (false accept)")).toBeInTheDocument();
    expect(within(first).getByText("Similar clothing colours")).toBeInTheDocument();
    expect(within(first).getByText(/look-alike embeddings do not prove identical clothing/i)).toBeInTheDocument();
    const second = screen.getByRole("article", { name: /Look-alike pair 2/ });
    expect(within(second).getByText("Correctly rejected")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText(/^show$/i), "accepted");
    expect(screen.queryByRole("article", { name: /Look-alike pair 2/ })).not.toBeInTheDocument();
    expect(screen.getByRole("article", { name: /Look-alike pair 1/ })).toBeInTheDocument();
  });

  it("keeps measured facts apart from unproven hypotheses in every mistake", async () => {
    withResult();
    renderApp("/lookalike");
    await userEvent.click(await screen.findByRole("tab", { name: "Mistakes" }));
    const card = await screen.findByRole("article", { name: /Stranger accepted as an enrolled person IN-001/ });
    expect(within(card).getByRole("region", { name: /observed measurements/i })).toHaveTextContent(/Similarity to the pick/);
    const causes = within(card).getByRole("region", { name: /possible causes, not proven/i });
    expect(causes).toHaveTextContent(/hypotheses, not proven/i);
    expect(causes).toHaveTextContent(/Evidence: similarity 0.820 is only 0.020 above the threshold/);

    await userEvent.selectOptions(screen.getByLabelText(/^show$/i), "genuine_rejected");
    expect(screen.queryByRole("article", { name: /IN-001/ })).not.toBeInTheDocument();
    expect(screen.getByRole("article", { name: /Enrolled person not accepted GE-001/ })).toBeInTheDocument();
  });

  it("describes the challenge set and warns not to compare its stranger rate with a target", async () => {
    withResult();
    renderApp("/lookalike");
    await userEvent.click(await screen.findByRole("tab", { name: "Challenge set" }));
    expect(await screen.findByText("Read the two stranger columns together")).toBeInTheDocument();
    expect(screen.getByText(/chosen BECAUSE they are hard/)).toBeInTheDocument();
    expect(screen.getByText("How this challenge set was built")).toBeInTheDocument();
    expect(screen.getByText(/similar EMBEDDINGS/)).toBeInTheDocument();
    expect(screen.getByRole("slider", { name: /threshold position on the curve/i })).toBeInTheDocument();
  });

  it("shows no comparison - and no invented numbers - when no improved model was evaluated", async () => {
    withResult();
    renderApp("/lookalike");
    await userEvent.click(await screen.findByRole("tab", { name: "Baseline vs improved" }));
    expect(await screen.findByText("No improved-model comparison in this experiment")).toBeInTheDocument();
    expect(screen.getByText(/No fine-tuned checkpoint was selected/)).toBeInTheDocument();
    expect(screen.getByText(/makes no claim that metric-learning fine-tuning improves results/i)).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: /baseline and improved model compared/i })).not.toBeInTheDocument();
  });

  it("compares two models on the same examples when an improved one was evaluated", async () => {
    withResult(labRun({}, true));
    renderApp("/lookalike");
    await userEvent.click(await screen.findByRole("tab", { name: "Baseline vs improved" }));
    const table = await screen.findByRole("table", { name: /baseline and improved model compared/i });
    expect(within(table).getByText("Challenge: hard strangers accepted")).toBeInTheDocument();
    expect(within(table).getByText(/12 of 24/)).toBeInTheDocument();
    expect(within(table).getByText(/5 of 24/)).toBeInTheDocument();
    expect(screen.getByText(/Same examples, each model at its own calibrated threshold/)).toBeInTheDocument();
  });

  it("exports the experiment in each format through the backend", async () => {
    const run = labRun();
    const api = withResult(run);
    renderApp("/lookalike");
    await userEvent.click(await screen.findByRole("button", { name: /pairs \(csv\)/i }));
    await userEvent.click(screen.getByRole("button", { name: /mistakes \(csv\)/i }));
    await userEvent.click(screen.getByRole("button", { name: /full record \(json\)/i }));
    await waitFor(() => expect(api.called("GET", `/api/lookalike/runs/${run.run_id}/export`)).toHaveLength(3));
    const formats = api.called("GET", `/api/lookalike/runs/${run.run_id}/export`).map((c) => new URLSearchParams(c.search).get("format"));
    expect(formats).toEqual(["pairs_csv", "failures_csv", "json"]);
  });

  it("states its limitations and how to reproduce the experiment", async () => {
    withResult();
    renderApp("/lookalike");
    await userEvent.click(await screen.findByRole("tab", { name: "Method & limits" }));
    expect(await screen.findByText("Limitations of this experiment")).toBeInTheDocument();
    expect(screen.getByText(/challenge set is selected by the baseline model/i)).toBeInTheDocument();
    expect(screen.getByText("Reproducibility")).toBeInTheDocument();
  });

  it("flags a smoke-test experiment so it cannot pass for a benchmark", async () => {
    const run = labRun({ dataset_kind: "smoke_test" });
    (run.result as { metadata: { is_benchmark: boolean }; warnings: string[] }).metadata.is_benchmark = false;
    (run.result as { warnings: string[] }).warnings = ["'smoke_synthetic' is a smoke test dataset: these results only show that the lab runs end to end. They are NOT benchmark results."];
    withResult(run);
    renderApp("/lookalike");
    expect(await screen.findByText("Read this first")).toBeInTheDocument();
    expect(screen.getByText(/NOT benchmark results/)).toBeInTheDocument();
    expect(screen.getByText("Smoke test, not a benchmark")).toBeInTheDocument();
  });

  it("reports a failed experiment with its reason", async () => {
    const run = labRun({ status: "failed", result: null, error: "The chosen split has fewer than two people." });
    mockApi({ "GET /api/lookalike/runs": () => ({ items: [summary(run)], total: 1 }), [`GET /api/lookalike/runs/${run.run_id}`]: () => run });
    renderApp("/lookalike");
    expect(await screen.findByText("This experiment failed")).toBeInTheDocument();
    expect(screen.getAllByText(/fewer than two people/).length).toBeGreaterThan(0);
  });
});

// ================================================================================ Threshold sandbox
describe("Threshold sandbox", () => {
  function openSandbox() {
    const run = labRun();
    const api = mockApi({
      "GET /api/evaluation/datasets": () => [market],
      "GET /api/lookalike/runs": () => ({ items: [summary(run)], total: 1 }),
      [`GET /api/lookalike/runs/${run.run_id}`]: () => run,
      [`GET /api/evaluation/runs/${run.run_id}/sandbox`]: () => sandboxInfo(),
      [`POST /api/evaluation/runs/${run.run_id}/sandbox`]: ({ body }) => sandboxResult((body as { threshold: number }).threshold, (body as { split: "calibration" | "test" }).split),
    });
    return { run, api };
  }

  it("starts from the calibrated rule - nothing changes - and offers no way to apply a value", async () => {
    const { run, api } = openSandbox();
    renderApp("/lookalike");
    await userEvent.click(await screen.findByRole("tab", { name: "Threshold sandbox" }));
    expect(await screen.findByText("Read-only sandbox")).toBeInTheDocument();
    expect(screen.getByText(/no decision differs from the calibrated rule/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply|save|set as/i })).not.toBeInTheDocument(); // by design
    expect(screen.getByRole("link", { name: /model & system settings/i })).toHaveAttribute("href", "/settings?tab=model");
    expect(screen.getByRole("button", { name: /back to the calibrated rule/i })).toBeDisabled();
    const [first] = api.called("POST", `/api/evaluation/runs/${run.run_id}/sandbox`);
    expect(first.body).toMatchObject({ split: "calibration", threshold: 0.8, min_margin: 0.05 });
  });

  it("recounts on the backend when the threshold moves and lists the decisions that change", async () => {
    const { run, api } = openSandbox();
    renderApp("/lookalike");
    await userEvent.click(await screen.findByRole("tab", { name: "Threshold sandbox" }));
    const exact = await screen.findByLabelText("Exact threshold");
    await userEvent.clear(exact);
    await userEvent.type(exact, "0.7");
    expect(await screen.findByText(/12 decisions differ from the calibrated rule/i)).toBeInTheDocument();
    const calls = api.called("POST", `/api/evaluation/runs/${run.run_id}/sandbox`);
    expect(calls[calls.length - 1].body).toMatchObject({ threshold: 0.7 });
    const table = screen.getByRole("table", { name: /differs from the calibrated rule/i });
    expect(within(table).getByText("0101/c2_03.jpg")).toBeInTheDocument();
    expect(within(table).getByText("stranger")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /back to the calibrated rule/i })).toBeEnabled();
  });

  it("warns that choosing a threshold by watching test results is tuning on the test set", async () => {
    openSandbox();
    renderApp("/lookalike");
    await userEvent.click(await screen.findByRole("tab", { name: "Threshold sandbox" }));
    const counted = await screen.findByRole("group", { name: "Which people to count" });
    await userEvent.click(within(counted).getByRole("radio", { name: /test people/i }));
    expect(await screen.findByText("Exploration only")).toBeInTheDocument();
    expect(screen.getByText(/tuning on the test set/i)).toBeInTheDocument();
  });

  it("is available in the Evaluation Lab for evaluation runs that kept their scores", async () => {
    const run = finishedRun();
    (run.result as { sandbox_available?: boolean }).sandbox_available = true;
    mockApi({
      "GET /api/evaluation/runs": () => ({ items: [summary(run)], total: 1 }), [`GET /api/evaluation/runs/${run.run_id}`]: () => run,
      [`GET /api/evaluation/runs/${run.run_id}/sandbox`]: () => sandboxInfo(),
    });
    renderApp("/evaluation");
    expect(await screen.findByRole("tab", { name: "Threshold sandbox" })).toBeInTheDocument();
  });

  it("is absent for runs that did not keep the per-query table", async () => {
    const run = finishedRun();
    mockApi({ "GET /api/evaluation/runs": () => ({ items: [summary(run)], total: 1 }), [`GET /api/evaluation/runs/${run.run_id}`]: () => run });
    renderApp("/evaluation");
    await screen.findByText("Selected configuration");
    expect(screen.queryByRole("tab", { name: "Threshold sandbox" })).not.toBeInTheDocument();
    void evaluationResult;
  });
});

// ============================================================================= Model & System Settings
describe("Model & System Settings", () => {
  it("separates validated from experimental settings on the model tab", async () => {
    mockApi({ "GET /api/model/status": () => ({ embedding: { ready: true, architecture: "OSNet-AIN x1.0" }, detector: { ready: true }, device: {}, gallery_index: { version: 1, identities: 0, images: 0 } }), "GET /api/config/history": () => [] });
    renderApp("/model"); // the old address forwards here
    expect(await screen.findByText("Experimental: set the rules by hand")).toBeInTheDocument();
    expect(screen.getByText("Validated: apply a calibration result")).toBeInTheDocument();
  });

  it("shows the live health of each component and the real reason when something failed to load", async () => {
    mockApi({ "GET /api/readiness": () => ({ ...readiness, status: "degraded", components: { ...readiness.components, detector: { ok: false, error: "Detector weights are missing." } } }) });
    renderApp("/settings?tab=system");
    expect(await screen.findByText("System health")).toBeInTheDocument();
    expect(screen.getByText("Database")).toBeInTheDocument();
    expect(screen.getByText("Person detector")).toBeInTheDocument();
    expect(await screen.findByText("Dependency or weight-loading problem")).toBeInTheDocument();
    expect(screen.getAllByText(/Detector weights are missing/).length).toBeGreaterThan(0);
    expect(screen.getByText("Runtime configuration")).toBeInTheDocument();
    expect(screen.getByText(/up to 100 MB · 180 s long · 120 sampled frames/)).toBeInTheDocument();
  });

  it("lists datasets relative to the project folder, never an absolute server path", async () => {
    mockApi({ "GET /api/overview": () => overview({ datasets: [{ name: "market1501", layout: "market1501", kind: "benchmark", description: "", license_note: "", identities: 1501, images: 32000, cameras: 6, available: true, problems: [] }] }) });
    renderApp("/settings?tab=system");
    expect(await screen.findByText("datasets/market1501")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/[A-Za-z]:\\|\/home\//);
  });
});

// keep a type-only import referenced
void readiness;
