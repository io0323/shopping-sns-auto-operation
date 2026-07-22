export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface PageMeta {
  page: number;
  per_page: number;
  total: number;
}

export interface Candidate {
  id: string;
  product_id: string;
  product_name: string;
  genre_name: string;
  shop_name: string;
  item_url: string;
  image_url: string | null;
  selected_date: string;
  score: number;
  score_breakdown: Record<string, number>;
  status: string;
}

export interface CandidateListResponse {
  items: Candidate[];
  meta: PageMeta;
}

export interface Content {
  id: string;
  product_id: string;
  candidate_id: string;
  product_name: string;
  title: string;
  description: string;
  hashtags: string[];
  x_post: string;
  cta: string;
  quality_score: number | null;
  quality_breakdown: Record<string, number> | null;
  eval_comment: string | null;
  regen_count: number;
  prompt_version: string;
  status: string;
  scheduled_at: string | null;
  posted_at: string | null;
  edited_by_human: boolean;
  created_at: string;
  updated_at: string;
}

export interface ContentListResponse {
  items: Content[];
  meta: PageMeta;
}

export interface ContentUpdatePayload {
  title?: string;
  description?: string;
  hashtags?: string[];
  x_post?: string;
  cta?: string;
  scheduled_at?: string | null;
}

interface ApiErrorBody {
  error: { code: string; message: string };
}

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      body = null;
    }
    throw new ApiError(
      response.status,
      body?.error?.code ?? "UNKNOWN",
      body?.error?.message ?? response.statusText,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function fetchCandidates(date: string): Promise<CandidateListResponse> {
  const params = new URLSearchParams({ date });
  return request<CandidateListResponse>(`/api/v1/candidates?${params.toString()}`);
}

export function fetchContents(
  statuses: string[],
  sort?: string,
): Promise<ContentListResponse> {
  const params = new URLSearchParams();
  statuses.forEach((status) => params.append("status", status));
  if (sort) params.append("sort", sort);
  params.append("per_page", "200");
  return request<ContentListResponse>(`/api/v1/contents?${params.toString()}`);
}

export function updateContent(
  id: string,
  payload: ContentUpdatePayload,
): Promise<Content> {
  return request<Content>(`/api/v1/contents/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function approveContent(id: string): Promise<Content> {
  return request<Content>(`/api/v1/contents/${id}/approve`, { method: "POST" });
}

export function rejectContent(id: string): Promise<Content> {
  return request<Content>(`/api/v1/contents/${id}/reject`, { method: "POST" });
}

export function markContentPosted(id: string): Promise<Content> {
  return request<Content>(`/api/v1/contents/${id}/mark-posted`, { method: "POST" });
}
