/**
 * ConnectScreen: shown ONLY when the app cannot get in on its own.
 *
 * In plain words: by default the backend needs no access key, and this screen never appears.
 * It appears in two situations:
 *   1. the server was started with access keys switched on (REID_AUTH_REQUIRED=true) - then
 *      it takes a key, asks the backend what role it grants, and lets the person in;
 *   2. the backend cannot be reached at all - then it says so and offers "Try again".
 * Keys live in this browser tab (or on this device if "remember" is ticked) and are never
 * put in a URL.
 */
import { ShieldCheck } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Brand } from "@/components/layout/Brand";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Feedback";
import { Checkbox, Field, TextInput } from "@/components/ui/Form";
import type { SessionProblem } from "@/hooks/useSession";
import { api } from "@/services/api";
import { accessKey, ApiError, describeError } from "@/services/http";

function Frame({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-nav px-4 py-10">
      <div className="w-full max-w-md space-y-5">
        <div className="flex justify-center">
          <Brand />
        </div>
        {children}
        <p className="text-center text-xs text-nav-ink-2">
          Research prototype · authorised, controlled test images only · not a surveillance or identity-verification service.
        </p>
      </div>
    </div>
  );
}

export function ConnectScreen({ error, retry }: SessionProblem) {
  const [value, setValue] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(error ? describeError(error) : null);

  // A refused key is a 401; anything else (no network, server error) is not about keys at all.
  const unreachable = error !== null && !(error instanceof ApiError && error.status === 401);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setProblem(null);
    accessKey.set(value, remember);
    try {
      await api.me(); // validates the key before entering the app
    } catch (failure) {
      accessKey.clear();
      setProblem(describeError(failure));
    } finally {
      setBusy(false);
    }
  }

  if (unreachable) {
    return (
      <Frame>
        <div className="space-y-4 rounded-lg border border-line bg-surface p-6 shadow-pop">
          <h1 className="text-lg">Cannot reach the backend</h1>
          <Notice tone="bad" title="Could not connect">{describeError(error)}</Notice>
          <Button variant="primary" onClick={retry} className="w-full">Try again</Button>
        </div>
      </Frame>
    );
  }

  return (
    <Frame>
      <form onSubmit={submit} className="space-y-4 rounded-lg border border-line bg-surface p-6 shadow-pop">
        <div>
          <h1 className="text-lg">Connect to the backend</h1>
          <p className="mt-1 text-sm text-ink-3">This server asks for an access key. The key decides what you are allowed to do.</p>
        </div>
        {problem && <Notice tone="bad" title="Could not connect">{problem}</Notice>}
        <Field label="Access key" hint="Set in the server's .env file (REID_VIEWER_KEY, REID_OPERATOR_KEY or REID_ADMIN_KEY).">
          <TextInput type="password" autoComplete="off" spellCheck={false} value={value} onChange={(e) => setValue(e.target.value)} required />
        </Field>
        <Checkbox label="Remember on this device" hint="Otherwise the key is forgotten when you close the tab." checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        <Button type="submit" variant="primary" loading={busy} disabled={!value.trim()} className="w-full" icon={<ShieldCheck aria-hidden className="size-4" />}>
          Connect
        </Button>
      </form>
    </Frame>
  );
}
