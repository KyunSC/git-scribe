"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { formatDateTime, formatDuration, runDuration } from "@/lib/format";
import type { RunResult } from "@/lib/types";
import { useNow } from "@/lib/useNow";
import { progressFromResult, useRunEvents } from "@/lib/useRunEvents";

import { ActivityFeed } from "./ActivityFeed";
import { BatchSummaries } from "./BatchSummaries";
import { ChangelogView } from "./ChangelogView";
import { FileAnalyses } from "./FileAnalyses";
import { PipelineProgress } from "./PipelineProgress";
import { StatusBadge } from "./StatusBadge";
import { BackendBanner, Card, EmptyState, ErrorText, buttonClass } from "./ui";

/** While a run is live, re-read checkpointed results this often so the tabs fill in. */
const LIVE_REFRESH_MS = 4000;

type Tab = "changelog" | "batches" | "files";

/** The GitHub page for the run's branch or pull request. */
function pullOrRepoUrl(source: string, ref: string | null): string {
  if (!ref) return source;
  return ref.startsWith("#") ? `${source}/pull/${ref.slice(1)}` : `${source}/tree/${ref}`;
}

/** Progress stepper and activity feed; keyed by the parent so each subscription starts from a fresh seed. */
function LiveProgress({ result, onEnd }: { result: RunResult; onEnd: () => void }) {
  const live = result.run.status === "running";
  const events = useRunEvents(result.run.run_id, result, live, onEnd);
  // Once the run has ended, the latest result is authoritative; keep the activity log.
  const progress = live ? events : { ...progressFromResult(result), log: events.log };
  return (
    <>
      <Card title="Pipeline">
        <PipelineProgress progress={progress} />
      </Card>
      {(live || progress.log.length > 0) && (
        <Card title="Activity">
          <ActivityFeed items={progress.log} live={live} />
        </Card>
      )}
    </>
  );
}

function Results({ result }: { result: RunResult }) {
  const [tab, setTab] = useState<Tab>("changelog");
  const { run } = result;
  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "changelog", label: "Changelog", count: result.changelog_sections.length },
    { id: "batches", label: "Batches", count: result.summaries.length },
    { id: "files", label: "Files", count: result.analyses.length },
  ];
  const outputPath = result.written?.[0] ?? null;

  return (
    <Card>
      <div role="tablist" aria-label="Results" className="-mx-4 -mt-4 mb-4 flex gap-1 overflow-x-auto border-b border-border px-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
              tab === t.id ? "border-accent text-foreground" : "border-transparent text-muted hover:text-foreground"
            }`}
          >
            {t.label}
            {t.count !== undefined && <span className="ml-1.5 text-xs tabular-nums text-muted">{t.count}</span>}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "changelog" &&
          (result.changelog_sections.length > 0 ? (
            <ChangelogView runId={run.run_id} markdown={result.markdown} outputPath={outputPath} />
          ) : (
            <EmptyState>
              {result.commit_count === 0
                ? "No commits found."
                : result.files_total === 0
                  ? "All changes were filtered as noise."
                  : run.status === "running"
                    ? "The changelog is written after all batches are summarized."
                    : run.status === "done"
                      ? "No changelog sections were produced."
                      : "No changelog yet. Resume the run to finish it."}
            </EmptyState>
          ))}
        {tab === "batches" && <BatchSummaries summaries={result.summaries} sections={result.sections} />}
        {tab === "files" && (
          <FileAnalyses analyses={result.analyses} skipped={result.skipped} commitCount={result.commit_count} />
        )}
      </div>
    </Card>
  );
}

export function RunDetail({ runId }: { runId: string }) {
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [session, setSession] = useState(0);
  const [resuming, setResuming] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.getResult(runId).then(
      (r) => {
        setResult(r);
        setError(null);
      },
      (err) => setError(err instanceof ApiError ? err : new ApiError(500, String(err))),
    );
  }, [runId]);

  const status = result?.run.status;

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (status !== "running") return;
    const id = setInterval(load, LIVE_REFRESH_MS);
    return () => clearInterval(id);
  }, [status, load]);

  const now = useNow(status === "running");

  async function resume() {
    setResuming(true);
    setResumeError(null);
    try {
      await api.resumeRun(runId);
      const fresh = await api.getResult(runId);
      // Same tick: the remounted progress panel seeds from the fresh result.
      setResult(fresh);
      setSession((s) => s + 1);
    } catch (err) {
      setResumeError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setResuming(false);
    }
  }

  if (!result) {
    if (error?.unreachable) return <BackendBanner />;
    if (error) {
      return (
        <div className="space-y-4">
          <ErrorText>{error.status === 404 ? `Run ${runId} not found.` : error.detail}</ErrorText>
          <Link href="/" className={buttonClass()}>
            Back to runs
          </Link>
        </div>
      );
    }
    return <EmptyState>Loading run…</EmptyState>;
  }

  const { run } = result;
  const hasResults =
    result.analyses.length > 0 || result.summaries.length > 0 || result.skipped.length > 0 || result.commit_count !== null;

  return (
    <div className="space-y-6">
      {error?.unreachable && <BackendBanner />}

      <div className="space-y-3">
        <Link href="/" className="text-sm text-muted hover:text-foreground">
          ← All runs
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold tracking-tight">{run.repo_name}</h1>
              <StatusBadge status={run.status} />
            </div>
            {run.ref && (
              <p className="mt-1 text-sm">
                <span className="font-mono">{run.ref}</span>
                {run.ref_title && <span className="text-muted"> {run.ref_title}</span>}
              </p>
            )}
            <p className="mt-1 break-all font-mono text-xs text-muted">
              {run.source ? (
                <a href={pullOrRepoUrl(run.source, run.ref)} target="_blank" rel="noreferrer" className="hover:text-foreground">
                  {run.source}
                </a>
              ) : (
                run.repo_path
              )}
            </p>
            <p className="mt-1 text-xs text-muted">
              Run <span className="font-mono">{run.run_id}</span> · by {run.batch_by} · started{" "}
              {formatDateTime(run.started_at)} ·{" "}
              <span className="tabular-nums">{formatDuration(runDuration(run.started_at, run.finished_at, now))}</span>
            </p>
          </div>
          {(run.status === "failed" || run.status === "interrupted") && (
            <button type="button" onClick={resume} disabled={resuming} className={buttonClass("primary")}>
              {resuming ? "Resuming…" : "Resume"}
            </button>
          )}
        </div>
        {run.status === "failed" && run.error && <ErrorText>Run failed: {run.error}</ErrorText>}
        {run.status === "interrupted" && (
          <p className="text-sm text-muted">
            The server stopped during this run. Resume continues from the last checkpoint; analyzed files come from
            the cache.
          </p>
        )}
        {resumeError && <ErrorText>{resumeError}</ErrorText>}
      </div>

      <LiveProgress key={session} result={result} onEnd={load} />

      {hasResults && <Results result={result} />}
    </div>
  );
}
