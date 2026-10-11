"use client";

import { useEffect, useReducer, useRef } from "react";

import { eventsUrl } from "./api";
import { plural } from "./format";
import { RUN_EVENT_TYPES, type RunEvent, type RunEventType, type RunResult, type RunStatus } from "./types";

const MAX_LOG = 200;

export interface ActivityItem {
  id: number;
  kind: "file" | "batch" | "info";
  title: string;
  detail?: string;
  cached?: boolean;
  breaking?: boolean;
  changeType?: string;
}

/** Live pipeline progress. Counts are null until their stage has reported. */
export interface RunProgress {
  status: RunStatus | null;
  error: string | null;
  commits: number | null;
  filesTotal: number | null;
  skipped: number | null;
  /** `${commit_sha}:${path}` of analyzed files; a set so replays and checkpoints don't double count. */
  filesDone: Set<string>;
  cached: Set<string>;
  batchesTotal: number | null;
  batchesDone: Set<string>;
  sectionsDone: Set<string>;
  written: string[] | null;
  log: ActivityItem[];
}

/** Progress as already checkpointed, before any live events (also the view of finished runs). */
export function progressFromResult(result: RunResult | null): RunProgress {
  const fileKey = (a: { commit_sha: string; path: string }) => `${a.commit_sha}:${a.path}`;
  return {
    status: result?.run.status ?? null,
    error: result?.run.error ?? null,
    commits: result?.commit_count ?? null,
    filesTotal: result?.files_total ?? null,
    skipped: result && result.files_total !== null ? result.skipped.length : null,
    filesDone: new Set(result?.analyses.map(fileKey)),
    cached: new Set(result?.analyses.filter((a) => a.cached).map(fileKey)),
    batchesTotal: result?.batches_total ?? null,
    batchesDone: new Set(result?.summaries.map((s) => s.batch_id)),
    sectionsDone: new Set(result?.changelog_sections.map((s) => s.label)),
    written: result?.written ?? null,
    log: [],
  };
}

function withLog(state: RunProgress, item: ActivityItem): RunProgress {
  return { ...state, log: [item, ...state.log].slice(0, MAX_LOG) };
}

function reduce(state: RunProgress, event: RunEvent): RunProgress {
  switch (event.type) {
    case "status":
      return { ...state, status: event.data.status, error: event.data.error ?? null };
    case "commits":
      return withLog(
        { ...state, commits: event.data.count },
        { id: event.id, kind: "info", title: `Loaded ${plural(event.data.count, "commit")}` },
      );
    case "filtered":
      return withLog(
        { ...state, filesTotal: event.data.files_total, skipped: event.data.skipped.length },
        {
          id: event.id,
          kind: "info",
          title: `${plural(event.data.files_total, "file change")} to analyze`,
          detail: `${event.data.skipped.length} skipped as noise`,
        },
      );
    case "file_analyzed": {
      const d = event.data;
      const key = `${d.commit_sha}:${d.path}`;
      const filesDone = new Set(state.filesDone).add(key);
      const cached = d.cached ? new Set(state.cached).add(key) : state.cached;
      return withLog(
        { ...state, filesDone, cached },
        {
          id: event.id,
          kind: "file",
          title: d.path,
          detail: d.summary,
          cached: d.cached,
          breaking: d.breaking,
          changeType: d.change_type,
        },
      );
    }
    case "batches":
      return withLog(
        { ...state, batchesTotal: event.data.batches_total },
        {
          id: event.id,
          kind: "info",
          title: `Grouped into ${plural(event.data.batches_total, "batch", "batches")}`,
          detail: plural(event.data.sections.length, "release section"),
        },
      );
    case "batch_summarized": {
      const d = event.data;
      return withLog(
        { ...state, batchesDone: new Set(state.batchesDone).add(d.batch_id) },
        {
          id: event.id,
          kind: "batch",
          title: d.title,
          detail: `${d.section} · ${plural(d.note_count, "note")}`,
          breaking: d.breaking_count > 0,
        },
      );
    }
    case "changelog_section":
      return withLog(
        { ...state, sectionsDone: new Set(state.sectionsDone).add(event.data.label) },
        { id: event.id, kind: "info", title: `Changelog section ${event.data.label}`, detail: event.data.date },
      );
    case "written":
      return withLog(
        { ...state, written: event.data.paths },
        { id: event.id, kind: "info", title: "Wrote output", detail: event.data.paths.join(", ") },
      );
  }
}

/**
 * Subscribe to a live run's SSE stream while `enabled`, folding events into
 * progress seeded from `seed`. The seed is only read on mount, so give the
 * calling component a `key` that changes when a new subscription should start
 * from fresh data (e.g. after a resume).
 */
export function useRunEvents(
  runId: string,
  seed: RunResult | null,
  enabled: boolean,
  onEnd?: (status: RunStatus) => void,
): RunProgress {
  const [state, dispatch] = useReducer(reduce, seed, progressFromResult);
  const onEndRef = useRef(onEnd);
  useEffect(() => {
    onEndRef.current = onEnd;
  });

  useEffect(() => {
    if (!enabled) return;
    const source = new EventSource(eventsUrl(runId));
    const listeners = RUN_EVENT_TYPES.map((type: RunEventType) => {
      const listener = (msg: MessageEvent<string>) => {
        const event = { id: Number(msg.lastEventId), type, data: JSON.parse(msg.data) } as RunEvent;
        dispatch(event);
        if (event.type === "status" && event.data.status !== "running") {
          source.close();
          onEndRef.current?.(event.data.status);
        }
      };
      source.addEventListener(type, listener);
      return [type, listener] as const;
    });
    return () => {
      for (const [type, listener] of listeners) source.removeEventListener(type, listener);
      source.close();
    };
  }, [runId, enabled]);

  return state;
}
