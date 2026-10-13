/** Upload limits as configured on the server (falls back to safe defaults until they load). */
import { useQuery } from "@tanstack/react-query";
import { DEFAULT_LIMITS, type FileLimits } from "@/lib/files";
import { api, keys } from "@/services/api";

export function useFileLimits(): FileLimits {
  const { data } = useQuery({ queryKey: keys.config, queryFn: api.config, staleTime: 60_000 });
  return data ? { maxBytes: data.limits.max_upload_mb * 1024 * 1024, extensions: data.limits.allowed_extensions } : DEFAULT_LIMITS;
}
