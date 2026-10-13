/**
 * Screen-level tests: the real application, with a pretend server.
 * They check behaviour a person would notice - what is shown, what is disabled, what is sent.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { accessKey } from "@/services/http";
import { config, finishedRun, galleryPage, identity, overview, policy, predictResponse } from "@/test/fixtures";
import { apiError, imageFile, mockApi, renderApp } from "@/test/utils";

// Screens are loaded lazily. Compiling them (especially the chart library behind the Evaluation Lab) takes
// several seconds the first time on a small CPU. Do that ONCE here so it never counts against the 8 s wait of
// an individual interaction and makes a test flaky.
beforeAll(async () => {
  await Promise.all([
    import("@/pages/CommandCenterPage"), import("@/pages/MatchStudioPage"), import("@/pages/GalleryPage"), import("@/pages/EvaluationPage"),
    import("@/pages/VideoPage"), import("@/pages/LookalikePage"), import("@/pages/HistoryPage"), import("@/pages/SettingsPage"), import("@/pages/NotFoundPage"),
  ]);
}, 120_000);

describe("access and navigation", () => {
  it("opens straight into the app when the server has access keys switched off (the default)", async () => {
    const api = mockApi({}, "admin", { authRequired: false });
    renderApp("/", { signedIn: false });
    expect(await screen.findByRole("heading", { name: "Command Center" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /connect to the backend/i })).not.toBeInTheDocument();
    expect(screen.queryByTitle("Your access role")).not.toBeInTheDocument();
    const sentAKey = api.fetchMock.mock.calls.some(([, init]) => new Headers(init?.headers).has("X-API-Key"));
    expect(sentAKey).toBe(false); // nothing was typed, so nothing is sent
    expect(accessKey.get()).toBeNull();
  });

  it("says plainly that keys are off in Settings, and offers no sign-out", async () => {
    mockApi({}, "admin", { authRequired: false });
    renderApp("/settings?tab=preferences", { signedIn: false });
    expect(await screen.findByText(/access keys are switched off/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sign out/i })).not.toBeInTheDocument();
    // every admin action is available without a key
    expect(await screen.findByRole("button", { name: /run cleanup now/i })).toBeEnabled();
  });

  it("says so, with a retry, when the backend cannot be reached - it does not ask for a key", async () => {
    mockApi({ "GET /api/auth/me": () => { throw new TypeError("Failed to fetch"); } });
    renderApp("/", { signedIn: false });
    expect(await screen.findByRole("heading", { name: /cannot reach the backend/i })).toBeInTheDocument();
    expect(screen.queryByLabelText("Access key")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("asks for an access key first when the server requires one, and only enters the app after the backend accepts it", async () => {
    mockApi();
    renderApp("/", { signedIn: false });
    expect(await screen.findByRole("heading", { name: /connect to the backend/i })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Access key"), "good-key");
    await userEvent.click(screen.getByRole("button", { name: /^connect$/i }));
    expect(await screen.findByRole("heading", { name: "Command Center" })).toBeInTheDocument();
    expect(accessKey.get()).toBe("good-key");
  });

  it("rejects a wrong key with the server's message and does not keep it", async () => {
    mockApi({ "GET /api/auth/me": () => apiError(401, "unauthorized", "The access key was not recognised.") });
    renderApp("/", { signedIn: false });
    await userEvent.type(await screen.findByLabelText("Access key"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /^connect$/i }));
    expect(await screen.findByText(/access key was not recognised/i)).toBeInTheDocument();
    expect(accessKey.get()).toBeNull();
  });

  it("opens each of the seven screens from the navigation", async () => {
    mockApi({ "GET /api/model/status": () => ({ embedding: { ready: true }, detector: { ready: true }, device: {}, gallery_index: { version: 1, identities: 0, images: 0 } }), "GET /api/config/history": () => [policy()], "GET /api/reid/history": () => ({ items: [], total: 0, limit: 15, offset: 0 }), "GET /api/audit": () => [] });
    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    const expected: [string, RegExp][] = [
      ["Identity Gallery", /^identity gallery$/i], ["Match Studio", /^match studio$/i], ["Video Explorer", /^video explorer$/i],
      ["Lookalike Failure Lab", /^lookalike failure lab$/i], ["Evaluation Lab", /^evaluation lab$/i],
      ["Model & System", /^model & system settings$/i], ["Command Center", /^command center$/i],
    ];
    for (const [label, heading] of expected) {
      await userEvent.click(within(nav).getAllByRole("link", { name: label })[0]);
      expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    }
  });

  it("shows an honest message for unknown addresses", async () => {
    mockApi();
    renderApp("/nowhere");
    expect(await screen.findByText(/this page does not exist/i)).toBeInTheDocument();
  });
});

describe("Command Center", () => {
  it("shows 'Not evaluated' and empty states - not invented numbers - when nothing has happened", async () => {
    mockApi();
    renderApp("/");
    expect(await screen.findAllByText("Not evaluated")).toHaveLength(2); // FAR and recall tiles
    expect(screen.getAllByText("No requests yet").length).toBeGreaterThan(0);
    expect(screen.getByText("No experiment has been run")).toBeInTheDocument();
    expect(screen.getByText("No dataset installed")).toBeInTheDocument();
    expect(screen.getByText(/has not been calibrated/i)).toBeInTheDocument();
  });

  it("shows the real values the backend reports", async () => {
    mockApi({ "GET /api/overview": () => overview({
      gallery: { identities: 12, images: 40 },
      inference: { requests: 7, people_processed: 9, outcomes: { accepted: 3, unknown: 5, review_required: 1 }, unknown_or_rejected: 5, acceptance_rate: 0.3333, acceptance_rate_definition: "accepted / decided", average_latency_ms: 1234, latency_window: "last 200 requests" },
      latest_evaluation: { benchmark_available: true, far: 0.0125, recall: 0.874, run_id: "r", dataset: "market1501", note: null, definition: "" },
    }) });
    renderApp("/");
    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getByText(/33\.3% of decided people/)).toBeInTheDocument();
    expect(screen.getByText("1.25%")).toBeInTheDocument();
    expect(screen.getByText("87.4%")).toBeInTheDocument();
    expect(screen.getByText("1.23 s")).toBeInTheDocument();
  });

  it("reports a failed load with a retry button instead of a blank page", async () => {
    mockApi({ "GET /api/overview": () => apiError(500, "internal_error", "Something went wrong on the server.") });
    renderApp("/");
    expect(await screen.findByRole("alert")).toHaveTextContent(/something went wrong/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

describe("Match Studio", () => {
  it("keeps the action buttons disabled until an image is chosen", async () => {
    mockApi();
    renderApp("/match");
    const run = await screen.findByRole("button", { name: /run re-identification/i });
    expect(run).toBeDisabled();
    expect(screen.getByRole("button", { name: /detect people/i })).toBeDisabled();
  });

  it("refuses an unsupported file before uploading anything", async () => {
    const api = mockApi();
    renderApp("/match");
    const input = (await screen.findByLabelText("Choose an image file")) as HTMLInputElement;
    await userEvent.upload(input, new File(["%PDF"], "doc.pdf", { type: "application/pdf" }), { applyAccept: false });
    expect(await screen.findByRole("alert")).toHaveTextContent(/not a supported image type/i);
    expect(api.called("POST", "/api/reid/predict")).toHaveLength(0);
  });

  it("uploads, calls the backend and shows the real decision and candidates", async () => {
    const api = mockApi({ "POST /api/reid/predict": () => predictResponse("accepted") });
    renderApp("/match");
    await userEvent.upload(await screen.findByLabelText("Choose an image file"), imageFile("query.png"));
    await userEvent.click(screen.getByRole("checkbox", { name: /already a person crop/i }));
    await userEvent.click(screen.getByRole("button", { name: /run re-identification/i }));
    expect((await screen.findAllByText("Match")).length).toBeGreaterThan(0); // the decision badge, the candidate and the comparison
    expect(screen.getByRole("list", { name: "Ranked candidates" })).toBeInTheDocument();
    const [call] = api.called("POST", "/api/reid/predict");
    expect(call.body).toBeInstanceOf(FormData);
    expect((call.body as FormData).get("mode")).toBe("crop");
  });

  it("shows an unknown outcome as unknown", async () => {
    mockApi({ "POST /api/reid/predict": () => predictResponse("unknown") });
    renderApp("/match");
    await userEvent.upload(await screen.findByLabelText("Choose an image file"), imageFile());
    await userEvent.click(screen.getByRole("button", { name: /run re-identification/i }));
    expect((await screen.findAllByText("Unknown")).length).toBeGreaterThan(0);
    expect(screen.queryAllByText("Match")).toHaveLength(0); // an unknown outcome is never dressed up as a match
  });

  it("shows a Processing error panel when the backend refuses the input", async () => {
    mockApi({ "POST /api/reid/predict": () => apiError(422, "no_person_detected", "No person was detected in this image.") });
    renderApp("/match");
    await userEvent.upload(await screen.findByLabelText("Choose an image file"), imageFile());
    await userEvent.click(screen.getByRole("button", { name: /run re-identification/i }));
    expect(await screen.findByText("Processing error")).toBeInTheDocument();
    expect(screen.getByText(/No person was detected/)).toBeInTheDocument();
  });

  it("draws one selectable box per detected person and matches only the selected one", async () => {
    const detections = [
      { index: 0, box: [10, 10, 60, 150], detector_score: 0.97, quality: { usable: true, flags: [], blocking_reason: null, metrics: {} } },
      { index: 1, box: [80, 20, 140, 170], detector_score: 0.88, quality: { usable: true, flags: [], blocking_reason: null, metrics: {} } },
    ];
    const api = mockApi({
      "POST /api/reid/detect": () => ({ request_id: "d1", image: { width: 200, height: 200 }, detector: "fake", detections, timings_ms: {} }),
      "POST /api/reid/predict": () => predictResponse("unknown"),
    });
    renderApp("/match");
    await userEvent.upload(await screen.findByLabelText("Choose an image file"), imageFile());
    await userEvent.click(screen.getByRole("button", { name: /detect people/i }));
    const second = await screen.findByRole("button", { name: /person 2, detector confidence 0.88/i });
    await userEvent.click(second);
    expect(second).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: /run re-identification/i }));
    await screen.findAllByText("Unknown");
    const body = api.called("POST", "/api/reid/predict")[0].body as FormData;
    expect(body.get("mode")).toBe("box");
    expect(body.get("box")).toBe("80,20,140,170");
  });

  it("tells the person when no one was found", async () => {
    mockApi({ "POST /api/reid/detect": () => ({ request_id: "d1", image: { width: 100, height: 100 }, detector: "fake", detections: [], timings_ms: {} }) });
    renderApp("/match");
    await userEvent.upload(await screen.findByLabelText("Choose an image file"), imageFile());
    await userEvent.click(screen.getByRole("button", { name: /detect people/i }));
    expect(await screen.findByText(/no person was detected/i)).toBeInTheDocument();
  });
});

describe("Identity gallery", () => {
  it("shows a helpful empty state and offers to enroll", async () => {
    mockApi();
    renderApp("/gallery");
    expect(await screen.findByText("The gallery is empty")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /enroll the first identity/i })).toBeEnabled();
  });

  it("lists identities and sends the search text to the backend", async () => {
    const api = mockApi({ "GET /api/gallery": ({ url }) => galleryPage(url.searchParams.get("search") ? [identity("alpha-1")] : [identity("alpha-1"), identity("bravo-2")]) });
    renderApp("/gallery");
    expect(await screen.findByRole("button", { name: /open bravo-2/i })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search identities"), "alpha");
    await waitFor(() => expect(screen.queryByRole("button", { name: /open bravo-2/i })).not.toBeInTheDocument());
    expect(api.called("GET", "/api/gallery").some((c) => c.search.includes("search=alpha"))).toBe(true);
  });

  it("sorts and filters through the backend, not just on screen", async () => {
    const api = mockApi({ "GET /api/gallery": () => galleryPage([identity("alpha-1")]) });
    renderApp("/gallery");
    await screen.findByRole("button", { name: /open alpha-1/i });
    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "n_images");
    await userEvent.selectOptions(screen.getByLabelText("Filter by embedding status"), "stale");
    await waitFor(() => expect(api.called("GET", "/api/gallery").some((c) => c.search.includes("sort=n_images") && c.search.includes("embedding_status=stale"))).toBe(true));
  });

  it("requires typing the reference ID before an identity can be deleted, then calls DELETE with the confirmation", async () => {
    const api = mockApi({
      "GET /api/gallery": () => galleryPage([identity("alpha-1")]),
      "GET /api/gallery/alpha-1": () => ({ ...identity("alpha-1"), consent_confirmed: true, images: [] }),
      "DELETE /api/gallery/alpha-1": () => ({ ok: true, message: "Deleted 'alpha-1' and 3 reference images.", detail: {} }),
    });
    renderApp("/gallery");
    await userEvent.click(await screen.findByRole("button", { name: /open alpha-1/i }));
    await userEvent.click(await screen.findByRole("button", { name: /delete identity/i }));
    const confirm = await screen.findByRole("dialog", { name: /delete alpha-1\?/i });
    const button = within(confirm).getByRole("button", { name: "Delete identity" });
    expect(button).toBeDisabled();
    await userEvent.type(within(confirm).getByRole("textbox"), "alpha-1");
    await userEvent.click(button);
    await waitFor(() => expect(api.called("DELETE", "/api/gallery/alpha-1")).toHaveLength(1));
    expect(api.called("DELETE", "/api/gallery/alpha-1")[0].search).toBe("?confirm=alpha-1");
    expect(await screen.findByText(/deleted 'alpha-1'/i)).toBeInTheDocument(); // toast appears only AFTER the backend answered
  });

  it("disables management actions for a viewer and says why", async () => {
    mockApi({}, "viewer");
    renderApp("/gallery");
    const enroll = await screen.findByRole("button", { name: /^enroll identity$/i });
    expect(enroll).toBeDisabled();
    expect(enroll).toHaveAttribute("title", expect.stringMatching(/operator role/i));
    expect(screen.getByRole("button", { name: /reset demo gallery/i })).toBeDisabled();
  });

  it("will not enroll without the authorisation confirmation", async () => {
    const api = mockApi({ "POST /api/gallery/enroll": () => ({}) });
    renderApp("/gallery");
    await userEvent.click(await screen.findByRole("button", { name: /^enroll identity$/i }));
    const dialog = await screen.findByRole("dialog", { name: /enroll an authorised identity/i });
    await userEvent.type(within(dialog).getByLabelText(/reference id/i), "subject-017");
    await userEvent.upload(within(dialog).getByLabelText("Choose image files"), imageFile("a.png"));
    const submit = within(dialog).getByRole("button", { name: "Enroll identity" });
    expect(submit).toBeDisabled(); // consent not ticked yet
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /i confirm this person is authorised/i }));
    expect(submit).toBeEnabled();
    expect(api.called("POST", "/api/gallery/enroll")).toHaveLength(0);
  });

  it("validates the reference ID format", async () => {
    mockApi();
    renderApp("/gallery");
    await userEvent.click(await screen.findByRole("button", { name: /^enroll identity$/i }));
    const dialog = await screen.findByRole("dialog");
    const id = within(dialog).getByLabelText(/reference id/i);
    await userEvent.type(id, "../etc/passwd");
    await userEvent.tab();
    expect(await within(dialog).findByText(/use 2–64 letters, digits/i)).toBeInTheDocument();
  });
});

describe("Model & thresholds", () => {
  const status = { embedding: { ready: true, architecture: "OSNet-AIN x1.0", embedding_dim: 512, weights: "official", device: "cpu", fingerprint: "osnet-abc-flip0" }, detector: { ready: true }, device: {}, gallery_index: { version: 1, identities: 0, images: 0 } };

  it("labels the policy honestly and shows the model facts", async () => {
    mockApi({ "GET /api/model/status": () => status, "GET /api/config/history": () => [policy()] });
    renderApp("/settings");
    expect(await screen.findByText("Unvalidated starting value")).toBeInTheDocument();
    expect(screen.getByText("OSNet-AIN x1.0")).toBeInTheDocument();
    expect(screen.getByText("512")).toBeInTheDocument();
  });

  it("rejects out-of-range thresholds with a message and keeps Save disabled", async () => {
    mockApi({ "GET /api/model/status": () => status, "GET /api/config/history": () => [policy()] });
    renderApp("/settings");
    const field = await screen.findByLabelText("Acceptance threshold");
    await userEvent.clear(field);
    await userEvent.type(field, "1.7");
    expect(await screen.findByText(/between 0 and 1/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save settings/i })).toBeDisabled();
  });

  it("asks for confirmation, then sends the change to the backend as a new experimental version", async () => {
    const api = mockApi({
      "GET /api/model/status": () => status, "GET /api/config/history": () => [policy()],
      "POST /api/config/thresholds": () => policy({ version: 2, accept_threshold: 0.82, status: "experimental" }),
    });
    renderApp("/settings");
    const field = await screen.findByLabelText("Acceptance threshold");
    await userEvent.clear(field);
    await userEvent.type(field, "0.82");
    await userEvent.click(screen.getByRole("button", { name: /save settings/i }));
    const dialog = await screen.findByRole("dialog", { name: /apply these decision rules/i });
    expect(within(dialog).getByText(/immediately/i)).toBeInTheDocument();
    expect(api.called("POST", "/api/config/thresholds")).toHaveLength(0); // nothing sent before confirming
    await userEvent.click(within(dialog).getByRole("button", { name: /apply to live decisions/i }));
    await waitFor(() => expect(api.called("POST", "/api/config/thresholds")).toHaveLength(1));
    expect(api.called("POST", "/api/config/thresholds")[0].body).toMatchObject({ accept_threshold: 0.82, confirm: true });
  });

  it("is read-only for non-admins", async () => {
    mockApi({ "GET /api/model/status": () => status, "GET /api/config/history": () => [policy()] }, "operator");
    renderApp("/settings");
    expect(await screen.findByLabelText("Acceptance threshold")).toBeDisabled();
    expect(screen.getByText(/needs the admin role/i)).toBeInTheDocument();
  });
});

describe("Evaluation lab", () => {
  it("explains how to install a dataset instead of showing fake results", async () => {
    mockApi();
    renderApp("/evaluation");
    expect(await screen.findByText("No dataset is installed")).toBeInTheDocument();
    expect(screen.getByText(/Market-1501/)).toBeInTheDocument();
    expect(screen.getByText("No results yet")).toBeInTheDocument();
  });

  it("starts a calibration through the backend and tells the person only after it is accepted", async () => {
    const api = mockApi({
      "GET /api/evaluation/datasets": () => [{ name: "market1501", layout: "market1501", kind: "benchmark", description: "", license_note: "", identities: 1501, images: 32000, cameras: 6, available: true, problems: [] }],
      "POST /api/evaluation/calibrate": () => finishedRun({ kind: "calibration", status: "queued", result: null, progress: 0 }),
    });
    renderApp("/evaluation");
    await userEvent.click(await screen.findByRole("button", { name: /calibrate threshold/i }));
    await waitFor(() => expect(api.called("POST", "/api/evaluation/calibrate")).toHaveLength(1));
    expect(api.called("POST", "/api/evaluation/calibrate")[0].body).toMatchObject({ dataset: "market1501", target: { mode: "fixed_recall", target_recall: 0.9 } });
    expect(await screen.findByText(/calibration started/i)).toBeInTheDocument();
  });

  const market = { name: "market1501", layout: "market1501", kind: "benchmark", description: "", license_note: "", identities: 1501, images: 32000, cameras: 6, available: true, problems: [] };

  it("lets you pick a fine-tuned checkpoint, pins the seed it was trained for, and sends its name (never a path)", async () => {
    const api = mockApi({
      "GET /api/evaluation/datasets": () => [market],
      "GET /api/evaluation/checkpoints": () => [{ name: "market_seed2.pt", dataset: "market1501", seed: 2, trained_people: 600, training_images: 9000, validated: false, size_mb: 8.5, modified: "2026-10-12T10:00:00Z" }],
      "POST /api/evaluation/run": () => finishedRun({ status: "queued", result: null, progress: 0 }),
    });
    renderApp("/evaluation");
    await screen.findByRole("option", { name: /market_seed2\.pt/ }); // the list loads asynchronously
    await userEvent.selectOptions(screen.getByLabelText(/fine-tuned backbone/i), "market_seed2.pt");
    expect(screen.getByText("Not yet validated")).toBeInTheDocument(); // a checkpoint is never presented as proven
    expect(screen.getByRole("checkbox", { name: "Seed 2" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Seed 0" })).not.toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: /run evaluation/i }));
    await waitFor(() => expect(api.called("POST", "/api/evaluation/run")).toHaveLength(1));
    expect(api.called("POST", "/api/evaluation/run")[0].body).toMatchObject({ finetuned_checkpoint: "market_seed2.pt", seeds: [2] });
  });

  it("explains that no fine-tuned checkpoint exists instead of offering a fake one", async () => {
    mockApi({ "GET /api/evaluation/datasets": () => [market] });
    renderApp("/evaluation");
    expect(await screen.findByText("None trained")).toBeInTheDocument();
  });

  it("rejects development + calibration fractions that leave no test split", async () => {
    mockApi({ "GET /api/evaluation/datasets": () => [market] });
    renderApp("/evaluation");
    await userEvent.click(await screen.findByText("Protocol and variants"));
    const dev = screen.getByLabelText(/development people/i);
    await userEvent.clear(dev);
    await userEvent.type(dev, "80");
    const cal = screen.getByLabelText(/calibration people/i);
    await userEvent.clear(cal);
    await userEvent.type(cal, "40");
    expect(await screen.findByText(/leave at least 10% for the test split/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run evaluation/i })).toBeDisabled();
  });

  it("disables running experiments for non-admins", async () => {
    mockApi({ "GET /api/evaluation/datasets": () => [{ name: "m", layout: "folder", kind: "benchmark", description: "", license_note: "", identities: 50, images: 500, cameras: 2, available: true, problems: [] }] }, "operator");
    renderApp("/evaluation");
    expect(await screen.findByRole("button", { name: /run evaluation/i })).toBeDisabled();
    expect(screen.getByText(/needs the admin role/i)).toBeInTheDocument();
  });

  it("shows the measured results: ablation table, selected configuration and honest labels", async () => {
    const run = finishedRun();
    mockApi({
      "GET /api/evaluation/runs": () => ({ items: [{ ...run, result: undefined, config: undefined }], total: 1 }),
      [`GET /api/evaluation/runs/${run.run_id}`]: () => run,
    });
    renderApp("/evaluation");
    expect(await screen.findByText("Selected configuration")).toBeInTheDocument();
    expect(screen.getByText(/selected on the/i)).toHaveTextContent(/calibration split/i);
    const table = await screen.findByRole("table", { name: /ablation comparison/i });
    expect(within(table).getByText("Nearest neighbour (no rejection)")).toBeInTheDocument();
    expect(within(table).getAllByText("+ Calibrated threshold").length).toBeGreaterThan(0);
    expect(within(table).getByText("Selected")).toBeInTheDocument();
    expect(within(table).getAllByText(/95% CI/).length).toBeGreaterThan(0);
    expect(screen.getByRole("tab", { name: /roc/i })).toBeInTheDocument();
  });

  it("labels smoke-test runs so they cannot be mistaken for a benchmark", async () => {
    const run = finishedRun({ dataset: "smoke_synthetic", dataset_kind: "smoke_test" });
    (run.result as { warnings: string[]; metadata: { is_benchmark: boolean } }).warnings = ["'smoke_synthetic' is a smoke test dataset. These numbers only verify that the pipeline runs end to end; they are NOT benchmark results."];
    mockApi({ "GET /api/evaluation/runs": () => ({ items: [{ ...run, result: undefined }], total: 1 }), [`GET /api/evaluation/runs/${run.run_id}`]: () => run });
    renderApp("/evaluation");
    expect(await screen.findByText("Not a benchmark result")).toBeInTheDocument();
  });

  it("reports a failed job with its reason", async () => {
    const run = finishedRun({ status: "failed", result: null, error: "Embedding model unavailable." });
    mockApi({ "GET /api/evaluation/runs": () => ({ items: [{ ...run, result: undefined }], total: 1 }), [`GET /api/evaluation/runs/${run.run_id}`]: () => run });
    renderApp("/evaluation");
    expect(await screen.findByText("This run failed")).toBeInTheDocument();
    expect(screen.getAllByText(/Embedding model unavailable/).length).toBeGreaterThan(0);
  });
});

describe("History and settings", () => {
  it("shows an empty history state, then filtered results", async () => {
    mockApi({ "GET /api/reid/history": () => ({ items: [], total: 0, limit: 15, offset: 0 }) });
    renderApp("/history");
    expect(await screen.findByText("No requests yet")).toBeInTheDocument();
  });

  it("lists past requests with their outcomes", async () => {
    mockApi({ "GET /api/reid/history": () => ({ total: 1, limit: 15, offset: 0, items: [{ request_id: "r1", created_at: "2026-10-12T10:00:00Z", mode: "all", n_people: 2, outcomes: { accepted: 1, unknown: 1 }, top_outcome: "accepted", best_score: 0.91, policy_version: 2, model_name: "osnet", total_ms: 1200 }] }) });
    renderApp("/history");
    expect((await screen.findAllByText("0.910")).length).toBeGreaterThan(0); // wait for the table (the filter menu also says "Match")
    expect(screen.getAllByText("Match").length).toBeGreaterThan(1);
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
  });

  it("shows retention facts and limits, and hides the audit trail from non-admins", async () => {
    mockApi({}, "operator");
    renderApp("/settings?tab=preferences");
    expect(await screen.findByText(/Deleted after 24 h/)).toBeInTheDocument();
    expect(screen.getByText(/Never stored \(only our own re-encoded person crop\)/)).toBeInTheDocument();
    expect(screen.getAllByText(/not a production surveillance/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("Audit trail")).not.toBeInTheDocument();
  });

  it("signs out and forgets the key", async () => {
    mockApi();
    renderApp("/settings?tab=preferences");
    await userEvent.click(await screen.findByRole("button", { name: /sign out/i }));
    expect(await screen.findByRole("heading", { name: /connect to the backend/i })).toBeInTheDocument();
    expect(accessKey.get()).toBeNull();
  });
});

describe("responsive navigation", () => {
  it("offers a menu button that opens the navigation as a dialog on small screens", async () => {
    mockApi();
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: /open navigation menu/i }));
    const dialog = await screen.findByRole("dialog", { name: /navigation/i });
    await userEvent.click(within(dialog).getByRole("link", { name: "Identity Gallery" }));
    expect(await screen.findByRole("heading", { level: 1, name: /identity gallery/i })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /navigation/i })).not.toBeInTheDocument());
  });

  it("has a skip link for keyboard users and a themed toggle", async () => {
    mockApi();
    renderApp("/");
    expect(await screen.findByRole("link", { name: /skip to main content/i })).toHaveAttribute("href", "#main");
    const toggle = screen.getByRole("button", { name: /switch to dark theme/i });
    await userEvent.click(toggle);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: /switch to light theme/i })).toBeInTheDocument();
  });
});

// Keep the config fixture referenced (it also documents the shape of /api/config for readers).
void config;
