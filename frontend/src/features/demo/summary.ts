/**
 * Counting up the example's results.
 *
 * In plain words: the server decides each photo and says whether the decision was right. This file only COUNTS those
 * verdicts (how many known people were recognised, how many strangers were wrongly accepted ...) and turns the counts
 * into a plain sentence. It never decides anything itself, so the numbers on screen are exactly what the server measured.
 */
import type { DemoCase, DemoCaseResult, DemoDecision } from "@/types/api";

/** The group of strangers who wear the same clothes as an enrolled person (the heart of the "low inter-class variance" problem). */
export const LOOKALIKE_GROUP = "lookalike";

export type Column = "face_body" | "clothes_only";

export interface Tally {
  /** Known people photographed in new clothes (right answer: MATCH). */
  known: { total: number; matched: number; sentToReview: number; missed: number; wrongPerson: number };
  /** Every stranger (right answer: UNKNOWN), including the ones dressed like an enrolled person. */
  strangers: { total: number; rejected: number; sentToReview: number; falseAccepted: number };
  /** Only the strangers dressed like an enrolled person. */
  lookalikes: { total: number; rejected: number; sentToReview: number; falseAccepted: number };
  /** Known people whose face cannot be used (right answer: REVIEW). */
  noFace: { total: number; sentToReview: number; acceptedOnClothes: number; other: number };
  /** Photos decided exactly right, and photos analysed so far. */
  right: number;
  analysed: number;
}

const blank = (): Tally => ({
  known: { total: 0, matched: 0, sentToReview: 0, missed: 0, wrongPerson: 0 },
  strangers: { total: 0, rejected: 0, sentToReview: 0, falseAccepted: 0 },
  lookalikes: { total: 0, rejected: 0, sentToReview: 0, falseAccepted: 0 },
  noFace: { total: 0, sentToReview: 0, acceptedOnClothes: 0, other: 0 },
  right: 0,
  analysed: 0,
});

export function tally(cases: DemoCase[], results: Record<string, DemoCaseResult | undefined>, column: Column): Tally {
  const t = blank();
  for (const c of cases) {
    const result = results[c.id];
    if (!result) continue;
    const d: DemoDecision = result[column];
    t.analysed += 1;
    if (d.verdict === "correct") t.right += 1;
    if (c.expect.kind === "match") {
      t.known.total += 1;
      if (d.verdict === "correct") t.known.matched += 1;
      else if (d.verdict === "review") t.known.sentToReview += 1;
      else if (d.verdict === "wrong_person") t.known.wrongPerson += 1;
      else t.known.missed += 1;
    } else if (c.expect.kind === "unknown") {
      const groups = c.group === LOOKALIKE_GROUP ? [t.strangers, t.lookalikes] : [t.strangers];
      for (const g of groups) {
        g.total += 1;
        if (d.verdict === "correct") g.rejected += 1;
        else if (d.verdict === "false_accept") g.falseAccepted += 1;
        else g.sentToReview += 1;
      }
    } else {
      t.noFace.total += 1;
      if (d.verdict === "correct") t.noFace.sentToReview += 1;
      else if (d.verdict === "risky") t.noFace.acceptedOnClothes += 1;
      else t.noFace.other += 1;
    }
  }
  return t;
}

/** 0.465 and 0.7 (not 0.47 and 0.70): a threshold is written with the digits it really has. */
export const plain = (value: number) => String(Number(value.toFixed(3)));

/** "3 of 6" - the way every figure on the page is written, so a reader never has to guess the denominator. */
export const ofTotal = (n: number, total: number) => `${n} of ${total}`;

/**
 * The plain-language conclusion, built only from the counts. It states what happened on THESE photos; it does not claim
 * more. Returns null until every photo has been analysed.
 */
export function conclusion(total: number, faceBody: Tally, clothes: Tally): string | null {
  if (total === 0 || faceBody.analysed < total || clothes.analysed < total) return null;
  const parts: string[] = [];
  const wrong = total - faceBody.right;

  if (clothes.lookalikes.total > 0) {
    parts.push(
      clothes.lookalikes.falseAccepted > 0
        ? `A clothes-only matcher accepted ${ofTotal(clothes.lookalikes.falseAccepted, clothes.lookalikes.total)} strangers who were dressed like an enrolled person.`
        : `A clothes-only matcher did not accept any of the ${clothes.lookalikes.total} strangers dressed like an enrolled person.`,
    );
    parts.push(
      faceBody.lookalikes.falseAccepted > 0
        ? `With the face as well, ${faceBody.lookalikes.falseAccepted} of those ${faceBody.lookalikes.total} were still accepted.`
        : `With the face as well, none of them was accepted.`,
    );
  }
  if (clothes.known.total > 0 && clothes.known.matched < clothes.known.total) {
    parts.push(
      `Clothes alone recognised ${ofTotal(clothes.known.matched, clothes.known.total)} known people photographed in different clothes; face + body recognised ${ofTotal(faceBody.known.matched, faceBody.known.total)}.`,
    );
  }
  parts.push(
    wrong === 0
      ? `Face + body gave the right answer for all ${total} photos.`
      : `Face + body gave the right answer for ${ofTotal(faceBody.right, total)} photos; the rows marked in red or amber show where it did not.`,
  );
  return parts.join(" ");
}

/** What the face alone would have done at another threshold: counts only, using the face scores the server measured. */
export interface WhatIf {
  knownTotal: number;
  knownAccepted: number;
  strangerTotal: number;
  strangerAccepted: number;
}

/**
 * "If the face threshold were X": a known person is recognised when the face similarity to the right person reaches X,
 * a stranger is wrongly accepted when it reaches X. Photos without a usable face are left out (the face does not decide them).
 */
export function whatIfFace(cases: DemoCase[], results: Record<string, DemoCaseResult | undefined>, threshold: number): WhatIf {
  const out: WhatIf = { knownTotal: 0, knownAccepted: 0, strangerTotal: 0, strangerAccepted: 0 };
  for (const c of cases) {
    const d = results[c.id]?.face_body;
    if (!d || d.face_score === null) continue;
    if (c.expect.kind === "match") {
      out.knownTotal += 1;
      if (d.top1_person === c.expect.person && d.face_score >= threshold) out.knownAccepted += 1;
    } else if (c.expect.kind === "unknown") {
      out.strangerTotal += 1;
      if (d.face_score >= threshold) out.strangerAccepted += 1;
    }
  }
  return out;
}

/** The lowest face score of a correctly named known person and the highest of any stranger (the "gap" the threshold sits in). */
export function faceGap(cases: DemoCase[], results: Record<string, DemoCaseResult | undefined>): { lowestKnown: number | null; highestStranger: number | null } {
  let lowestKnown: number | null = null;
  let highestStranger: number | null = null;
  for (const c of cases) {
    const d = results[c.id]?.face_body;
    if (!d || d.face_score === null) continue;
    if (c.expect.kind === "match" && d.top1_person === c.expect.person) lowestKnown = lowestKnown === null ? d.face_score : Math.min(lowestKnown, d.face_score);
    if (c.expect.kind === "unknown") highestStranger = highestStranger === null ? d.face_score : Math.max(highestStranger, d.face_score);
  }
  return { lowestKnown, highestStranger };
}
