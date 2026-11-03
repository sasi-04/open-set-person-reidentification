/** UseBlobUrl: turn a protected backend image into a URL an <img> can show. When the server asks for an access key, a plain <img src="/api/..."> cannot send it. */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/services/api";

export function useBlobUrl(src: string | null | undefined): { url: string | null; loading: boolean; failed: boolean } {
  const { data: blob, isError, isLoading } = useQuery({
    queryKey: ["image", src],
    queryFn: () => api.imageBlob(src as string),
    enabled: !!src,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!blob) return setUrl(null);
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);

  return { url, loading: isLoading || (!!blob && !url), failed: isError };
}
