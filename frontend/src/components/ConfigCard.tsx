import type { ReactNode } from "react";

import type { ConfigInfo } from "@/lib/types";

import { Card, EmptyState } from "./ui";

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 truncate text-right font-mono text-xs" title={typeof value === "string" ? value : undefined}>
        {value}
      </dd>
    </div>
  );
}

export function ConfigCard({ config }: { config: ConfigInfo | null }) {
  return (
    <Card title="Model">
      {config === null ? (
        <EmptyState>Loading…</EmptyState>
      ) : (
        <>
          <dl className="divide-y divide-border text-sm">
            <Row label="Provider" value={config.provider} />
            <Row label="Fast model (layer 1)" value={config.model_fast} />
            <Row label="Strong model (layers 2–3)" value={config.model_strong} />
            <Row label="Thinking" value={config.think_strong ? "on" : "off"} />
            <Row label="Context window" value={config.num_ctx.toLocaleString()} />
            <Row label="Concurrency" value={config.max_concurrency} />
          </dl>
          {config.provider === "ollama" && (
            <p className="mt-3 rounded-lg bg-subtle px-3 py-2 text-xs text-muted">
              Runs need Ollama at <code className="font-mono">{config.base_url}</code>. Start it with{" "}
              <code className="font-mono text-foreground">ollama serve</code> and pull the models above.
            </p>
          )}
          {config.provider === "fake" && (
            <p className="mt-3 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-200">
              Fake provider: results are canned placeholders for UI development.
            </p>
          )}
        </>
      )}
    </Card>
  );
}
