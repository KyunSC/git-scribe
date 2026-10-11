import { Suspense } from "react";

import { RunDetail } from "@/components/RunDetail";
import { EmptyState } from "@/components/ui";

export default function RunPage({ params }: PageProps<"/runs/[runId]">) {
  return (
    <Suspense fallback={<EmptyState>Loading run…</EmptyState>}>
      {params.then(({ runId }) => (
        <RunDetail runId={runId} />
      ))}
    </Suspense>
  );
}
