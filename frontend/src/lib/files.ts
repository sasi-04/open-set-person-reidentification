/**
 * Client-side checks for chosen image files.
 *
 * In plain words: these give instant feedback ("that is a PDF", "that is 14 MB") before
 * anything is uploaded. They are a convenience only - the backend repeats and enforces
 * every one of these checks by looking at the real file contents.
 */
import { fileSize } from "./format";

export interface FileLimits {
  maxBytes: number;
  extensions: string[]; // e.g. [".jpg", ".png"]
}

export const DEFAULT_LIMITS: FileLimits = { maxBytes: 10 * 1024 * 1024, extensions: [".jpg", ".jpeg", ".png", ".webp", ".bmp"] };

/** Returns a human-readable problem, or null if the file looks acceptable. */
export function validateImageFile(file: File, limits: FileLimits = DEFAULT_LIMITS): string | null {
  const dot = file.name.lastIndexOf(".");
  const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!limits.extensions.includes(extension)) {
    return `"${file.name}" is not a supported image type. Use ${limits.extensions.join(", ")}.`;
  }
  if (file.size === 0) return `"${file.name}" is empty.`;
  if (file.size > limits.maxBytes) {
    return `"${file.name}" is ${fileSize(file.size)}; the limit is ${fileSize(limits.maxBytes)}.`;
  }
  return null;
}

export function acceptAttribute(limits: FileLimits = DEFAULT_LIMITS): string {
  return limits.extensions.join(",");
}
