/**
 * FileDrop: drag-and-drop or browse for image files.
 *
 * In plain words: a drop area plus a real "Browse files" button (so keyboard users and
 * touch devices are not excluded). Each chosen file is checked for type and size; valid
 * files are passed on, and problems are listed in plain words.
 */
import clsx from "clsx";
import { ImagePlus, UploadCloud } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";
import { acceptAttribute, DEFAULT_LIMITS, validateImageFile, type FileLimits } from "@/lib/files";
import { Button } from "./Button";

export function FileDrop({
  onFiles,
  multiple = false,
  limits = DEFAULT_LIMITS,
  disabled = false,
  title,
  helper,
  compact = false,
}: {
  onFiles: (files: File[]) => void;
  multiple?: boolean;
  limits?: FileLimits;
  disabled?: boolean;
  title?: string;
  helper?: string;
  compact?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);
  const helpId = useId();

  function accept(list: FileList | File[] | null) {
    if (!list) return;
    const chosen = Array.from(list);
    const good: File[] = [];
    const bad: string[] = [];
    for (const file of chosen) {
      const problem = validateImageFile(file, limits);
      if (problem) bad.push(problem);
      else good.push(file);
    }
    setProblems(bad);
    if (good.length) onFiles(multiple ? good : good.slice(0, 1));
    if (!multiple && chosen.length > 1) setProblems([...bad, "Only one image can be used here; the first valid one was kept."]);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (!disabled) accept(event.dataTransfer.files);
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={clsx(
          "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed text-center transition-colors",
          compact ? "px-4 py-5" : "px-4 py-8",
          dragging ? "border-brand bg-brand-tint" : "border-line-strong bg-surface-2/50",
          disabled && "opacity-60",
        )}
      >
        <div className="flex size-10 items-center justify-center rounded-full bg-surface text-ink-3 shadow-card">
          <UploadCloud aria-hidden className="size-5" />
        </div>
        <p className="text-sm font-medium">{title ?? (multiple ? "Drag images here" : "Drag an image here")}</p>
        <p id={helpId} className="max-w-xs text-xs text-ink-3">
          {helper ?? `or browse. ${limits.extensions.join(", ")} · up to ${Math.round(limits.maxBytes / 1024 / 1024)} MB each.`}
        </p>
        <Button variant="secondary" size="sm" disabled={disabled} icon={<ImagePlus aria-hidden className="size-4" />} onClick={() => inputRef.current?.click()} aria-describedby={helpId}>
          Browse files
        </Button>
        <input
          ref={inputRef}
          type="file"
          className="sr-only"
          tabIndex={-1}
          aria-label={multiple ? "Choose image files" : "Choose an image file"}
          accept={acceptAttribute(limits)}
          multiple={multiple}
          disabled={disabled}
          onChange={(e) => {
            accept(e.target.files);
            e.target.value = ""; // lets the same file be chosen again after removing it
          }}
        />
      </div>
      {problems.length > 0 && (
        <ul role="alert" className="mt-2 space-y-1 text-xs font-medium text-bad">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
