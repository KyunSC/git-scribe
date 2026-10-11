"use client";

import { useEffect, useState } from "react";

/**
 * The current time in ms, re-read every `intervalMs` while `ticking`.
 * Null until the first tick, since the clock must not be read while prerendering.
 */
export function useNow(ticking: boolean, intervalMs = 1000): number | null {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (!ticking) return;
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, intervalMs);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [ticking, intervalMs]);
  return now;
}
