/** RunHistory: every past evaluation/calibration with its status, a way to open it, and its reports. */
import { Eye } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/Feedback";
import { dateTime, pct } from "@/lib/format";
import type { RunSummary } from "@/types/api";
import { FlaskConical } from "lucide-react";

const TONE = { succeeded: "ok", failed: "bad", cancelled: "neutral", running: "info", queued: "info" } as const;

export function RunHistory({ runs, selectedId, onSelect }: { runs: RunSummary[]; selectedId: string | null; onSelect: (id: string) => void }) {
  if (runs.length === 0) {
    return <EmptyState icon={<FlaskConical aria-hidden className="size-5" />} title="No runs yet">Experiments you start appear here with their status and reports.</EmptyState>;
  }
  return (
    <ul className="divide-y divide-line rounded-md border border-line">
      {runs.map((run) => {
        const h = run.headline as Record<string, unknown> | null;
        return (
          <li key={run.run_id} className="flex flex-wrap items-center justify-between gap-3 p-3" aria-current={run.run_id === selectedId ? "true" : undefined}>
            <div className="min-w-0 space-y-1">
              <p className="text-sm font-medium capitalize">{run.kind === "lookalike" ? "look-alike experiment" : run.kind} · {run.dataset} {run.dataset_kind !== "benchmark" && <Badge tone="warn">smoke test</Badge>}</p>
              <p className="text-xs text-ink-3">{dateTime(run.created_at)} · <span className="font-mono">{run.run_id.slice(0, 8)}</span></p>
              {h && run.kind === "evaluation" && h.far !== null && h.far !== undefined && <p className="text-xs text-ink-3">selected variant {String(h.selected_variant ?? "none")} · FAR {pct(h.far as number, 2)} · recall {pct(h.recall as number)}</p>}
              {h && run.kind === "calibration" && <p className="text-xs text-ink-3">{h.target_achieved ? "target reached" : "target not reached"} · threshold {h.threshold === null ? "—" : Number(h.threshold).toFixed(3)}</p>}
              {h && run.kind === "lookalike" && <p className="text-xs text-ink-3">searched {String(h.mining_split)} people · challenge FAR {pct(h.challenge_far as number | null, 1)} (all pairs {pct(h.all_pairs_far as number | null, 3)}) · improved model {String(h.improved_status)}</p>}
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={TONE[run.status]}>{run.status === "running" ? `running ${pct(run.progress, 0)}` : run.status}</Badge>
              <Button size="sm" variant={run.run_id === selectedId ? "dark" : "secondary"} icon={<Eye aria-hidden className="size-3.5" />} onClick={() => onSelect(run.run_id)}>
                {run.run_id === selectedId ? "Viewing" : "View"}
              </Button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
