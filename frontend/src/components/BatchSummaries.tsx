import { CATEGORY_LABELS, CATEGORY_ORDER, plural } from "@/lib/format";
import type { BatchSummary, Section } from "@/lib/types";

import { EmptyState } from "./ui";

function SummaryCard({ s }: { s: BatchSummary }) {
  return (
    <article className="min-w-0 rounded-lg border border-border bg-background p-4">
      <header>
        <h4 className="font-semibold leading-snug">{s.title}</h4>
        <p className="mt-0.5 truncate text-xs text-muted" title={s.label}>
          {s.label} · {s.date.slice(0, 10)}
        </p>
      </header>
      <p className="mt-2 text-sm">{s.narrative}</p>

      {s.breaking_changes.length > 0 && (
        <div className="mt-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-800 dark:text-red-200">
          <div className="text-xs font-semibold uppercase tracking-wide">Breaking</div>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            {s.breaking_changes.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </div>
      )}

      {CATEGORY_ORDER.map((cat) => {
        const notes = s.notes.filter((n) => n.category === cat);
        if (notes.length === 0) return null;
        return (
          <div key={cat} className="mt-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">{CATEGORY_LABELS[cat]}</div>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm">
              {notes.map((n, i) => (
                <li key={i}>{n.description}</li>
              ))}
            </ul>
          </div>
        );
      })}
    </article>
  );
}

export function BatchSummaries({ summaries, sections }: { summaries: BatchSummary[]; sections: Section[] }) {
  if (summaries.length === 0) return <EmptyState>No batch summaries yet.</EmptyState>;

  // Newest release first, summaries newest first within it.
  const order = new Map(sections.map((s) => [s.label, s.order]));
  const groups = new Map<string, BatchSummary[]>();
  for (const s of summaries) groups.set(s.section, [...(groups.get(s.section) ?? []), s]);
  const labels = [...groups.keys()].sort((a, b) => (order.get(b) ?? 0) - (order.get(a) ?? 0));

  return (
    <div className="space-y-6">
      {labels.map((label) => (
        <section key={label}>
          <h3 className="mb-2 text-sm font-semibold">
            {label}{" "}
            <span className="font-normal text-muted">
              · {plural(groups.get(label)!.length, "batch", "batches")}
            </span>
          </h3>
          <div className="grid gap-3 md:grid-cols-2">
            {groups
              .get(label)!
              .sort((a, b) => b.date.localeCompare(a.date))
              .map((s) => (
                <SummaryCard key={s.batch_id} s={s} />
              ))}
          </div>
        </section>
      ))}
    </div>
  );
}
