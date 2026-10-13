/**
 * Access, appearance, privacy/retention, audit trail, and the honest limits (one tab of the
 * Model & System Settings screen).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, LogOut, Moon, ShieldCheck, Sun, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, DefinitionList } from "@/components/ui/Card";
import { ErrorState, Notice, Skeleton } from "@/components/ui/Feedback";
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/hooks/useSession";
import { useTheme } from "@/hooks/useTheme";
import { dateTime, humanize } from "@/lib/format";
import { can } from "@/lib/present";
import { api, keys } from "@/services/api";
import { describeError } from "@/services/http";

const LIMITATIONS = [
  "Research prototype. It is not a production surveillance or identity-verification service and makes no claim of demographic fairness, privacy compliance or production readiness.",
  "A threshold chosen on one calibration sample does not guarantee the same false-accept rate for new people; the evaluation reports show sample sizes and confidence intervals.",
  "Same-clothing difficulty is measured with a colour-histogram proxy, because standard benchmarks have no clothing labels.",
  "Speed was measured on a 4-thread CPU; the pipeline is interactive (about a second per query), not real-time. Video Explorer re-identifies sampled frames of prerecorded clips one frame at a time; it is not a multi-object tracker, and no live-camera or cross-camera tracking is implemented.",
  "The pretrained weights were trained on public research datasets whose terms are research-oriented (DukeMTMC-reID was withdrawn in 2019 for privacy reasons).",
];

function AuditTrail() {
  const query = useQuery({ queryKey: keys.audit, queryFn: api.audit });
  if (query.isLoading) return <Skeleton className="h-32 w-full" />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (!query.data?.length) return <p className="text-sm text-ink-3">No audited actions yet.</p>;
  return (
    <div className="max-h-80 overflow-auto rounded-md border border-line">
      <table className="w-full text-left text-xs">
        <caption className="sr-only">Audit trail, newest first</caption>
        <thead className="sticky top-0 bg-surface-2 text-ink-3"><tr>{["When", "Role", "Action", "Subject"].map((h) => <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-line">
          {query.data.map((e, i) => (
            <tr key={`${e.at}-${i}`}><td className="px-3 py-1.5 whitespace-nowrap">{dateTime(e.at)}</td><td className="px-3 py-1.5 capitalize">{e.role}</td><td className="px-3 py-1.5">{humanize(e.action.replace(".", " "))}</td><td className="px-3 py-1.5 font-mono break-all">{e.subject ?? "—"}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PreferencesPanel() {
  const { role, authRequired, signOut } = useSession();
  const { theme, setTheme } = useTheme();
  const toast = useToast();
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: keys.config, queryFn: api.config });
  const cleanup = useMutation({
    mutationFn: api.cleanup,
    onSuccess: (r) => {
      toast.success(`Cleanup done: ${r.expired_crops_removed} expired crops, ${r.history_rows_removed} old history rows and ${r.orphan_files_removed} stray files removed.`);
      void queryClient.invalidateQueries({ queryKey: keys.history });
    },
    onError: (e) => toast.error(describeError(e)),
  });

  return (
    <>
      <p className="mb-4 max-w-3xl text-sm text-ink-3">Your access, the look of the app, and how data is kept.</p>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card aria-labelledby="access-title">
          <CardHeader id="access-title" title="Access" description={authRequired ? "The key you connected with decides what you may do." : "No access key is needed on this server."} />
          <CardBody className="space-y-4">
            {authRequired ? (
              <>
                <DefinitionList items={[{ term: "Your role", value: <span className="font-semibold capitalize">{role}</span> }, { term: "Can run queries", value: "Yes" }, { term: "Can manage the gallery", value: can(role, "operator") ? "Yes" : "No (operator role)" }, { term: "Can change thresholds and run evaluations", value: can(role, "admin") ? "Yes" : "No (admin role)" }]} />
                <Button icon={<LogOut aria-hidden className="size-4" />} onClick={signOut}>Sign out and forget the key</Button>
              </>
            ) : (
              <p className="text-sm text-ink-2">
                Access keys are switched off, so everyone who can open this page has full control. That is fine on your own computer
                (the server only listens on 127.0.0.1). Before sharing it, set <code className="font-mono text-[13px]">REID_AUTH_REQUIRED=true</code> in <code className="font-mono text-[13px]">.env</code> and restart.
              </p>
            )}
          </CardBody>
        </Card>

        <Card aria-labelledby="appearance-title">
          <CardHeader id="appearance-title" title="Appearance" />
          <CardBody>
            <div role="radiogroup" aria-label="Theme" className="grid grid-cols-2 gap-2">
              {([["light", "Light", <Sun key="s" aria-hidden className="size-4" />], ["dark", "Dark", <Moon key="m" aria-hidden className="size-4" />]] as const).map(([value, label, icon]) => (
                <button key={value} type="button" role="radio" aria-checked={theme === value} onClick={() => setTheme(value)}
                  className={`flex min-h-10 items-center justify-center gap-2 rounded-md border text-sm font-medium ${theme === value ? "border-ink bg-surface-2" : "border-line-strong hover:bg-surface-2"}`}>
                  {icon}{label}
                </button>
              ))}
            </div>
          </CardBody>
        </Card>

        <Card aria-labelledby="privacy-title">
          <CardHeader id="privacy-title" title="Privacy and retention" description="What is stored, and for how long." />
          <CardBody className="space-y-4">
            {config.isLoading && <Skeleton className="h-24 w-full" />}
            {config.isError && <ErrorState error={config.error} onRetry={() => void config.refetch()} />}
            {config.data && (
              <>
                <DefinitionList items={[
                  { term: "Reference images", value: config.data.retention.reference_images },
                  { term: "Query crops", value: config.data.retention.query_retention_hours === 0 ? "Never stored" : `Deleted after ${config.data.retention.query_retention_hours} h` },
                  { term: "History rows", value: `Deleted after ${config.data.retention.history_retention_days} days` },
                  { term: "Raw uploads", value: "Never stored (only our own re-encoded person crop)" },
                  { term: "Embeddings in logs", value: "Never logged" },
                ]} />
                <Button disabled={!can(role, "admin")} title={can(role, "admin") ? undefined : "Requires the admin role"} loading={cleanup.isPending} icon={<Trash2 aria-hidden className="size-4" />} onClick={() => cleanup.mutate()}>
                  Run cleanup now
                </Button>
              </>
            )}
          </CardBody>
        </Card>

        <Card aria-labelledby="about-title">
          <CardHeader id="about-title" title="About this system" />
          <CardBody className="space-y-3">
            <Notice tone="warn" title="Research and demonstration use only">Use only authorised, controlled test images. This tool must not be pointed at public cameras or used to identify real-world individuals.</Notice>
            <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">{LIMITATIONS.map((l) => <li key={l}>{l}</li>)}</ul>
            <a className="inline-flex items-center gap-2 text-sm font-medium underline" href="/api/docs" target="_blank" rel="noreferrer"><BookOpen aria-hidden className="size-4" />Open the API documentation</a>
          </CardBody>
        </Card>

        {can(role, "admin") && (
          <Card className="lg:col-span-2" aria-labelledby="audit-title">
            <CardHeader id="audit-title" title="Audit trail" description="Sensitive actions: who did what, and when. Never includes images or embeddings." action={<ShieldCheck aria-hidden className="size-5 text-ink-3" />} />
            <CardBody><AuditTrail /></CardBody>
          </Card>
        )}
      </div>
    </>
  );
}
