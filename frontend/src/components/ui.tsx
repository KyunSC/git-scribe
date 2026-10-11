import type { ReactNode } from "react";

import { API_URL } from "@/lib/api";
import { CHANGE_TYPE_STYLES } from "@/lib/format";
import type { ChangeType } from "@/lib/types";

export function Card({ title, actions, children, className = "" }: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`min-w-0 rounded-xl border border-border bg-surface shadow-sm ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Badge({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${className}`}
    >
      {children}
    </span>
  );
}

export function ChangeTypeBadge({ type }: { type: ChangeType }) {
  return <Badge className={CHANGE_TYPE_STYLES[type] ?? CHANGE_TYPE_STYLES.chore}>{type}</Badge>;
}

export function BreakingBadge() {
  return <Badge className="bg-red-500/10 text-red-700 ring-red-600/30 dark:text-red-300">breaking</Badge>;
}

export function CachedBadge() {
  return <Badge className="bg-zinc-500/10 text-muted ring-zinc-500/20">cached</Badge>;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-muted">{children}</p>;
}

export function ErrorText({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300">
      {children}
    </p>
  );
}

export function BackendBanner() {
  return (
    <div
      role="alert"
      className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-200"
    >
      Backend not reachable at <code className="font-mono">{API_URL}</code>. Start it with{" "}
      <code className="rounded bg-amber-500/15 px-1 font-mono">uvicorn main:app --reload</code> in{" "}
      <code className="font-mono">fastapi-backend/</code>.
    </div>
  );
}

const BUTTON_VARIANTS = {
  primary: "bg-accent text-white hover:bg-accent/90 disabled:bg-accent/50",
  secondary: "border border-border bg-surface hover:bg-subtle disabled:opacity-50",
};

export function buttonClass(variant: keyof typeof BUTTON_VARIANTS = "secondary") {
  return `inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed ${BUTTON_VARIANTS[variant]}`;
}
