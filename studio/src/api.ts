import type { AssetRecord, Health, Job, TeachingPlanSummary } from "./types";

let token: string | null = null;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.method && init.method !== "GET" && token) {
    headers.set("X-Yue-Token", token);
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function loadSession(): Promise<void> {
  const data = await request<{ token: string | null }>("/api/session");
  token = data.token;
}

export function fetchHealth(): Promise<Health> {
  return request<Health>("/api/health");
}

export async function uploadImage(file: File): Promise<{ uploadId: string }> {
  const form = new FormData();
  form.append("file", file);
  return request<{ uploadId: string }>("/api/uploads", { method: "POST", body: form });
}

export function createJob(payload: {
  uploadId?: string;
  grade?: number;
  subjectHint?: string;
  demo?: boolean;
}): Promise<Job> {
  return request<Job>("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchJob(jobId: string): Promise<Job> {
  return request<Job>(`/api/jobs/${jobId}`);
}

export function regenerateJob(
  jobId: string,
  payload: { mode?: string; feedback?: string },
): Promise<Job> {
  return request<Job>(`/api/jobs/${jobId}/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchJobs(): Promise<Job[]> {
  return request<Job[]>("/api/jobs");
}

export function cancelJob(jobId: string): Promise<Job> {
  return request<Job>(`/api/jobs/${jobId}/cancel`, { method: "POST" });
}

export function fetchPlan(jobId: string): Promise<TeachingPlanSummary> {
  return request<TeachingPlanSummary>(`/api/jobs/${jobId}/plan`);
}

export function exportPackage(jobId: string): Promise<{ downloadUrl: string }> {
  return request<{ downloadUrl: string }>(`/api/jobs/${jobId}/exports`, { method: "POST" });
}

export function fetchAssets(): Promise<AssetRecord[]> {
  return request<AssetRecord[]>("/api/assets");
}

export function createAsset(payload: Record<string, string>): Promise<{ assetId: string }> {
  return request<{ assetId: string }>("/api/assets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function jobVideoUrl(jobId: string): string {
  return `/api/jobs/${jobId}/video`;
}

export function jobSubtitleUrl(jobId: string): string {
  return `/api/jobs/${jobId}/subtitles`;
}

export function jobPackageUrl(jobId: string): string {
  return `/api/jobs/${jobId}/package`;
}
