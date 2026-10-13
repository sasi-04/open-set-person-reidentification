/**
 * Face + body matching in the interface.
 *
 * In plain words: these tests check that what the server says about the FACE (and the body, and the colour cues) reaches
 * the screen truthfully - which evidence decided, both scores next to their own thresholds, why a face could not be
 * used - and that the controls for switching the mode send exactly what was chosen. The server is a pretend one.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeAll, describe, expect, it } from "vitest";
import { CandidatePanel } from "@/features/reid/CandidatePanel";
import { DecisionSummary } from "@/features/reid/DecisionSummary";
import { EvidencePanel } from "@/features/reid/EvidencePanel";
import { config, faceBodyResponse, galleryPage, identity, policy, predictResponse } from "@/test/fixtures";
import { imageFile, mockApi, renderApp } from "@/test/utils";

function wrap(node: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

// Warm the lazily-loaded screens once so a slow first compile never counts against one interaction's wait.
beforeAll(async () => {
  await Promise.all([import("@/pages/MatchStudioPage"), import("@/pages/GalleryPage"), import("@/pages/SettingsPage"), import("@/pages/HowItWorksPage")]);
}, 60_000);

describe("a result decided by the face", () => {
  it("labels the score as a FACE similarity and shows the face threshold, not the body threshold", () => {
    const response = faceBodyResponse("accepted");
    wrap(<DecisionSummary person={response.people[0]} response={response} total={1} />);
    expect(screen.getByText("Face similarity")).toBeInTheDocument();
    expect(screen.getByText("0.742")).toBeInTheDocument();
    expect(screen.getByText("Face threshold")).toBeInTheDocument();
    expect(screen.getAllByText("0.363").length).toBeGreaterThan(0);
    expect(screen.getByText(/accepted by face/i)).toBeInTheDocument();
  });

  it("a stranger in the same clothes is UNKNOWN, and the screen says clothing alone was not accepted", () => {
    const response = faceBodyResponse("unknown");
    wrap(<DecisionSummary person={response.people[0]} response={response} total={1} />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.queryByText("Selected reference ID")).not.toBeInTheDocument();
    expect(screen.getByText(/NOT accepted when a face is available/)).toBeInTheDocument();
  });

  it("shows each candidate's face and body scores, each against its own threshold", () => {
    const response = faceBodyResponse("accepted");
    wrap(<CandidatePanel person={response.people[0]} onReview={() => {}} />);
    const [first, second] = within(screen.getByRole("list", { name: "Ranked candidates" })).getAllByRole("listitem");
    expect(within(first).getByText("Scored by face")).toBeInTheDocument();
    expect(first).toHaveTextContent("Face 0.742");
    expect(first).toHaveTextContent("Body 0.910");
    expect(within(first).getByText("Match")).toBeInTheDocument();
    expect(within(second).getByText("Scored by body (no face on file)")).toBeInTheDocument();
    expect(within(second).getByText("Below threshold")).toBeInTheDocument(); // 0.31 against the BODY threshold 0.70
  });
});

describe("EvidencePanel", () => {
  it("lays out face, body and colour cues, and says the cues never decide", () => {
    const response = faceBodyResponse("accepted");
    wrap(<EvidencePanel person={response.people[0]} imageUrl="blob:query" />);
    expect(screen.getByText("Decided by the face")).toBeInTheDocument();
    expect(screen.getByText("Face found and usable")).toBeInTheDocument();
    expect(screen.getByText(/the face decides/i)).toBeInTheDocument();
    expect(screen.getByText("supports")).toBeInTheDocument(); // the body only supports when the face decides
    expect(screen.getByRole("img", { name: "Face found in the query picture" })).toBeInTheDocument();
    const cues = screen.getByRole("table");
    expect(within(cues).getByText("Upper clothing")).toBeInTheDocument();
    expect(within(cues).getByText("Hair colour")).toBeInTheDocument();
    expect(within(cues).getByText("Similar")).toBeInTheDocument();
    expect(within(cues).getByText("Different")).toBeInTheDocument(); // a colour that differs is shown, not hidden
    expect(screen.getByText(/not part of the decision rule/i)).toBeInTheDocument();
  });

  it("explains in plain words when there was no usable face and the body had to decide", () => {
    const response = faceBodyResponse("review_required");
    const person = response.people[0];
    person.decision = { ...person.decision, basis: "body", face_status: "no_face", top1_face_score: null, top1_body_score: 0.93, face_threshold: 0.363, body_threshold: 0.7, top1_score: 0.93, accept_threshold: 0.7 };
    person.face = { status: "no_face", box: null, detector_score: null, face_px: null, flags: [], message: "No face was found in this picture, so only the body could be compared." };
    person.candidates = [{ ...person.candidates[0], basis: "body", face_score: null, face_box: null, body_score: 0.93, score: 0.93 }];
    person.cues = [];
    wrap(<EvidencePanel person={person} imageUrl="blob:query" />);
    expect(screen.getByText("Decided by the body")).toBeInTheDocument();
    expect(screen.getByText("No face found")).toBeInTheDocument();
    expect(screen.getAllByText(/only the body.*could be compared/i).length).toBeGreaterThan(0); // the explanation and the face row say it
    expect(screen.getByText("0.930")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("names the reason when a face was found but could not be used", () => {
    const response = faceBodyResponse("review_required");
    const person = response.people[0];
    person.decision = { ...person.decision, basis: "body", face_status: "unusable", top1_face_score: null, top1_body_score: 0.9 };
    person.face = { status: "unusable", box: [20, 6, 40, 20], detector_score: 0.9, face_px: 20, flags: ["face_small"], message: "A face was found but it is not usable: The face is too small in the picture to compare reliably." };
    wrap(<EvidencePanel person={person} imageUrl="blob:query" />);
    expect(screen.getByText("Face found but not usable")).toBeInTheDocument();
    expect(screen.getByText(/Face too small/)).toBeInTheDocument();
  });
});

describe("Match Studio with face matching", () => {
  it("shows the Evidence card for a face + body result, and only then", async () => {
    mockApi({ "POST /api/reid/predict": () => faceBodyResponse("accepted") });
    renderApp("/match");
    await userEvent.upload(await screen.findByLabelText("Choose an image file"), imageFile("face.png"));
    await userEvent.click(screen.getByRole("checkbox", { name: /already a person crop/i }));
    await userEvent.click(screen.getByRole("button", { name: /run re-identification/i }));
    expect(await screen.findByText("Decided by the face")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evidence" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /face found for person 1: usable/i })).toBeInTheDocument();
  });

  it("a body-only result keeps the original layout (no Evidence card)", async () => {
    mockApi({ "POST /api/reid/predict": () => predictResponse("accepted") });
    renderApp("/match");
    await userEvent.upload(await screen.findByLabelText("Choose an image file"), imageFile());
    await userEvent.click(screen.getByRole("button", { name: /run re-identification/i }));
    expect((await screen.findAllByText("Match")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Evidence" })).not.toBeInTheDocument();
  });
});

describe("Identity gallery with faces", () => {
  it("shows which people have a usable face on file, and warns about those who do not", async () => {
    mockApi({ "GET /api/gallery": () => galleryPage([identity("with-face", { n_faces: 3 }), identity("without-face", { n_faces: 0 })]) });
    renderApp("/gallery");
    expect(await screen.findByText("3 of 3 with a face")).toBeInTheDocument();
    expect(screen.getByText("No face on file")).toBeInTheDocument();
  });

  it("'Analyse faces' asks the server to fingerprint the faces of photos enrolled before face matching", async () => {
    const api = mockApi({
      "GET /api/gallery": () => ({ ...galleryPage([identity("older", { n_faces: 0 })]), summary: { ...galleryPage([identity("older")]).summary, faces_not_analysed: 3, face_model: "face-x" } }),
      "POST /api/gallery/analyse-faces": () => ({ ok: true, message: "Analysed 3 reference picture(s): 3 with a usable face.", detail: {} }),
    });
    renderApp("/gallery");
    expect(await screen.findByText(/3 reference photo\(s\) have not had their face analysed/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /analyse faces/i }));
    await waitFor(() => expect(api.called("POST", "/api/gallery/analyse-faces")).toHaveLength(1));
    expect(await screen.findByText(/analysed 3 reference picture/i)).toBeInTheDocument();
  });
});

describe("Model & thresholds with face matching", () => {
  const status = {
    embedding: { ready: true, architecture: "OSNet-AIN x1.0", embedding_dim: 512, weights: "official", device: "cpu", fingerprint: "osnet-abc-flip0" },
    detector: { ready: true }, device: {}, gallery_index: { version: 1, identities: 0, images: 0 },
    face: { ready: true, enabled: true, display_name: "YuNet detector + SFace recogniser", embedding_dim: 128, enrolled_faces: 4, identities_with_a_face: 2,
            weights_verified_against_pinned_hash: true, usable_face_rules: { min_face_px: 40, min_detector_confidence: 0.8, max_turn_ratio: 0.45, min_sharpness: 10 } },
  };
  const faceBody = policy({ matching_mode: "face_body", face_accept_threshold: 0.363, face_review_band: 0.08, body_only_action: "review" });

  it("shows the active mode, the face threshold and the loaded face models", async () => {
    mockApi({ "GET /api/model/status": () => status, "GET /api/config/history": () => [faceBody], "GET /api/config": () => config({ policy: faceBody }) });
    renderApp("/settings");
    expect(await screen.findByText("Face + body")).toBeInTheDocument();
    expect(screen.getByText("YuNet detector + SFace recogniser")).toBeInTheDocument();
    expect(screen.getByText(/4 reference faces from 2 people/)).toBeInTheDocument();
    expect(screen.getByText(/at least 40 px wide/)).toBeInTheDocument();
  });

  it("sends the chosen mode and face threshold, after a confirmation that names the consequence", async () => {
    const api = mockApi({
      "GET /api/model/status": () => status, "GET /api/config/history": () => [faceBody], "GET /api/config": () => config({ policy: faceBody }),
      "POST /api/config/thresholds": () => policy({ version: 2, matching_mode: "face_body", face_accept_threshold: 0.45, status: "experimental" }),
    });
    renderApp("/settings");
    const field = await screen.findByLabelText("Face threshold");
    await userEvent.clear(field);
    await userEvent.type(field, "0.45");
    await userEvent.click(screen.getByRole("button", { name: /save settings/i }));
    const dialog = await screen.findByRole("dialog", { name: /apply these decision rules/i });
    expect(within(dialog).getByText(/face \+ body matching \(face threshold 0\.45\)/i)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: /apply to live decisions/i }));
    await waitFor(() => expect(api.called("POST", "/api/config/thresholds")).toHaveLength(1));
    expect(api.called("POST", "/api/config/thresholds")[0].body).toMatchObject({ matching_mode: "face_body", face_accept_threshold: 0.45, body_only_action: "review", confirm: true });
  });

  it("switching to body-only hides the face controls and says what is sent", async () => {
    const api = mockApi({
      "GET /api/model/status": () => status, "GET /api/config/history": () => [faceBody], "GET /api/config": () => config({ policy: faceBody }),
      "POST /api/config/thresholds": () => policy({ version: 2, status: "experimental" }),
    });
    renderApp("/settings");
    await userEvent.selectOptions(await screen.findByLabelText("Matching mode"), "body");
    expect(screen.queryByLabelText("Face threshold")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /save settings/i }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: /apply to live decisions/i }));
    await waitFor(() => expect(api.called("POST", "/api/config/thresholds")).toHaveLength(1));
    const sent = api.called("POST", "/api/config/thresholds")[0].body as Record<string, unknown>;
    expect(sent.matching_mode).toBe("body");
    expect(sent).not.toHaveProperty("face_accept_threshold");
  });

  it("warns when the policy asks for faces but the models are not loaded", async () => {
    const notLoaded = policy({ matching_mode: "face_body", face_accept_threshold: 0.363, face_review_band: 0.08, body_only_action: "review", face_models_loaded: false });
    mockApi({ "GET /api/model/status": () => ({ ...status, face: { ready: false, enabled: true, error: "weights missing", enrolled_faces: 0, identities_with_a_face: 0 } }), "GET /api/config/history": () => [notLoaded], "GET /api/config": () => config({ policy: notLoaded }) });
    renderApp("/settings");
    expect((await screen.findAllByText(/face models are not loaded/i)).length).toBeGreaterThan(0);
  });
});

describe("How it works", () => {
  it("is reachable from the top bar, explains the three answers and the limits, and shows the live thresholds", async () => {
    const live = policy({ matching_mode: "face_body", face_accept_threshold: 0.465, face_review_band: 0.1, body_only_action: "review" });
    mockApi({ "GET /api/config": () => config({ policy: live }) });
    renderApp("/");
    await userEvent.click(await screen.findByRole("link", { name: /how it works/i }));
    expect(await screen.findByRole("heading", { level: 1, name: "How it works" })).toBeInTheDocument();
    for (const outcome of ["Match", "Unknown", "Review"]) expect(screen.getAllByText(outcome).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: /what it cannot do/i })).toBeInTheDocument();
    expect(screen.getByText(/a phone's Face ID/i)).toBeInTheDocument();
    expect(await screen.findByText("0.465")).toBeInTheDocument(); // read from the backend, not typed into the page
    expect(screen.getByRole("img", { name: /two different people wearing the same blue jacket/i })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Processing steps" }).children).toHaveLength(7);
  });

  it("says plainly when the active policy does not use the face", async () => {
    mockApi({ "GET /api/config": () => config({ policy: policy() }) });
    renderApp("/how-it-works");
    expect(await screen.findByText(/the active policy is body-only/i)).toBeInTheDocument();
    expect(await screen.findByText(/not in use: body-only policy/i)).toBeInTheDocument();
  });
});