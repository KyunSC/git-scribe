import type { ChangeType } from "@/lib/types";
import type { ActivityItem } from "@/lib/useRunEvents";

import { BreakingBadge, CachedBadge, ChangeTypeBadge, EmptyState } from "./ui";

const KIND_ICON: Record<ActivityItem["kind"], string> = { file: "L1", batch: "L2", info: "•" };

export function ActivityFeed({ items, live }: { items: ActivityItem[]; live: boolean }) {
  if (items.length === 0)
    return <EmptyState>{live ? "Waiting for the pipeline…" : "Live activity appears here while a run is in progress."}</EmptyState>;
  return (
    <ol className="-mx-4 -my-4 max-h-96 divide-y divide-border overflow-y-auto" aria-live="polite">
      {items.map((item) => (
        <li key={item.id} className="flex gap-3 px-4 py-2 text-sm">
          <span
            aria-hidden
            className="mt-0.5 w-6 shrink-0 text-center font-mono text-[0.65rem] leading-5 text-muted"
          >
            {KIND_ICON[item.kind]}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className={`min-w-0 break-all ${item.kind === "file" ? "font-mono text-xs" : "font-medium"}`}>
                {item.title}
              </span>
              {item.changeType && <ChangeTypeBadge type={item.changeType as ChangeType} />}
              {item.breaking && <BreakingBadge />}
              {item.cached && <CachedBadge />}
            </div>
            {item.detail && <p className="line-clamp-2 text-xs text-muted">{item.detail}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
