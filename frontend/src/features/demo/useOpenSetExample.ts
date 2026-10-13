/** The example's data and its runner together, so the page can hand the same object to every part that needs it. */
import { useQuery } from "@tanstack/react-query";
import { api, keys } from "@/services/api";
import { useDemoRun } from "./useDemoRun";

/** The id of the example's card: the "Run the example" buttons elsewhere on the page scroll to it. */
export const EXAMPLE_ID = "open-set-example";

export function useOpenSetExample() {
  const query = useQuery({ queryKey: keys.demo, queryFn: api.demo, retry: false, staleTime: 60_000 });
  const runner = useDemoRun(query.data);
  return { query, runner };
}

export type OpenSetExampleState = ReturnType<typeof useOpenSetExample>;
