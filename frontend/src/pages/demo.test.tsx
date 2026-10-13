/**
 * The home page's built-in example: enroll / match / open-set analysis, as an interviewer would meet it.
 * As elsewhere: the real application, a pretend server, and assertions about what a person would see.
 */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { apiError, mockApi, renderApp, type Handler } from "@/test/utils";
import { demoCaseResult, demoInfo, demoPrepared, DEMO_ANSWERS, overview } from "@/test/fixtures";

beforeAll(async () => {
  await Promise.all([import("@/pages/CommandCenterPage"), import("@/pages/MatchStudioPage")]);
}, 120_000);

/** A pretend server for the example: it builds the gallery, then answers each photo from the fixtures. */
const demoServer = (over: Record<string, Handler> = {}) => ({
  "POST /api/demo/prepare": () => demoPrepared(),
  ...Object.fromEntries(Object.keys(DEMO_ANSWERS).map((id) => [`POST /api/demo/cases/${id}`, (() => demoCaseResult(id)) as Handler])),
  ...over,
});

const runButtons = () => screen.getAllByRole("button", { name: /^run the example$/i });

async function runExample(api: ReturnType<typeof mockApi>) {
  await userEvent.click((await screen.findAllByRole("button", { name: /^run the example$/i }))[0]);
  expect(await screen.findByText("What the example shows")).toBeInTheDocument();
  return api;
}

describe("home page: the essentials first", () => {
  it("leads with enroll / match / open-set analysis, then the example, then the live status", async () => {
    mockApi();
    renderApp("/");
    await screen.findByRole("heading", { level: 2, name: /the essentials in three steps/i });
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent ?? "");
    const at = (pattern: RegExp) => headings.findIndex((h) => pattern.test(h));
    expect(at(/essentials/i)).toBeGreaterThanOrEqual(0);
    expect(at(/essentials/i)).toBeLessThan(at(/open-set example/i));
    expect(at(/open-set example/i)).toBeLessThan(at(/live system status/i));

    const essentials = within(screen.getByRole("region", { name: /the essentials in three steps/i }));
    const steps = essentials.getAllByRole("listitem").filter((li) => /^(To do|Done): /.test(li.textContent ?? ""));
    expect(steps).toHaveLength(3);
    ["1. Enroll people", "2. Match photos", "3. See the open-set analysis"].forEach((title, i) => expect(steps[i]).toHaveTextContent(title));
    expect(screen.getByRole("link", { name: /enroll a person/i })).toHaveAttribute("href", "/gallery");
    expect(screen.getByRole("link", { name: /match a photo/i })).toHaveAttribute("href", "/match");
  });

  it("shows what is enrolled and ticks the first two steps from real data", async () => {
    mockApi({ "GET /api/overview": () => overview({
      gallery: { identities: 2, images: 6 },
      inference: { requests: 1, people_processed: 1, outcomes: { accepted: 1 }, unknown_or_rejected: 0, acceptance_rate: 1, acceptance_rate_definition: "x", average_latency_ms: 900, latency_window: "w" },
    }) });
    renderApp("/");
    expect(await screen.findByText(/2 people enrolled · 6 photos/)).toBeInTheDocument();
    expect(screen.getByText(/1 photo checked so far/)).toBeInTheDocument();
    const essentials = within(screen.getByRole("region", { name: /the essentials in three steps/i }));
    expect(essentials.getAllByText(/^Done:$/)).toHaveLength(2);
    expect(essentials.getAllByText(/^To do:$/)).toHaveLength(1);
  });

  it("warns that matching a photo is pointless until someone is enrolled", async () => {
    mockApi();
    renderApp("/");
    expect(await screen.findByText(/Enroll someone first: with nobody enrolled, every answer is UNKNOWN/)).toBeInTheDocument();
    expect(screen.getByText("No one is enrolled yet")).toBeInTheDocument();
  });

  it("is linked from the How it works tour, next to the illustration it makes real", async () => {
    mockApi(demoServer());
    renderApp("/how-it-works");
    const link = await screen.findByRole("link", { name: /see it with real photos/i });
    expect(link).toHaveAttribute("href", "/");
    await userEvent.click(link);
    expect(await screen.findByRole("heading", { level: 2, name: /open-set example/i })).toBeInTheDocument();
  });

  it("keeps the live figures further down, and still shows the example when the status cannot be loaded", async () => {
    mockApi({ "GET /api/overview": () => apiError(500, "internal_error", "Something went wrong on the server.") });
    renderApp("/");
    expect(await screen.findByRole("alert")).toHaveTextContent(/something went wrong/i);
    expect(screen.getByRole("heading", { level: 2, name: /open-set example/i })).toBeInTheDocument();
    expect(screen.getByText("The 6 photos, and what each matcher decided")).toBeInTheDocument();
  });
});

describe("home page: the open-set example", () => {
  it("describes the example before it is run: who is enrolled, the photos, the right answers, and what it will not do", async () => {
    const api = mockApi(demoServer());
    renderApp("/");
    expect(await screen.findByText("Who the system knows")).toBeInTheDocument();
    for (const name of ["Example person 1", "Example person 2", "Example person 3"]) expect(screen.getAllByText(name).length).toBeGreaterThan(0);
    for (const title of ["Known people, seen again", "Known person, but no usable face", "Strangers (never enrolled)", "Strangers in the SAME clothes as an enrolled person"]) {
      expect(screen.getByRole("heading", { level: 4, name: title })).toBeInTheDocument();
    }
    const row = document.querySelector('[data-case="same-1"]') as HTMLElement;
    expect(within(row).getByText("A stranger in the same orange flight suit (1)")).toBeInTheDocument();
    expect(within(row).getByText(/UNKNOWN - this person was never enrolled/)).toBeInTheDocument();
    expect(within(row).getAllByText("Not run yet")).toHaveLength(2);
    expect(screen.getByText(/not a benchmark/i)).toBeInTheDocument();
    expect(screen.getByText(/face line 0\.465 · clothes line 0\.7 /)).toBeInTheDocument();
    expect(api.calls.filter((c) => c.path.startsWith("/api/demo/") && c.method === "POST")).toHaveLength(0); // nothing runs by itself
  });

  it("runs the example photo by photo and lays out the comparison", async () => {
    const api = mockApi(demoServer());
    renderApp("/");
    await runExample(api);

    expect(api.called("POST", "/api/demo/prepare")).toHaveLength(1);
    expect(api.calls.filter((c) => c.method === "POST" && c.path.startsWith("/api/demo/cases/")).map((c) => c.path.split("/").pop())).toEqual(demoInfo().cases.map((c) => c.id));

    const table = screen.getByRole("table", { name: /judged by the system/i });
    const rowOf = (name: RegExp) => within(table).getByRole("row", { name });
    expect(within(rowOf(/Known people recognised/)).getAllByRole("cell").map((c) => c.textContent)).toEqual(["2 of 2 (good)", "0 of 2 (not good)"]);
    expect(within(rowOf(/^Strangers wrongly accepted/)).getAllByRole("cell").map((c) => c.textContent)).toEqual(["0 of 3 (good)", "2 of 3 (not good)"]);
    expect(within(rowOf(/same clothes as an enrolled person/)).getAllByRole("cell").map((c) => c.textContent)).toEqual(["0 of 2 (good)", "2 of 2 (not good)"]);
    expect(within(rowOf(/no usable face sent to a person/)).getAllByRole("cell").map((c) => c.textContent)).toEqual(["1 of 1 (good)", "0 of 1 (not good)"]);
    expect(within(rowOf(/decided exactly right/)).getAllByRole("cell").map((c) => c.textContent)).toEqual(["6 of 6 (good)", "1 of 6 (not good)"]);

    expect(screen.getByText(/A clothes-only matcher accepted 2 of 2 strangers who were dressed like an enrolled person\./)).toBeInTheDocument();
    expect(screen.getByText(/Face \+ body gave the right answer for all 6 photos\./)).toBeInTheDocument();
  });

  it("marks every answer: the stranger in the same clothes is accepted by clothes alone and refused by the face", async () => {
    const api = mockApi(demoServer());
    renderApp("/");
    await runExample(api);
    const row = document.querySelector('[data-case="same-1"]') as HTMLElement;
    expect(within(row).getByText("Right answer")).toBeInTheDocument(); // the system's verdict
    expect(within(row).getByText("Stranger accepted")).toBeInTheDocument(); // the clothes-only verdict
    expect(within(row).getByText(/Named:/).parentElement).toHaveTextContent("Example person 1");
    expect(within(row).getByText(/Face similarity/)).toHaveTextContent("0.15");
    expect(within(row).getByText(/Clothes and build similarity/)).toHaveTextContent("0.79");
    expect(within(row).getByText(/Clothing similarity alone is NOT accepted/)).toBeInTheDocument(); // the reason, behind "Why this answer"

    const noFace = document.querySelector('[data-case="noface-1"]') as HTMLElement;
    expect(within(noFace).getByText("Review")).toBeInTheDocument(); // REVIEW is the right, cautious answer for the system
    expect(within(noFace).getByText("Accepted on clothes alone")).toBeInTheDocument();
    expect(within(noFace).getByText("No face found")).toBeInTheDocument();
  });

  it("draws the face and clothing plots with their lines and explains what the gap means", async () => {
    const api = mockApi(demoServer());
    renderApp("/");
    await runExample(api);
    expect(screen.getByRole("img", { name: /^Face similarity\..*Face line 0\.465/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /^Clothing and build similarity\..*Clothes line 0\.7\./ })).toBeInTheDocument();
    expect(screen.getByText(/every stranger with a visible face scored at most/i)).toHaveTextContent("0.55");
    expect(screen.getByText(/Strangers in the same clothes scored/)).toHaveTextContent("0.79–0.81");
  });

  it("lets you move the face line and shows who would get in", async () => {
    const api = mockApi(demoServer());
    renderApp("/");
    await runExample(api);
    const slider = screen.getByRole("slider", { name: /move the face line/i });
    expect(slider).toHaveValue("0.465");
    expect(screen.getByText(/known people recognised/i, { selector: "p" })).toHaveTextContent("2 of 2");
    expect(screen.getByText(/known people recognised/i, { selector: "p" })).toHaveTextContent("strangers wrongly accepted 0 of 3");

    fireEvent.change(slider, { target: { value: "0.1" } });
    expect(screen.getByText(/strangers wrongly accepted/i, { selector: "p" })).toHaveTextContent("strangers wrongly accepted 3 of 3");
    expect(screen.getByText(/strangers start getting in/i)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /^Face similarity\..*Your line 0\.1\./ })).toBeInTheDocument();

    fireEvent.change(slider, { target: { value: "0.6" } });
    expect(screen.getByText(/known people start being missed/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /back to the system's 0\.465/i }));
    expect(slider).toHaveValue("0.465");
  });

  it("ticks the third essential and keeps the results when you visit another screen and come back", async () => {
    const api = mockApi(demoServer());
    renderApp("/");
    await runExample(api);
    expect(screen.getByRole("button", { name: /show the results/i })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: /the essentials in three steps/i })).getAllByText(/^Done:$/)).toHaveLength(1);

    const nav = screen.getByRole("navigation", { name: "Main" });
    await userEvent.click(within(nav).getByRole("link", { name: "Match Studio" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Match Studio" })).toBeInTheDocument();
    await userEvent.click(within(nav).getByRole("link", { name: "Command Center" }));
    expect(await screen.findByText("What the example shows")).toBeInTheDocument();
    expect(api.called("POST", "/api/demo/prepare")).toHaveLength(1); // not run a second time
  });

  it("can be run again", async () => {
    const api = mockApi(demoServer());
    renderApp("/");
    await runExample(api);
    await userEvent.click(screen.getByRole("button", { name: /run it again/i }));
    await waitFor(() => expect(api.called("POST", "/api/demo/prepare")).toHaveLength(2));
    expect(await screen.findByText("What the example shows")).toBeInTheDocument();
  });

  it("says plainly when it stops half-way, and offers to try again", async () => {
    let failing = true;
    const api = mockApi(demoServer({ "POST /api/demo/cases/known-2": () => (failing ? apiError(503, "model_unavailable", "The face models are not loaded.") : demoCaseResult("known-2")) }));
    renderApp("/");
    await userEvent.click((await screen.findAllByRole("button", { name: /^run the example$/i }))[0]);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/the example stopped/i);
    expect(alert).toHaveTextContent(/face models are not loaded/i);
    expect(screen.queryByText("What the example shows")).not.toBeInTheDocument();

    failing = false;
    await userEvent.click(within(alert).getByRole("button", { name: /try again/i }));
    expect(await screen.findByText("What the example shows")).toBeInTheDocument();
    expect(api.called("POST", "/api/demo/prepare")).toHaveLength(2);
  });

  it("explains when the server cannot run it, and does not offer to", async () => {
    const api = mockApi({ "GET /api/demo": () => demoInfo({ available: false, reason: "The face models are not loaded, so the example cannot compare faces.", cases: [], people: [], groups: [] }) });
    renderApp("/");
    expect(await screen.findByText("The example is not available on this server")).toBeInTheDocument();
    expect(screen.getByText(/face models are not loaded/i)).toBeInTheDocument();
    expect(screen.getByText("Not available on this server")).toBeInTheDocument();
    expect(runButtons()[0]).toBeDisabled();
    expect(api.calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("scrolls to the example when the third essential is used", async () => {
    const api = mockApi(demoServer());
    renderApp("/");
    const scrolled: string[] = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function scroll(this: Element) { scrolled.push(this.id); };
    try {
      await userEvent.click((await screen.findAllByRole("button", { name: /^run the example$/i }))[0]);
      expect(scrolled).toContain("open-set-example");
      await screen.findByText("What the example shows");
      expect(api.called("POST", "/api/demo/prepare")).toHaveLength(1);
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });
});
