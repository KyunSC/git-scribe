"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore, type FormEvent } from "react";

import { api, ApiError } from "@/lib/api";
import type { BatchBy, PullRef, RepoRefs } from "@/lib/types";

import { Card, ErrorText, buttonClass } from "./ui";

const REPO_KEY = "gitscribe:last-repo-path";
/** Wait for typing or pasting to settle before looking up branches. */
const REFS_DEBOUNCE_MS = 400;

const BATCH_OPTIONS: { value: BatchBy; label: string; hint: string }[] = [
  { value: "pr", label: "Pull request", hint: "One batch per merge; direct commits grouped" },
  { value: "tag", label: "Tag", hint: "One batch per release tag" },
  { value: "week", label: "Week", hint: "One batch per ISO week" },
];

type RefKind = "branch" | "pr";

const INPUT_CLASS =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/25 disabled:opacity-50";

const noSubscribe = () => () => {};

function readSavedPath(): string {
  try {
    return localStorage.getItem(REPO_KEY) ?? "";
  } catch {
    return "";
  }
}

function Segmented<T extends string>({ name, value, options, onChange }: {
  name: string;
  value: T;
  options: { value: T; label: string; hint?: string; disabled?: boolean }[];
  onChange: (value: T) => void;
}) {
  return (
    <div role="radiogroup" className="flex rounded-lg border border-border bg-background p-0.5">
      {options.map((o) => (
        <label
          key={o.value}
          title={o.hint}
          className={`flex-1 whitespace-nowrap rounded-md px-2.5 py-1.5 text-center text-sm transition-colors has-focus-visible:ring-2 has-focus-visible:ring-accent/40 ${
            o.disabled
              ? "cursor-not-allowed text-muted opacity-50"
              : value === o.value
                ? "cursor-pointer bg-surface font-medium shadow-sm ring-1 ring-border"
                : "cursor-pointer text-muted hover:text-foreground"
          }`}
        >
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={value === o.value}
            disabled={o.disabled}
            onChange={() => onChange(o.value)}
            className="sr-only"
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}

function pullLabel(p: PullRef): string {
  const state = p.draft ? " (draft)" : p.state !== "open" ? ` (${p.state})` : "";
  return `#${p.number} ${p.title}${state}`;
}

/** Branch (and, for GitHub, pull request) picker for the looked-up repository. */
function RefPicker({ refs, kind, branch, pr, onKind, onBranch, onPr }: {
  refs: RepoRefs;
  kind: RefKind;
  branch: string;
  pr: number | null;
  onKind: (kind: RefKind) => void;
  onBranch: (branch: string) => void;
  onPr: (pr: number) => void;
}) {
  const github = refs.kind === "github";
  const pull = refs.pulls.find((p) => p.number === pr);

  if (!github && refs.branches.length === 0) return null;

  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">{github ? "Branch or pull request" : "Branch"}</legend>
      <div className="grid gap-2 sm:grid-cols-[auto_minmax(0,1fr)]">
        {github && (
          <Segmented<RefKind>
            name="ref_kind"
            value={kind}
            onChange={onKind}
            options={[
              { value: "branch", label: `Branch · ${refs.branches.length}` },
              {
                value: "pr",
                label: `Pull request · ${refs.pulls.length}`,
                disabled: refs.pulls.length === 0,
                hint: refs.pulls.length === 0 ? "No open pull requests" : undefined,
              },
            ]}
          />
        )}
        {kind === "branch" || !github ? (
          <select
            aria-label="Branch"
            value={branch}
            onChange={(e) => onBranch(e.target.value)}
            className={`${INPUT_CLASS} font-mono`}
          >
            {refs.branches.map((b) => (
              <option key={b} value={b}>
                {b === refs.default_branch ? `${b} (${github ? "default" : "current"})` : b}
              </option>
            ))}
          </select>
        ) : (
          <select
            aria-label="Pull request"
            value={pr ?? ""}
            onChange={(e) => onPr(Number(e.target.value))}
            className={INPUT_CLASS}
          >
            {refs.pulls.map((p) => (
              <option key={p.number} value={p.number}>
                {pullLabel(p)}
              </option>
            ))}
          </select>
        )}
      </div>
      <p className="text-xs text-muted">
        {kind === "pr" && pull ? (
          <>
            Only the commits in #{pull.number}: <span className="font-mono">{pull.head}</span> since it branched
            off <span className="font-mono">{pull.base}</span>.
          </>
        ) : (
          <>
            All history reachable from <span className="font-mono">{branch}</span>.
          </>
        )}
      </p>
    </fieldset>
  );
}

export function NewRunForm() {
  const router = useRouter();
  // localStorage only exists in the browser: the server render sees "" and the client the saved path.
  const savedPath = useSyncExternalStore(noSubscribe, readSavedPath, () => "");
  const [editedPath, setRepoPath] = useState<string | null>(null);
  const repoPath = editedPath ?? savedPath;
  const [batchBy, setBatchBy] = useState<BatchBy>("pr");
  const [outDir, setOutDir] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Refs lookup, keyed by the repository it was made for so stale answers are ignored.
  const [lookup, setLookup] = useState<{ repo: string; refs?: RepoRefs; error?: string } | null>(null);
  const [refKind, setRefKind] = useState<RefKind>("branch");
  const [branch, setBranch] = useState("");
  const [pr, setPr] = useState<number | null>(null);

  const repo = repoPath.trim();
  const current = lookup?.repo === repo ? lookup : null;
  const refs = current?.refs ?? null;
  const lookingUp = repo !== "" && current === null;

  useEffect(() => {
    if (!repo) return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      api.getRefs(repo, ctrl.signal).then(
        (r) => {
          setLookup({ repo, refs: r });
          setRefKind(r.pr !== null ? "pr" : "branch");
          setBranch(r.branch ?? r.branches[0] ?? "");
          setPr(r.pr ?? r.pulls[0]?.number ?? null);
        },
        (err) => {
          if (!ctrl.signal.aborted) setLookup({ repo, error: err instanceof ApiError ? err.detail : String(err) });
        },
      );
    }, REFS_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [repo]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!repo) return;
    setSubmitting(true);
    setError(null);
    // Without a lookup (it failed), the backend falls back to HEAD / the default branch or whatever the link names.
    const selection =
      refs === null ? {} : refKind === "pr" && refs.kind === "github" ? { pr } : { branch: branch || null };
    try {
      const run = await api.createRun({
        repo,
        ...selection,
        batch_by: batchBy,
        output: "changelog",
        out_dir: outDir.trim() || null,
      });
      try {
        localStorage.setItem(REPO_KEY, repo);
      } catch {
        // storage unavailable (private mode): nothing to remember
      }
      router.push(`/runs/${run.run_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
      setSubmitting(false);
    }
  }

  return (
    <Card title="New run">
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="repo-path" className="text-sm font-medium">
            Repository
          </label>
          <input
            id="repo-path"
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            placeholder="/path/to/a/git/repo or https://github.com/owner/repo"
            spellCheck={false}
            autoComplete="off"
            required
            className={`${INPUT_CLASS} font-mono`}
          />
          {current?.error ? (
            <p role="alert" className="text-xs text-red-700 dark:text-red-300">
              {current.error}
            </p>
          ) : (
            <p className="text-xs text-muted" aria-live="polite">
              {lookingUp ? (
                "Looking up branches…"
              ) : refs?.kind === "github" ? (
                <>
                  <a href={refs.source ?? undefined} target="_blank" rel="noreferrer" className="hover:text-foreground">
                    {refs.repo_name}
                  </a>{" "}
                  on GitHub · fetched into a local cache when the run starts.
                </>
              ) : (
                "A path on the machine running the backend, or a GitHub link to a repo, branch or pull request."
              )}
            </p>
          )}
        </div>

        {refs && (
          <RefPicker
            refs={refs}
            kind={refKind}
            branch={branch}
            pr={pr}
            onKind={setRefKind}
            onBranch={setBranch}
            onPr={setPr}
          />
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Batch commits by</legend>
            <Segmented name="batch_by" value={batchBy} options={BATCH_OPTIONS} onChange={setBatchBy} />
            <p className="text-xs text-muted">{BATCH_OPTIONS.find((o) => o.value === batchBy)?.hint}</p>
          </fieldset>

          <div className="space-y-1.5">
            <label htmlFor="output" className="text-sm font-medium">
              Output
            </label>
            <select id="output" defaultValue="changelog" className={INPUT_CLASS}>
              <option value="changelog">Changelog</option>
              <option disabled>Module docs (coming soon)</option>
              <option disabled>Architecture (coming soon)</option>
            </select>
          </div>
        </div>

        <details className="group">
          <summary className="cursor-pointer text-sm text-muted hover:text-foreground">Output folder</summary>
          <div className="mt-2 space-y-1.5">
            <input
              aria-label="Output folder"
              value={outDir}
              onChange={(e) => setOutDir(e.target.value)}
              placeholder="output/<repo name>"
              spellCheck={false}
              className={`${INPUT_CLASS} font-mono`}
            />
            <p className="text-xs text-muted">Relative paths resolve against the backend&apos;s working directory.</p>
          </div>
        </details>

        {error && <ErrorText>{error}</ErrorText>}

        <div className="flex justify-end">
          <button type="submit" disabled={submitting || !repo || lookingUp} className={buttonClass("primary")}>
            {submitting ? (refs?.kind === "github" ? "Fetching repository…" : "Starting…") : "Generate changelog"}
          </button>
        </div>
      </form>
    </Card>
  );
}
