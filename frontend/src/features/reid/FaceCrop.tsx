/**
 * FaceCrop: zoom in on one face inside a picture.
 *
 * In plain words: the matcher reports WHERE it found the face (a box in pixels). This draws just that part of the
 * picture, with a little margin, so a person can look at the two faces side by side - the one in the query and the one
 * in the closest enrolled photo - and judge for themselves. It only draws what the server already measured; it does
 * not detect or compare anything in the browser. Pictures behind the access key are fetched through the app's own client.
 */
import clsx from "clsx";
import { UserRound } from "lucide-react";
import { useEffect, useRef } from "react";
import { useBlobUrl } from "@/hooks/useBlobUrl";

const MARGIN = 0.35; // show this much of the face's size around it, so hair and chin are visible

export function FaceCrop({ src, box, alt, protectedImage = false, className }: {
  src: string | null | undefined;
  /** [x1, y1, x2, y2] of the face in the picture's own pixels. */
  box: number[] | null | undefined;
  alt: string;
  /** True for server pictures that need the access key (reference photos); false for a local blob: preview. */
  protectedImage?: boolean;
  className?: string;
}) {
  const fetched = useBlobUrl(protectedImage ? src : null);
  const url = protectedImage ? fetched.url : src;
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!url || !box) return;
    let cancelled = false;
    const picture = new Image();
    picture.onload = () => {
      const context = canvas.current?.getContext("2d");
      if (cancelled || !context || !canvas.current) return;
      const [x1, y1, x2, y2] = box;
      const w = x2 - x1;
      const h = y2 - y1;
      const sx = Math.max(0, x1 - MARGIN * w);
      const sy = Math.max(0, y1 - MARGIN * h);
      const sw = Math.min(picture.naturalWidth, x2 + MARGIN * w) - sx;
      const sh = Math.min(picture.naturalHeight, y2 + MARGIN * h) - sy;
      if (sw < 2 || sh < 2) return;
      canvas.current.width = 192;
      canvas.current.height = Math.max(32, Math.round((192 * sh) / sw));
      context.drawImage(picture, sx, sy, sw, sh, 0, 0, canvas.current.width, canvas.current.height);
    };
    picture.src = url;
    return () => { cancelled = true; };
  }, [url, box]);

  if (!box) {
    return (
      <div role="img" aria-label={`${alt} (no face to show)`} className={clsx("flex aspect-square items-center justify-center rounded-md border border-dashed border-line bg-surface-2 text-ink-3", className)}>
        <UserRound aria-hidden className="size-1/3 min-h-5 min-w-5" />
      </div>
    );
  }
  return <canvas ref={canvas} role="img" aria-label={alt} className={clsx("block h-auto w-full rounded-md border border-line bg-surface-2", className)} />;
}
