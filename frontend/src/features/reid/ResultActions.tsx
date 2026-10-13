/**
 * ResultActions: what you can do after a result.
 *
 * "Decision record" downloads what the BACKEND saved for this request - the decision, every score, the
 * threshold and policy version it was made under, the candidates and the timings, plus a plain-language
 * notice that a score is not a probability. It contains no image, crop or embedding, so it is safe to
 * share. "Export result summary" is the same idea built in the browser from the screen's own data.
 */
import { Download, History, RotateCcw, Settings2, Upload } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { api } from "@/services/api";
import { describeError, saveBlob } from "@/services/http";
import type { PredictResponse } from "@/types/api";

export function buildSummary(response: PredictResponse) {
  return {
    note: "Non-sensitive summary: scores and decisions only. No images, crops or embeddings are included.",
    request_id: response.request_id,
    created_at: response.created_at,
    mode: response.mode,
    model: { name: response.model.name, fingerprint: response.model.fingerprint, device: response.model.device },
    policy: { version: response.policy_version, status: response.policy_status },
    timings_ms: response.timings_ms,
    people: response.people.map((p) => ({
      index: p.index,
      detector_confidence: p.detector_score,
      outcome: p.decision.outcome,
      reason: p.decision.reason,
      accepted_reference_id: p.decision.accepted_reference_id,
      similarity_top1: p.decision.top1_score,
      margin: p.decision.margin,
      accept_threshold: p.decision.accept_threshold,
      min_margin: p.decision.min_margin,
      calibrated_confidence: p.decision.calibrated_confidence,
      candidates: p.candidates.map((c) => ({ rank: c.rank, reference_id: c.reference_id, similarity: c.score })),
    })),
  };
}

export function ResultActions({ response, onNewQuery, onClear }: { response: PredictResponse; onNewQuery: () => void; onClear: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<"json" | "csv" | null>(null);

  function exportSummary() {
    const blob = new Blob([JSON.stringify(buildSummary(response), null, 2)], { type: "application/json" });
    saveBlob(blob, `reid-result-${response.request_id}.json`);
    toast.success("Result summary exported (scores and decisions only).");
  }

  async function exportRecord(format: "json" | "csv") {
    setBusy(format);
    try {
      saveBlob(await api.decisionRecord(response.request_id, format), `decision-${response.request_id.slice(0, 8)}.${format}`);
      toast.success(`Decision record downloaded (${format.toUpperCase()}).`);
    } catch (failure) {
      toast.error(describeError(failure));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Export the decision record">
        <Button variant="secondary" size="sm" loading={busy === "json"} icon={<Download aria-hidden className="size-4" />} onClick={() => void exportRecord("json")}>
          Decision record (JSON)
        </Button>
        <Button variant="secondary" size="sm" loading={busy === "csv"} icon={<Download aria-hidden className="size-4" />} onClick={() => void exportRecord("csv")}>
          Decision record (CSV)
        </Button>
        <Button variant="ghost" size="sm" icon={<Download aria-hidden className="size-4" />} onClick={exportSummary}>
          Export result summary
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" icon={<Upload aria-hidden className="size-4" />} onClick={onNewQuery}>
          Upload another query
        </Button>
        <Link to="/history">
          <Button variant="secondary" size="sm" icon={<History aria-hidden className="size-4" />}>
            Decision history
          </Button>
        </Link>
        <Link to="/settings?tab=model">
          <Button variant="secondary" size="sm" icon={<Settings2 aria-hidden className="size-4" />}>
            Policy and thresholds
          </Button>
        </Link>
        <Button variant="ghost" size="sm" icon={<RotateCcw aria-hidden className="size-4" />} onClick={onClear}>
          Clear session
        </Button>
      </div>
    </div>
  );
}
