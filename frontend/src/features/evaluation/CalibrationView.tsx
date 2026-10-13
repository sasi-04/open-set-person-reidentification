/**
 * CalibrationView: the result of a threshold-calibration run.
 *
 * In plain words: tells you plainly whether the requested operating point was reached on the
 * calibration split, what threshold and margin were found, how many people that is based on
 * (and how sure we can be - the 95% upper bound on FAR), and where the score distributions
 * overlap. If the target was NOT reached, that is the headline - no result is dressed up.
 */
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, DefinitionList } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Feedback";
import { num, pct } from "@/lib/format";
import type { CalibrationResult, RunDetail } from "@/types/api";
import { ScoreDistributionChart } from "./charts";

export function CalibrationView({ run, result }: { run: RunDetail; result: CalibrationResult }) {
  const s = result.selected;
  const achieved = s.target_achieved;
  return (
    <Card aria-labelledby="cal-result-title">
      <CardHeader
        id="cal-result-title"
        title="Threshold calibration"
        description={`${result.metadata.dataset.name} · ${result.metadata.operating_target}`}
        action={achieved ? <Badge tone="ok">Target reached</Badge> : <Badge tone="warn">Target NOT reached</Badge>}
      />
      <CardBody className="space-y-4">
        {result.warnings.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}
        <Notice tone={achieved ? "info" : "warn"} title={achieved ? "A threshold meeting the target was found" : "No threshold meets the requested target"}>
          {result.metadata.split_used}. {achieved
            ? "This is a measurement on one calibration sample - not a guarantee for new people."
            : "The numbers below describe a best-effort fallback only; it cannot be applied as 'calibrated'."}
        </Notice>
        <DefinitionList items={[
          { term: "Accept threshold", value: <b className="tabular">{num(s.threshold)}</b> },
          { term: "Minimum margin", value: s.min_margin === null ? "Not needed" : <b className="tabular">{num(s.min_margin)}</b> },
          { term: "FAR on calibration data", value: `${pct(s.calibration.far, 2)} (${s.calibration.counts.unknown_accepted} of ${s.n_unknown} strangers)` },
          { term: "FAR 95% upper bound", value: pct(s.far_upper_bound_95, 2) },
          { term: "Recall on calibration data", value: `${pct(s.calibration.dir_at_rank["1"])} accepted and correct · ${pct(s.calibration.tar)} accepted` },
          { term: "Sample size", value: `${s.n_known} enrolled-person queries, ${s.n_unknown} stranger queries${s.sample_size_adequate ? "" : " (small for this target)"}` },
        ]} />
        {s.notes.map((n) => <p key={n} className="text-xs text-ink-3">{n}</p>)}
        <ScoreDistributionChart histogram={result.score_histogram} threshold={s.threshold} />
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/settings?tab=model"><Button variant="primary" disabled={!achieved}>{achieved ? "Go to Model & System Settings to apply it" : "Cannot be applied"}</Button></Link>
          <span className="font-mono text-xs text-ink-3">run {run.run_id.slice(0, 12)}…</span>
        </div>
      </CardBody>
    </Card>
  );
}
