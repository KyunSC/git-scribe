import type { ConfigInfo, RepoRefs, RunCreate, RunInfo, RunResult } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }

  /** True when the backend could not be reached at all (status 0). */
  get unreachable(): boolean {
    return this.status === 0;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, `Backend not reachable at ${API_URL}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      // non-JSON error body: keep the status text
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  config: () => request<ConfigInfo>("/api/config"),
  listRuns: () => request<RunInfo[]>("/api/runs"),
  getRun: (id: string) => request<RunInfo>(`/api/runs/${encodeURIComponent(id)}`),
  getResult: (id: string) => request<RunResult>(`/api/runs/${encodeURIComponent(id)}/result`),
  getRefs: (repo: string, signal?: AbortSignal) =>
    request<RepoRefs>(`/api/refs?${new URLSearchParams({ repo })}`, { signal }),
  createRun: (body: RunCreate) => request<RunInfo>("/api/runs", { method: "POST", body: JSON.stringify(body) }),
  resumeRun: (id: string) => request<RunInfo>(`/api/runs/${encodeURIComponent(id)}/resume`, { method: "POST" }),
};

export const eventsUrl = (id: string) => `${API_URL}/api/runs/${encodeURIComponent(id)}/events`;
export const changelogUrl = (id: string) => `${API_URL}/api/runs/${encodeURIComponent(id)}/changelog.md`;
