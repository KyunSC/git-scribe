import type { ChangeCategory, ChangeType } from "./types";

export const shortSha = (sha: string) => sha.slice(0, 8);

/** `3 files`, `1 file`; irregular plurals pass `many`. */
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

/** Elapsed ms of a run; null while it is running and the clock hasn't been read yet. */
export function runDuration(startedAt: string, finishedAt: string | null, now: number | null): number | null {
  const end = finishedAt ? Date.parse(finishedAt) : now;
  return end === null ? null : end - Date.parse(startedAt);
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export const CHANGE_TYPE_STYLES: Record<ChangeType, string> = {
  feature: "bg-emerald-500/10 text-emerald-700 ring-emerald-600/20 dark:text-emerald-300",
  bugfix: "bg-orange-500/10 text-orange-700 ring-orange-600/20 dark:text-orange-300",
  refactor: "bg-violet-500/10 text-violet-700 ring-violet-600/20 dark:text-violet-300",
  docs: "bg-sky-500/10 text-sky-700 ring-sky-600/20 dark:text-sky-300",
  test: "bg-lime-500/10 text-lime-700 ring-lime-600/20 dark:text-lime-300",
  chore: "bg-zinc-500/10 text-zinc-600 ring-zinc-500/20 dark:text-zinc-300",
  perf: "bg-fuchsia-500/10 text-fuchsia-700 ring-fuchsia-600/20 dark:text-fuchsia-300",
  style: "bg-pink-500/10 text-pink-700 ring-pink-600/20 dark:text-pink-300",
  build: "bg-amber-500/10 text-amber-700 ring-amber-600/20 dark:text-amber-300",
  ci: "bg-cyan-500/10 text-cyan-700 ring-cyan-600/20 dark:text-cyan-300",
};

export const CATEGORY_ORDER: ChangeCategory[] = ["added", "changed", "fixed", "removed", "deprecated", "security"];

export const CATEGORY_LABELS: Record<ChangeCategory, string> = {
  added: "Added",
  changed: "Changed",
  fixed: "Fixed",
  removed: "Removed",
  deprecated: "Deprecated",
  security: "Security",
};
