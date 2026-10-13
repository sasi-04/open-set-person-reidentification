/**
 * EvidencePanel: what each kind of evidence says about the closest enrolled person.
 *
 * In plain words: a decision rests on two fingerprints and a few simple colour observations, and this panel lays them
 * side by side so anyone can follow the reasoning.
 *
 *   FACE   - how alike the two faces are. When a usable face is visible, THIS decides.
 *   BODY   - how alike the whole person is (mostly clothing colour and build). Supporting evidence when a face decides;
 *            the deciding evidence only when there is no usable face.
 *   CUES   - hair colour, skin tone, clothing colours of the query next to the closest enrolled photo. Plain image
 *            measurements, shown for a human reader; they never change MATCH / UNKNOWN / REVIEW.
 *
 * Every number comes from the server. The face crops are drawn from the server's reported face boxes.
 */
import { Badge } from "@/components/ui/Badge";
import { InfoTip } from "@/components/ui/InfoTip";
import { num } from "@/lib/format";
import { FACE_FLAGS, FACE_STATUS } from "@/lib/present";
import type { CueRow, PersonResult } from "@/types/api";
import { FaceCrop } from "./FaceCrop";
import { ScoreBar } from "./ScoreBar";

const swatch = (rgb: number[]) => `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;

function EvidenceRow({ title, tip, score, threshold, role, children }: {
  title: string; tip: string; score: number | null; threshold: number | null; role: string; children?: React.ReactNode;
}) {
  const passes = score !== null && threshold !== null && score >= threshold;
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          {title}
          <InfoTip label={`About ${title}`}>{tip}</InfoTip>
        </span>
        <span className="text-xs text-ink-3">{role}</span>
      </div>
      {score !== null ? (
        <>
          <div className="flex items-center gap-3">
            <div className="flex-1"><ScoreBar score={score} threshold={threshold} /></div>
            <span className="w-14 text-right text-sm font-semibold tabular">{num(score)}</span>
          </div>
          {threshold !== null && (
            <p className="text-xs text-ink-3">
              {passes ? "Reaches" : "Below"} its threshold of <span className="tabular">{num(threshold)}</span>.
            </p>
          )}
        </>
      ) : (
        <p className="text-sm text-ink-3">{children}</p>
      )}
    </div>
  );
}

function CueTable({ rows }: { rows: CueRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[22rem] text-left text-sm">
        <caption className="sr-only">Hair, skin and clothing colours of the query and of the closest enrolled photo</caption>
        <thead className="text-xs text-ink-3">
          <tr>
            <th scope="col" className="py-1.5 pr-3 font-medium">Cue</th>
            <th scope="col" className="py-1.5 pr-3 font-medium">Query</th>
            <th scope="col" className="py-1.5 pr-3 font-medium">Enrolled photo</th>
            <th scope="col" className="py-1.5 font-medium">Looks</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((row) => (
            <tr key={row.cue}>
              <th scope="row" className="py-2 pr-3 font-medium">{row.title}</th>
              {[{ rgb: row.query_rgb, label: row.query_label, who: "query" }, { rgb: row.reference_rgb, label: row.reference_label, who: "enrolled photo" }].map((side) => (
                <td key={side.who} className="py-2 pr-3">
                  <span className="flex items-center gap-2">
                    <span aria-hidden className="size-5 shrink-0 rounded border border-line-strong" style={{ background: swatch(side.rgb) }} />
                    <span className="capitalize">{side.label}<span className="sr-only"> ({side.who})</span></span>
                  </span>
                </td>
              ))}
              <td className="py-2">
                <Badge tone={row.verdict === "similar" ? "ok" : "neutral"}>{row.verdict === "similar" ? "Similar" : "Different"}</Badge>
                <span className="ml-1.5 text-xs text-ink-3 tabular">ΔE {row.delta_e.toFixed(0)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EvidencePanel({ person, imageUrl }: { person: PersonResult; imageUrl: string }) {
  const { decision, face } = person;
  const top = person.candidates.find((c) => c.reference_id === decision.top1_reference_id) ?? person.candidates[0];
  const decidedByFace = decision.basis === "face";
  const faceState = face ? FACE_STATUS[face.status] : null;
  const showFaces = !!face?.box && !!top?.face_box && top.face_score !== null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={decidedByFace ? "brand" : "neutral"}>{decidedByFace ? "Decided by the face" : "Decided by the body"}</Badge>
        {faceState && <Badge tone={faceState.tone}>{faceState.label}</Badge>}
      </div>
      <p className="text-sm text-ink-2">
        {decidedByFace
          ? "A usable face was visible, so the face decides. Clothing and build are shown as supporting evidence and cannot turn a face that does not match into a MATCH."
          : face?.status === "usable"
            ? "A usable face was visible, but nobody enrolled has a face on file to compare it with, so the body was used."
            : "No usable face was visible, so only the body (mostly clothing colour and build) could be compared. That is weaker evidence."}
      </p>

      <EvidenceRow
        title="Face" role={decidedByFace ? "decides" : "not used"} score={decision.top1_face_score} threshold={decision.face_threshold}
        tip="Cosine similarity between the face in the query and the closest enrolled face (−1 to 1). Same-person pairs usually score 0.5–0.8; different people usually score below 0.3."
      >
        {face ? (face.message ?? "No face to compare.") : "Face matching was not used for this result."}
        {face && face.flags.length > 0 && <span className="ml-1">({face.flags.map((f) => FACE_FLAGS[f] ?? f).join(", ")})</span>}
      </EvidenceRow>

      <EvidenceRow
        title="Body and clothing" role={decidedByFace ? "supports" : "decides"} score={decision.top1_body_score} threshold={decision.body_threshold}
        tip="Cosine similarity of the whole-person fingerprint. It mostly reflects clothing colour and build, so it can be high for two different people in similar clothes and low for one person who changed clothes."
      >
        Not compared.
      </EvidenceRow>

      {showFaces && top && (
        <figure className="grid grid-cols-2 gap-3">
          <div className="min-w-0 space-y-1.5">
            <p className="text-xs font-semibold text-ink-3 uppercase">Face in the query</p>
            <FaceCrop src={imageUrl} box={face?.box} alt="Face found in the query picture" />
          </div>
          <div className="min-w-0 space-y-1.5">
            <p className="text-xs font-semibold text-ink-3 uppercase">Closest enrolled face</p>
            <FaceCrop src={top.image_url} box={top.face_box} protectedImage alt={`Face of ${top.reference_id} in the closest enrolled photo`} />
          </div>
          <figcaption className="col-span-2 text-xs text-ink-3">The two crops are exactly the regions the face score was computed from.</figcaption>
        </figure>
      )}

      {person.cues.length > 0 && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-sm font-medium">
            Supporting cues
            <InfoTip label="About supporting cues">
              Hair colour, skin tone and clothing colours measured from the pictures with plain image statistics (no neural network). Lighting and camera settings move colours, and people change clothes, so these never change the decision. ΔE is the colour distance: about 2 is barely visible, 10–20 a clearly different shade, 40+ a different colour.
            </InfoTip>
          </div>
          <CueTable rows={person.cues} />
          <p className="text-xs text-ink-3">For a human reader only. They are not part of the decision rule.</p>
        </div>
      )}
    </div>
  );
}
