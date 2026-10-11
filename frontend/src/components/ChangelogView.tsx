"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { changelogUrl } from "@/lib/api";

import { buttonClass } from "./ui";

export function ChangelogView({ runId, markdown, outputPath }: { runId: string; markdown: string; outputPath: string | null }) {
  const [copied, setCopied] = useState<"ok" | "failed" | null>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied("ok");
    } catch {
      setCopied("failed");
    }
    setTimeout(() => setCopied(null), 1500);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {outputPath ? (
          <p className="min-w-0 text-xs text-muted">
            Written to <code className="break-all font-mono text-foreground">{outputPath}</code>
          </p>
        ) : (
          <p className="text-xs text-muted">Not written to disk yet.</p>
        )}
        <div className="flex gap-2">
          <button type="button" onClick={copy} className={buttonClass()}>
            {copied === "ok" ? "Copied" : copied === "failed" ? "Copy failed" : "Copy"}
          </button>
          <a href={changelogUrl(runId)} download="CHANGELOG.md" className={buttonClass("primary")}>
            Download
          </a>
        </div>
      </div>
      <article className="prose-changelog rounded-lg border border-border bg-background px-4 py-4 sm:px-6">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      </article>
    </div>
  );
}
