// Mirrors fastapi-backend/gitscribe/api/models.py and gitscribe/schemas.py.

export type RunStatus = "running" | "done" | "failed" | "interrupted";
export type BatchBy = "pr" | "tag" | "week";
export type OutputKind = "changelog";

export type ChangeType =
  | "feature"
  | "bugfix"
  | "refactor"
  | "docs"
  | "test"
  | "chore"
  | "perf"
  | "style"
  | "build"
  | "ci";

export type ChangeCategory = "added" | "changed" | "fixed" | "removed" | "deprecated" | "security";

export interface RunCreate {
  /** A local repository path or a GitHub repository link. */
  repo: string;
  branch?: string | null;
  /** GitHub pull request number: documents only its commits. */
  pr?: number | null;
  batch_by?: BatchBy;
  output?: OutputKind;
  out_dir?: string | null;
}

export interface RunInfo {
  run_id: string;
  repo_path: string;
  repo_name: string;
  /** GitHub link, when the repository was fetched from one. */
  source: string | null;
  /** Branch name or "#<pr number>". */
  ref: string | null;
  ref_title: string | null;
  output: string;
  batch_by: string;
  out_dir: string;
  status: RunStatus;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface PullRef {
  number: number;
  title: string;
  base: string;
  head: string;
  author: string;
  state: "open" | "closed" | "merged";
  draft: boolean;
}

/** Refs a run can document; `branch`/`pr` is the one the link pointed at (or the default branch). */
export interface RepoRefs {
  kind: "local" | "github";
  repo_name: string;
  source: string | null;
  default_branch: string | null;
  branches: string[];
  pulls: PullRef[];
  branch: string | null;
  pr: number | null;
}

export interface ConfigInfo {
  provider: string;
  base_url: string;
  model_fast: string;
  model_strong: string;
  think_strong: boolean;
  num_ctx: number;
  max_concurrency: number;
}

/** Layer 1: FileChange plus where it came from. */
export interface FileAnalysis {
  commit_sha: string;
  path: string;
  cached: boolean;
  summary: string;
  change_type: ChangeType;
  breaking: boolean;
  public_api_changes: string[];
}

export interface Skipped {
  commit_sha: string;
  path: string;
  reason: string;
}

export interface Section {
  label: string;
  date: string;
  order: number;
}

export interface ChangeNote {
  category: ChangeCategory;
  description: string;
}

/** Layer 2: BatchSummary plus its batch. */
export interface BatchSummary {
  batch_id: string;
  label: string;
  section: string;
  date: string;
  title: string;
  narrative: string;
  notes: ChangeNote[];
  breaking_changes: string[];
}

export interface ChangelogEntry {
  added: string[];
  changed: string[];
  fixed: string[];
  removed: string[];
  deprecated: string[];
  security: string[];
  breaking: string[];
}

/** Layer 3: one release section of the changelog. */
export interface ChangelogSection extends Section {
  entry: ChangelogEntry;
}

/** Counts are null until the stage that produces them has been checkpointed. */
export interface RunResult {
  run: RunInfo;
  finished: boolean;
  commit_count: number | null;
  files_total: number | null;
  batches_total: number | null;
  sections: Section[];
  changelog_sections: ChangelogSection[];
  summaries: BatchSummary[];
  analyses: FileAnalysis[];
  skipped: Skipped[];
  written: string[] | null;
  markdown: string;
}

// --- SSE events (GET /api/runs/{id}/events) ---------------------------------

export interface RunEventMap {
  status: { status: RunStatus; error?: string | null };
  commits: { count: number };
  filtered: { files_total: number; skipped: Skipped[] };
  file_analyzed: Pick<FileAnalysis, "commit_sha" | "path" | "cached" | "change_type" | "breaking" | "summary">;
  batches: { batches_total: number; sections: Section[] };
  batch_summarized: {
    batch_id: string;
    title: string;
    section: string;
    note_count: number;
    breaking_count: number;
  };
  changelog_section: { label: string; date: string };
  written: { paths: string[] };
}

export type RunEventType = keyof RunEventMap;

export type RunEvent = {
  [K in RunEventType]: { id: number; type: K; data: RunEventMap[K] };
}[RunEventType];

export const RUN_EVENT_TYPES: RunEventType[] = [
  "status",
  "commits",
  "filtered",
  "file_analyzed",
  "batches",
  "batch_summarized",
  "changelog_section",
  "written",
];
