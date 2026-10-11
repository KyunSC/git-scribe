"use client";

import { useEffect, useState } from "react";

import { ConfigCard } from "@/components/ConfigCard";
import { NewRunForm } from "@/components/NewRunForm";
import { RunsTable } from "@/components/RunsTable";
import { BackendBanner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { ConfigInfo, RunInfo } from "@/lib/types";

const REFRESH_MS = 5000;

export default function Dashboard() {
  const [runs, setRuns] = useState<RunInfo[] | null>(null);
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const handle = (err: unknown) => {
      if (!cancelled && err instanceof ApiError && err.unreachable) setUnreachable(true);
    };
    const load = () => {
      api
        .listRuns()
        .then((r) => {
          if (cancelled) return;
          setRuns(r);
          setUnreachable(false);
        })
        .catch(handle);
      api
        .config()
        .then((c) => !cancelled && setConfig(c))
        .catch(handle);
    };
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="space-y-6">
      {unreachable && <BackendBanner />}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          <NewRunForm />
          <RunsTable runs={runs} />
        </div>
        <aside className="min-w-0">
          <ConfigCard config={config} />
        </aside>
      </div>
    </div>
  );
}
