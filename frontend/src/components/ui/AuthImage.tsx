/**
 * AuthImage: shows an image that needs the access key.
 *
 * In plain words: a normal <img src="/api/..."> cannot send the X-API-Key header, so
 * reference images and stored crops would be blocked. This component downloads the
 * image through our authenticated client, shows it from an in-memory URL, and frees
 * that URL again when it disappears. Images are cached for a few minutes.
 */
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ImageOff, User } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/services/api";

export function AuthImage({ src, alt, className, fit = "cover" }: { src: string | null | undefined; alt: string; className?: string; fit?: "cover" | "contain" }) {
  const { data: blob, isError, isLoading } = useQuery({
    queryKey: ["image", src],
    queryFn: () => api.imageBlob(src as string),
    enabled: !!src,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!blob) return setObjectUrl(null);
    const url = URL.createObjectURL(blob);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [blob]);

  if (!src) {
    return (
      <div role="img" aria-label={alt} className={clsx("flex items-center justify-center bg-surface-2 text-ink-3", className)}>
        <User aria-hidden className="size-1/3 min-h-5 min-w-5" />
      </div>
    );
  }
  if (isError) {
    return (
      <div role="img" aria-label={`${alt} (not available)`} title="Image not available" className={clsx("flex items-center justify-center bg-surface-2 text-ink-3", className)}>
        <ImageOff aria-hidden className="size-1/3 min-h-5 min-w-5" />
      </div>
    );
  }
  if (isLoading || !objectUrl) return <div aria-hidden className={clsx("skeleton", className)} />;
  return <img src={objectUrl} alt={alt} className={clsx(fit === "cover" ? "object-cover" : "object-contain", className)} />;
}
