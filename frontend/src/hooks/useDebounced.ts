/** useDebounced: follow a value, but only after it has stopped changing for ``delayMs`` (slider drags, typing). */
import { useEffect, useState } from "react";

export function useDebounced<T>(value: T, delayMs = 250): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return settled;
}
