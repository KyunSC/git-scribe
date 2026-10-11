"use client";

import { useMemo, useState } from "react";

import { CHANGE_TYPE_STYLES, shortSha } from "@/lib/format";
import type { ChangeType, FileAnalysis, Skipped } from "@/lib/types";

import { BreakingBadge, CachedBadge, ChangeTypeBadge, EmptyState } from "./ui";

const CHANGE_TYPES = Object.keys(CHANGE_TYPE_STYLES) as ChangeType[];

const controlClass =
  "rounded-lg border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/25";

function SkippedList({ skipped }: { skipped: Skipped[] }) {
  const byReason = useMemo(() => {
    const m = new Map<string, Skipped[]>();
    for (const s of skipped) m.set(s.reason, [...(m.get(s.reason) ?? []), s]);
    return [...m.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [skipped]);

  return (
    <details className="rounded-lg border border-border">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium">
        Skipped as noise <span className="font-normal text-muted">({skipped.length})</span>
      </summary>
      <div className="space-y-3 border-t border-border px-3 py-3">
        {byReason.map(([reason, items]) => (
          <div key={reason}>
            <div className="text-xs font-semibold text-muted">
              {reason} · {items.length}
            </div>
            <ul className="mt-1 space-y-0.5">
              {items.map((s) => (
                <li key={`${s.commit_sha}:${s.path}`} className="break-all font-mono text-xs">
                  <span className="text-muted">{shortSha(s.commit_sha)}</span> {s.path}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </details>
  );
}

export function FileAnalyses({ analyses, skipped, commitCount }: {
  analyses: FileAnalysis[];
  skipped: Skipped[];
  commitCount: number | null;
}) {
  const [type, setType] = useState<ChangeType | "">("");
  const [breakingOnly, setBreakingOnly] = useState(false);
  const [cache, setCache] = useState<"" | "cached" | "fresh">("");
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return analyses.filter(
      (a) =>
        (!type || a.change_type === type) &&
        (!breakingOnly || a.breaking) &&
        (!cache || a.cached === (cache === "cached")) &&
        (!q || a.path.toLowerCase().includes(q) || a.summary.toLowerCase().includes(q) || a.commit_sha.startsWith(q)),
    );
  }, [analyses, type, breakingOnly, cache, query]);

  if (analyses.length === 0) {
    return (
      <div className="space-y-4">
        <EmptyState>
          {commitCount === 0
            ? "No commits found."
            : skipped.length > 0
              ? "All changes were filtered as noise."
              : "No file analyses yet."}
        </EmptyState>
        {skipped.length > 0 && <SkippedList skipped={skipped} />}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search path, summary or sha"
          aria-label="Search files"
          className={`${controlClass} min-w-0 flex-1 basis-56`}
        />
        <select
          value={type}
          onChange={(e) => setType(e.target.value as ChangeType | "")}
          aria-label="Change type"
          className={controlClass}
        >
          <option value="">All types</option>
          {CHANGE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          value={cache}
          onChange={(e) => setCache(e.target.value as "" | "cached" | "fresh")}
          aria-label="Cache"
          className={controlClass}
        >
          <option value="">Cached + fresh</option>
          <option value="cached">Cached only</option>
          <option value="fresh">Fresh only</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={breakingOnly}
            onChange={(e) => setBreakingOnly(e.target.checked)}
            className="accent-red-600"
          />
          Breaking only
        </label>
      </div>

      <p className="text-xs text-muted">
        {rows.length} of {analyses.length} files
      </p>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[40rem] text-sm">
          <thead className="bg-subtle text-left text-xs text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">File</th>
              <th className="px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 font-medium">Summary</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((a) => (
              <tr
                key={`${a.commit_sha}:${a.path}`}
                className={`align-top ${a.breaking ? "bg-red-500/5" : ""}`}
              >
                <td className="max-w-[18rem] px-3 py-2">
                  <div className="break-all font-mono text-xs">{a.path}</div>
                  <div className="font-mono text-[0.7rem] text-muted">{shortSha(a.commit_sha)}</div>
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-col items-start gap-1">
                    <ChangeTypeBadge type={a.change_type} />
                    {a.breaking && <BreakingBadge />}
                    {a.cached && <CachedBadge />}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <p>{a.summary}</p>
                  {a.public_api_changes.length > 0 && (
                    <p className="mt-1 text-xs text-muted">
                      API: <span className="font-mono">{a.public_api_changes.join("; ")}</span>
                    </p>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <EmptyState>No files match these filters.</EmptyState>}
      </div>

      {skipped.length > 0 && <SkippedList skipped={skipped} />}
    </div>
  );
}
