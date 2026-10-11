import { plural } from "@/lib/format";
import type { RunProgress } from "@/lib/useRunEvents";

type StageState = "pending" | "active" | "done" | "failed";

interface Stage {
  label: string;
  complete: boolean;
  detail?: string;
  bar?: { done: number; total: number };
}

function stages(p: RunProgress): Stage[] {
  const files = p.filesDone.size;
  const batches = p.batchesDone.size;
  const sections = p.sectionsDone.size;
  return [
    {
      label: "Load commits",
      complete: p.commits !== null,
      detail: p.commits !== null ? plural(p.commits, "commit") : undefined,
    },
    {
      label: "Filter noise",
      complete: p.filesTotal !== null,
      detail: p.filesTotal !== null ? `${plural(p.filesTotal, "file")} · ${p.skipped ?? 0} skipped` : undefined,
    },
    {
      label: "Analyze files",
      complete: p.batchesTotal !== null,
      detail: p.filesTotal !== null ? `${files}/${p.filesTotal} · ${p.cached.size} cached` : undefined,
      bar: p.filesTotal ? { done: files, total: p.filesTotal } : undefined,
    },
    {
      label: "Group batches",
      complete: p.batchesTotal !== null,
      detail: p.batchesTotal !== null ? plural(p.batchesTotal, "batch", "batches") : undefined,
    },
    {
      label: "Synthesize",
      complete: sections > 0 || p.written !== null,
      detail: p.batchesTotal !== null ? `${batches}/${plural(p.batchesTotal, "batch", "batches")}` : undefined,
      bar: p.batchesTotal ? { done: batches, total: p.batchesTotal } : undefined,
    },
    {
      label: "Write changelog",
      complete: p.written !== null,
      detail: sections > 0 ? plural(sections, "section") : undefined,
    },
    { label: "Done", complete: p.status === "done" },
  ];
}

function stateOf(list: Stage[], i: number, status: RunProgress["status"]): StageState {
  // A stage is complete if it or any later stage reports completion.
  if (list.slice(i).some((s) => s.complete) || status === "done") return "done";
  const firstOpen = list.findIndex((s, j) => !list.slice(j).some((t) => t.complete));
  if (i !== firstOpen) return "pending";
  if (status === "running") return "active";
  if (status === "failed" || status === "interrupted") return "failed";
  return "pending";
}

function Marker({ state, n }: { state: StageState; n: number }) {
  const base = "grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold";
  if (state === "done")
    return (
      <span className={`${base} bg-emerald-500 text-white`} aria-label="done">
        <svg viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} aria-hidden>
          <path d="M3.5 8.5l3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    );
  if (state === "failed")
    return (
      <span className={`${base} bg-red-500 text-white`} aria-label="stopped">
        !
      </span>
    );
  if (state === "active")
    return (
      <span className={`${base} relative bg-accent text-white`} aria-label="in progress">
        <span className="absolute inset-0 animate-ping rounded-full bg-accent/40" aria-hidden />
        {n}
      </span>
    );
  return <span className={`${base} bg-subtle text-muted ring-1 ring-border`}>{n}</span>;
}

export function PipelineProgress({ progress }: { progress: RunProgress }) {
  const list = stages(progress);
  return (
    <ol className="grid gap-x-3 gap-y-4 sm:grid-cols-2 md:grid-cols-4 xl:grid-cols-7">
      {list.map((stage, i) => {
        const state = stateOf(list, i, progress.status);
        const pct = stage.bar ? Math.min(100, Math.round((stage.bar.done / stage.bar.total) * 100)) : null;
        return (
          <li key={stage.label} className="flex min-w-0 gap-2.5 xl:flex-col xl:gap-2">
            <Marker state={state} n={i + 1} />
            <div className="min-w-0 flex-1">
              <div className={`text-sm font-medium ${state === "pending" ? "text-muted" : ""}`}>{stage.label}</div>
              {stage.detail && <div className="truncate text-xs tabular-nums text-muted">{stage.detail}</div>}
              {pct !== null && (
                <div
                  className="mt-1.5 h-1 overflow-hidden rounded-full bg-subtle"
                  role="progressbar"
                  aria-valuenow={pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${stage.label} progress`}
                >
                  <div
                    className={`h-full rounded-full transition-[width] duration-300 ${state === "failed" ? "bg-red-500" : state === "done" ? "bg-emerald-500" : "bg-accent"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
