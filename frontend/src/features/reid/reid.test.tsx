import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { predictResponse } from "@/test/fixtures";
import { CandidatePanel } from "./CandidatePanel";
import { DecisionSummary } from "./DecisionSummary";
import { buildSummary } from "./ResultActions";

function wrap(node: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

/** The small card holding one labelled metric (label + value), e.g. "Calibrated confidence". */
function metric(label: string): HTMLElement {
  return screen.getByText(label).closest("div")!.parentElement!;
}

describe("DecisionSummary", () => {
  it("shows an accepted match with its real numbers, and names the reference ID", () => {
    const response = predictResponse("accepted");
    wrap(<DecisionSummary person={response.people[0]} response={response} total={1} />);
    expect(screen.getByText("Match")).toBeInTheDocument();
    expect(screen.getByText("Selected reference ID")).toBeInTheDocument();
    expect(screen.getAllByText("subject-001").length).toBeGreaterThan(0);
    expect(screen.getByText("0.813")).toBeInTheDocument(); // similarity, as a score
    expect(screen.getAllByText("0.700").length).toBeGreaterThan(0); // threshold
    expect(screen.getByText("281 ms")).toBeInTheDocument(); // measured inference time
  });

  it("presents an unknown outcome as unknown - not as a success - and never invents a selected identity", () => {
    const response = predictResponse("unknown");
    wrap(<DecisionSummary person={response.people[0]} response={response} total={1} />);
    expect(screen.getByText("Unknown")).toBeInTheDocument();
    expect(screen.queryByText("Selected reference ID")).not.toBeInTheDocument();
    expect(screen.queryByText("Match")).not.toBeInTheDocument();
    expect(screen.getByText(/below the acceptance threshold/)).toBeInTheDocument();
    expect(screen.getByText(/not a finding about the person/i)).toBeInTheDocument();
  });

  it("does not turn similarity into a percentage, and labels the calibrated confidence as unavailable", () => {
    const response = predictResponse("accepted");
    wrap(<DecisionSummary person={response.people[0]} response={response} total={1} />);
    expect(screen.queryByText(/81\.3\s?%/)).not.toBeInTheDocument();
    expect(metric("Calibrated confidence")).toHaveTextContent("Not available");
  });

  it("shows a calibrated confidence only when the backend supplied one, separately from similarity", () => {
    const response = predictResponse("accepted");
    response.people[0].decision.calibrated_confidence = 0.947;
    wrap(<DecisionSummary person={response.people[0]} response={response} total={1} />);
    expect(screen.getByText("94.7%")).toBeInTheDocument();
    expect(screen.getByText("0.813")).toBeInTheDocument();
  });

  it("keeps detector confidence separate from the identity score", () => {
    const response = predictResponse("accepted");
    response.people[0].detector_score = 0.99;
    wrap(<DecisionSummary person={response.people[0]} response={response} total={1} />);
    expect(metric("Detector confidence")).toHaveTextContent("0.99");
    expect(metric("Detector confidence")).not.toHaveTextContent("0.813"); // the similarity lives elsewhere
  });

  it("lists quality flags for review outcomes", () => {
    const response = predictResponse("review_required");
    wrap(<DecisionSummary person={response.people[0]} response={response} total={2} />);
    expect(screen.getByText("Blurry")).toBeInTheDocument();
    expect(screen.getByText("Person 1 of 2")).toBeInTheDocument();
  });
});

describe("CandidatePanel", () => {
  it("keeps every candidate visible, highlights the accepted one and marks nothing below threshold as accepted", () => {
    const response = predictResponse("accepted");
    wrap(<CandidatePanel person={response.people[0]} onReview={() => {}} />);
    const list = screen.getByRole("list", { name: "Ranked candidates" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveAttribute("aria-current", "true");
    expect(within(items[0]).getByText("Match")).toBeInTheDocument();
    expect(within(items[1]).getByText("Below threshold")).toBeInTheDocument();
  });

  it("says 'no supported match' and calls the nearest neighbour only the closest candidate", () => {
    const response = predictResponse("unknown");
    wrap(<CandidatePanel person={response.people[0]} onReview={() => {}} />);
    expect(screen.getByText("No supported match")).toBeInTheDocument();
    expect(screen.getByText("Closest candidate (not a match)")).toBeInTheDocument();
    expect(screen.queryByText("Match")).not.toBeInTheDocument();
  });

  it("offers 'Review candidates' only for review outcomes", async () => {
    const onReview = vi.fn();
    const review = predictResponse("review_required");
    const { unmount } = wrap(<CandidatePanel person={review.people[0]} onReview={onReview} />);
    await userEvent.click(screen.getByRole("button", { name: /review candidates/i }));
    expect(onReview).toHaveBeenCalledOnce();
    unmount();
    wrap(<CandidatePanel person={predictResponse("unknown").people[0]} onReview={onReview} />);
    expect(screen.queryByRole("button", { name: /review candidates/i })).not.toBeInTheDocument();
  });

  it("shows a clear empty-gallery state instead of an empty list", () => {
    const response = predictResponse("unknown");
    response.people[0].candidates = [];
    wrap(<CandidatePanel person={response.people[0]} onReview={() => {}} />);
    expect(screen.getByText("The gallery is empty")).toBeInTheDocument();
  });
});

describe("exported result summary", () => {
  it("contains decisions and scores only - no images, crops or embeddings", () => {
    const summary = buildSummary(predictResponse("accepted"));
    const { note, ...data } = summary; // the explanatory note itself says "no embeddings", so check the data
    expect(JSON.stringify(data)).not.toMatch(/embedding|image_url|crop_url|base64/i);
    expect(note).toMatch(/No images/);
    expect(summary.people[0]).toMatchObject({ outcome: "accepted", accepted_reference_id: "subject-001", similarity_top1: 0.813 });
  });
});
