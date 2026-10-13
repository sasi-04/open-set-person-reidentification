/**
 * The session: who is using the app, and does this server ask for an access key at all?
 *
 * In plain words: when the page opens we ask the backend "who am I?". By default access keys
 * are switched off, so the answer is simply "admin" and the app opens straight away - no key
 * screen. If the server was started with keys switched on (REID_AUTH_REQUIRED=true) it answers
 * "401, I need a key" and we show the key screen instead; once a key works we ask again and
 * learn the role (viewer / operator / admin), which decides which buttons are enabled. The
 * backend still enforces every permission itself - the UI only avoids offering actions that
 * would be refused.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Spinner } from "@/components/ui/Feedback";
import { api, keys } from "@/services/api";
import { accessKey, ApiError, useAccessKey } from "@/services/http";
import type { Role } from "@/types/api";

interface Session {
  role: Role;
  /** False when the server runs with access keys switched off (the default). */
  authRequired: boolean;
  signOut: () => void;
}
const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside <SessionProvider>");
  return session;
}

/** What the "cannot enter yet" screen is told: why, and how to try again. */
export interface SessionProblem {
  /** Null on a first visit to a server that wants a key; a 401 means the key was refused; anything else means the server is unreachable or broken. */
  error: Error | null;
  retry: () => void;
}

/** Asks who we are; the children are only shown once the answer is known. */
export function SessionProvider({ children, fallback }: { children: ReactNode; fallback: (problem: SessionProblem) => ReactNode }) {
  const key = useAccessKey();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: [...keys.me, key], queryFn: api.me, retry: false, staleTime: 5 * 60_000 });

  // Once the server has said "I need a key", the key screen stays up (with its own state) until a key works.
  const [needsKey, setNeedsKey] = useState(false);
  const [refusedKey, setRefusedKey] = useState<Error | null>(null);
  useEffect(() => {
    if (!(query.error instanceof ApiError) || query.error.status !== 401) return;
    setNeedsKey(true);
    if (key) {
      setRefusedKey(query.error); // a stored key the server no longer accepts
      accessKey.clear();
    }
  }, [query.error, key]);

  const value = useMemo<Session | null>(
    () =>
      query.data
        ? {
            role: query.data.role,
            authRequired: query.data.auth_required,
            signOut: () => {
              accessKey.clear();
              queryClient.clear();
            },
          }
        : null,
    [query.data, queryClient],
  );

  if (value) return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;

  const unreachable = query.error && !(query.error instanceof ApiError && query.error.status === 401);
  if (unreachable) return <>{fallback({ error: query.error, retry: () => void query.refetch() })}</>;
  if (needsKey) return <>{fallback({ error: refusedKey, retry: () => void query.refetch() })}</>;

  return (
    <div className="flex min-h-dvh items-center justify-center">
      <Spinner label="Connecting to the backend" />
    </div>
  );
}
