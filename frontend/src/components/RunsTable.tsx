"use client";

import Link from "next/link";

import { formatDateTime, formatDuration, runDuration } from "@/lib/format";
import type { RunInfo } from "@/lib/types";
import { useNow } from "@/lib/useNow";

import { StatusBadge } from "./StatusBadge";
import { Card, EmptyState } from "./ui";

export function RunsTable({ runs }: { runs: RunInfo[] | null }) {
  const now = useNow(runs?.some((r) => r.status === "running") ?? false);

  return (
    <Card title="Runs">
      {runs === null ? (
        <EmptyState>Loading…</EmptyState>
      ) : runs.length === 0 ? (
        <EmptyState>No runs yet. Start one above.</EmptyState>
      ) : (
        <div className="-mx-4 -my-4 overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr className="border-b border-border">
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Repository</th>
                <th className="px-4 py-2 font-medium">Run</th>
                <th className="px-4 py-2 font-medium">Started</th>
                <th className="px-4 py-2 text-right font-medium">Duration</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id} className="group relative border-b border-border last:border-0 hover:bg-subtle">
                  <td className="px-4 py-2.5">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="max-w-[16rem] px-4 py-2.5">
                    <Link
                      href={`/runs/${r.run_id}`}
                      className="font-medium after:absolute after:inset-0 group-hover:text-accent"
                      title={r.source ?? r.repo_path}
                    >
                      {r.repo_name}
                    </Link>
                    <div className="truncate text-xs text-muted" title={r.ref_title ?? undefined}>
                      {r.ref && (
                        <>
                          <span className="font-mono">{r.ref}</span>
                          {r.ref_title && ` ${r.ref_title}`} ·{" "}
                        </>
                      )}
                      by {r.batch_by}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-muted">{r.run_id}</td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-muted">{formatDateTime(r.started_at)}</td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums text-muted">
                    {formatDuration(runDuration(r.started_at, r.finished_at, now))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
