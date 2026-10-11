import type { RunStatus } from "@/lib/types";

const STYLES: Record<RunStatus, { label: string; className: string; dot: string }> = {
  running: {
    label: "Running",
    className: "bg-blue-500/10 text-blue-700 ring-blue-600/20 dark:text-blue-300",
    dot: "bg-blue-500 animate-pulse",
  },
  done: {
    label: "Done",
    className: "bg-emerald-500/10 text-emerald-700 ring-emerald-600/20 dark:text-emerald-300",
    dot: "bg-emerald-500",
  },
  failed: {
    label: "Failed",
    className: "bg-red-500/10 text-red-700 ring-red-600/20 dark:text-red-300",
    dot: "bg-red-500",
  },
  interrupted: {
    label: "Interrupted",
    className: "bg-amber-500/10 text-amber-800 ring-amber-600/20 dark:text-amber-300",
    dot: "bg-amber-500",
  },
};

export function StatusBadge({ status }: { status: RunStatus }) {
  const s = STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${s.className}`}
    >
      <span aria-hidden className={`size-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}
