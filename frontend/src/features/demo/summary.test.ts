/** The example's counting rules: they only add up the server's verdicts, so these tests pin the sums and the sentences. */
import { describe, expect, it } from "vitest";
import { demoCaseResult, demoInfo } from "@/test/fixtures";
import type { DemoCaseResult } from "@/types/api";
import { conclusion, faceGap, ofTotal, tally, whatIfFace } from "./summary";

const info = demoInfo();
const all: Record<string, DemoCaseResult> = Object.fromEntries(info.cases.map((c) => [c.id, demoCaseResult(c.id)]));

describe("tally", () => {
  it("counts what face + body got right and wrong", () => {
    const t = tally(info.cases, all, "face_body");
    expect(t.known).toEqual({ total: 2, matched: 2, sentToReview: 0, missed: 0, wrongPerson: 0 });
    expect(t.strangers).toEqual({ total: 3, rejected: 3, sentToReview: 0, falseAccepted: 0 });
    expect(t.lookalikes).toEqual({ total: 2, rejected: 2, sentToReview: 0, falseAccepted: 0 });
    expect(t.noFace).toEqual({ total: 1, sentToReview: 1, acceptedOnClothes: 0, other: 0 });
    expect([t.right, t.analysed]).toEqual([6, 6]);
  });

  it("counts a clothes-only matcher missing known people and accepting strangers in the same clothes", () => {
    const t = tally(info.cases, all, "clothes_only");
    expect(t.known).toMatchObject({ total: 2, matched: 0, missed: 2 });
    expect(t.strangers).toMatchObject({ total: 3, rejected: 1, falseAccepted: 2 });
    expect(t.lookalikes).toMatchObject({ total: 2, falseAccepted: 2 });
    expect(t.noFace).toMatchObject({ total: 1, sentToReview: 0, acceptedOnClothes: 1 });
    expect([t.right, t.analysed]).toEqual([1, 6]);
  });

  it("counts only the photos analysed so far", () => {
    const t = tally(info.cases, { "known-1": all["known-1"] }, "face_body");
    expect(t.analysed).toBe(1);
    expect(t.known.total).toBe(1);
    expect(t.strangers.total).toBe(0);
  });

  it("separates a wrong person from a missed person, and sends everything cautious to 'review'", () => {
    const wrong = demoCaseResult("known-1");
    wrong.face_body = { ...wrong.face_body, verdict: "wrong_person" };
    const cautious = demoCaseResult("stranger-1");
    cautious.face_body = { ...cautious.face_body, outcome: "review_required", verdict: "review" };
    const t = tally(info.cases, { "known-1": wrong, "stranger-1": cautious }, "face_body");
    expect(t.known).toMatchObject({ matched: 0, wrongPerson: 1, missed: 0 });
    expect(t.strangers).toMatchObject({ rejected: 0, sentToReview: 1, falseAccepted: 0 });
  });
});

describe("conclusion", () => {
  const faceBody = tally(info.cases, all, "face_body");
  const clothes = tally(info.cases, all, "clothes_only");

  it("waits until every photo has been analysed", () => {
    expect(conclusion(6, tally(info.cases, { "known-1": all["known-1"] }, "face_body"), clothes)).toBeNull();
  });

  it("states what happened, with the denominators", () => {
    const text = conclusion(6, faceBody, clothes);
    expect(text).toContain("A clothes-only matcher accepted 2 of 2 strangers who were dressed like an enrolled person.");
    expect(text).toContain("With the face as well, none of them was accepted.");
    expect(text).toContain("Clothes alone recognised 0 of 2 known people");
    expect(text).toContain("face + body recognised 2 of 2");
    expect(text).toContain("Face + body gave the right answer for all 6 photos.");
  });

  it("does not claim success when the system itself got something wrong", () => {
    const flawed = { ...all, "same-1": { ...all["same-1"], face_body: { ...all["same-1"].face_body, outcome: "accepted" as const, verdict: "false_accept" as const } } };
    const t = tally(info.cases, flawed, "face_body");
    const text = conclusion(6, t, clothes);
    expect(text).toContain("With the face as well, 1 of those 2 were still accepted.");
    expect(text).toContain("right answer for 5 of 6 photos");
    expect(text).not.toContain("all 6 photos");
  });
});

describe("the face line", () => {
  it("finds the gap between the lowest known person and the highest stranger", () => {
    expect(faceGap(info.cases, all)).toEqual({ lowestKnown: 0.55, highestStranger: 0.18 });
  });

  it("counts who would be accepted at another line", () => {
    expect(whatIfFace(info.cases, all, 0.465)).toEqual({ knownTotal: 2, knownAccepted: 2, strangerTotal: 3, strangerAccepted: 0 });
    expect(whatIfFace(info.cases, all, 0.6)).toMatchObject({ knownAccepted: 1, strangerAccepted: 0 });
    expect(whatIfFace(info.cases, all, 0.1)).toMatchObject({ knownAccepted: 2, strangerAccepted: 3 });
  });

  it("does not credit a known person whose closest face belongs to someone else", () => {
    const confused = demoCaseResult("known-1");
    confused.face_body = { ...confused.face_body, top1_person: "person2" };
    expect(whatIfFace(info.cases, { "known-1": confused }, 0.1)).toMatchObject({ knownTotal: 1, knownAccepted: 0 });
  });

  it("ignores photos with no usable face", () => {
    expect(whatIfFace(info.cases, { "noface-1": all["noface-1"] }, 0.1)).toEqual({ knownTotal: 0, knownAccepted: 0, strangerTotal: 0, strangerAccepted: 0 });
  });
});

describe("ofTotal", () => {
  it("writes 'n of m'", () => expect(ofTotal(3, 6)).toBe("3 of 6"));
});
