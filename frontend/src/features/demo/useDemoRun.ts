/**
 * Running the example, one photo at a time.
 *
 * In plain words: "Run the example" asks the server to build its private example gallery (about 3 seconds), then to analyse
 * the 13 example photos one by one. Going one by one lets the page show progress and fill in rows as the answers arrive.
 * A finished run is kept for the rest of the visit, so going to another screen and coming back does not lose it.
 * Nothing is saved on the server: the example gallery lives only in memory and never touches the real gallery.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, keys } from "@/services/api";
import type { DemoCaseResult, DemoInfo, DemoPerson, DemoRules } from "@/types/api";

export type DemoPhase = "idle" | "preparing" | "running" | "done" | "error";

export interface DemoRun {
  phase: DemoPhase;
  /** Answers received so far, by case id. */
  results: Record<string, DemoCaseResult>;
  /** The example people with what the face analysis found in their photos (known after the gallery is built). */
  people: DemoPerson[] | null;
  rules: DemoRules | null;
  error: unknown;
  /** How long the whole run took, in milliseconds (known when done). */
  totalMs: number | null;
}

const IDLE: DemoRun = { phase: "idle", results: {}, people: null, rules: null, error: null, totalMs: null };

export function useDemoRun(info: DemoInfo | undefined) {
  const client = useQueryClient();
  const [run, setRun] = useState<DemoRun>(() => {
    const kept = client.getQueryData<DemoRun>(keys.demoRun);
    return kept?.phase === "done" ? kept : IDLE;
  });
  const ticket = useRef(0); // a newer run (or leaving the page) cancels the one in flight
  useEffect(() => () => { ticket.current += 1; }, []);

  const start = useCallback(async () => {
    if (!info?.available) return;
    const mine = ++ticket.current;
    const alive = () => ticket.current === mine;
    const began = performance.now();
    setRun({ ...IDLE, phase: "preparing" });
    try {
      const prepared = await api.demoPrepare();
      if (!alive()) return;
      let next: DemoRun = { ...IDLE, phase: "running", people: prepared.people, rules: prepared.rules };
      setRun(next);
      for (const c of info.cases) {
        const result = await api.demoCase(c.id);
        if (!alive()) return;
        next = { ...next, results: { ...next.results, [c.id]: result } };
        setRun(next);
      }
      next = { ...next, phase: "done", totalMs: Math.round(performance.now() - began) };
      setRun(next);
      client.setQueryDefaults(keys.demoRun, { gcTime: Infinity, staleTime: Infinity }); // nothing "observes" it: keep it for the visit
      client.setQueryData(keys.demoRun, next);
    } catch (error) {
      if (alive()) setRun((previous) => ({ ...previous, phase: "error", error }));
    }
  }, [client, info]);

  const reset = useCallback(() => {
    ticket.current += 1;
    client.removeQueries({ queryKey: keys.demoRun });
    setRun(IDLE);
  }, [client]);

  return { run, start, reset, busy: run.phase === "preparing" || run.phase === "running" };
}

export type DemoRunner = ReturnType<typeof useDemoRun>;
