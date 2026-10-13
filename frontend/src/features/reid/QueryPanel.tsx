/**
 * QueryPanel: choose the image and decide how to process it.
 *
 * In plain words: upload area (or the chosen file with Replace/Remove), the two processing
 * options, and the action buttons. The Run button always says what it is going to do, so
 * nothing happens that the person did not expect.
 */
import { ImagePlus, ScanSearch, Trash2, Users } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { FileDrop } from "@/components/ui/FileDrop";
import { Checkbox } from "@/components/ui/Form";
import { acceptAttribute, validateImageFile, type FileLimits } from "@/lib/files";
import { fileSize } from "@/lib/format";
import type { ChosenImage } from "./useReid";

interface Props {
  image: ChosenImage | null;
  limits: FileLimits;
  onChoose: (file: File) => void;
  onReset: () => void;
  asCrop: boolean;
  onAsCrop: (value: boolean) => void;
  matchAll: boolean;
  onMatchAll: (value: boolean) => void;
  mode: "crop" | "box" | "all";
  detecting: boolean;
  matching: boolean;
  onDetect: () => void;
  onRun: () => void;
}

const RUN_LABEL = { crop: "Match this image", box: "Match selected person", all: "Match all people" } as const;

export function QueryPanel(p: Props) {
  const replaceRef = useRef<HTMLInputElement>(null);
  const [replaceProblem, setReplaceProblem] = useState<string | null>(null);
  const busy = p.detecting || p.matching;

  return (
    <Card aria-labelledby="query-title">
      <CardHeader id="query-title" title="Query image" description="An authorised test image of one or more people." />
      <CardBody className="space-y-4">
        {!p.image ? (
          <FileDrop onFiles={([file]) => p.onChoose(file)} limits={p.limits} compact />
        ) : (
          <div className="flex items-center gap-3 rounded-md border border-line p-2.5">
            <img src={p.image.url} alt="Selected query" className="h-14 w-14 shrink-0 rounded object-cover" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium" title={p.image.file.name}>{p.image.file.name}</p>
              <p className="text-xs text-ink-3">{fileSize(p.image.file.size)}</p>
            </div>
            <div className="flex shrink-0 flex-col gap-1.5">
              <Button size="sm" variant="secondary" disabled={busy} icon={<ImagePlus aria-hidden className="size-3.5" />} onClick={() => replaceRef.current?.click()}>
                Replace
              </Button>
              <Button size="sm" variant="ghost" disabled={busy} icon={<Trash2 aria-hidden className="size-3.5" />} onClick={p.onReset}>
                Remove
              </Button>
            </div>
            <input
              ref={replaceRef}
              type="file"
              className="sr-only"
              tabIndex={-1}
              aria-label="Choose a replacement image"
              accept={acceptAttribute(p.limits)}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                const problem = validateImageFile(file, p.limits);
                setReplaceProblem(problem);
                if (!problem) p.onChoose(file);
              }}
            />
          </div>
        )}
        {replaceProblem && <p role="alert" className="text-xs font-medium text-bad">{replaceProblem}</p>}

        <div className="space-y-3">
          <Checkbox
            label="Image is already a person crop"
            hint="Skips the detector. Use for tight crops of a single person."
            checked={p.asCrop}
            disabled={busy}
            onChange={(e) => p.onAsCrop(e.target.checked)}
          />
          <Checkbox
            label="Match everyone found in the image"
            hint="Otherwise only the person you select after “Detect people” is matched."
            checked={p.matchAll}
            disabled={busy || p.asCrop}
            onChange={(e) => p.onMatchAll(e.target.checked)}
          />
        </div>

        <div className="space-y-2">
          <Button variant="secondary" className="w-full" disabled={!p.image || p.asCrop || p.matching} loading={p.detecting} icon={<Users aria-hidden className="size-4" />} onClick={p.onDetect}>
            Detect people
          </Button>
          <Button variant="primary" className="w-full" disabled={!p.image || p.detecting} loading={p.matching} icon={<ScanSearch aria-hidden className="size-4" />} onClick={p.onRun}>
            Run re-identification
          </Button>
          <p className="text-xs text-ink-3" aria-live="polite">
            {p.matching
              ? "Matching… on a CPU this usually takes a few seconds."
              : p.image
                ? `Will run: ${RUN_LABEL[p.mode].toLowerCase()}.`
                : "Choose an image to begin."}
          </p>
          <Button variant="ghost" className="w-full" disabled={busy || (!p.image && !p.asCrop && !p.matchAll)} onClick={p.onReset}>
            Reset
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}
