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

export interface ExportItem {
  content_id: string;
  product_id: string;
  product_name: string;
  item_url: string;
  room_text: string;
  x_text: string;
  has_ad_disclosure: boolean;
  checklist: string[];
  scheduled_at: string | null;
}

export interface ExportQueueResponse {
  items: ExportItem[];
}

export interface ImportErrorRow {
  raw_line: string;
  reason: string;
}

export interface ImportSummary {
  imported: number;
  updated: number;
  error_count: number;
  errors: ImportErrorRow[];
}

export interface GenreKpi {
  genre_id: string;
  genre_name: string;
  clicks: number;
  conversions: number;
  revenue: number;
}

export interface AnalyticsSummary {
  date_from: string | null;
  date_to: string | null;
  clicks: number;
  conversions: number;
  revenue: number;
  by_genre: GenreKpi[];
}

export interface AgentCost {
  agent: string;
  input_tokens: number;
  output_tokens: number;
  cost_jpy: number;
}

export interface CostSummary {
  month: string;
  total_cost_jpy: number;
  budget_jpy: number;
  by_agent: AgentCost[];
}

export interface PromptVersion {
  id: string;
  agent: string;
  version: string;
  body: string;
  is_active: boolean;
  note: string | null;
  created_at: string;
}

export interface LearningReportContent {
  summary: string;
  high_performer_patterns: string[];
  low_performer_patterns: string[];
  recommendations: string[];
}

export interface LearningReport {
  run_date: string | null;
  status:
    | "no_report"
    | "insufficient_data"
    | "budget_exceeded"
    | "invalid_llm_response"
    | "completed";
  data_point_count: number | null;
  report: LearningReportContent | null;
  proposed_prompt_version: PromptVersion | null;
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
  const isFormData = init?.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
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

export function fetchExportQueue(): Promise<ExportQueueResponse> {
  return request<ExportQueueResponse>("/api/v1/export/queue");
}

export function uploadAffiliateCsv(file: File): Promise<ImportSummary> {
  const formData = new FormData();
  formData.append("file", file);
  return request<ImportSummary>("/api/v1/import/affiliate-csv", {
    method: "POST",
    body: formData,
  });
}

export function fetchAnalyticsSummary(
  dateFrom?: string,
  dateTo?: string,
): Promise<AnalyticsSummary> {
  const params = new URLSearchParams();
  if (dateFrom) params.append("date_from", dateFrom);
  if (dateTo) params.append("date_to", dateTo);
  const query = params.toString();
  return request<AnalyticsSummary>(`/api/v1/analytics/summary${query ? `?${query}` : ""}`);
}

export function fetchCosts(month: string): Promise<CostSummary> {
  const params = new URLSearchParams({ month });
  return request<CostSummary>(`/api/v1/costs?${params.toString()}`);
}

export function fetchLearningReport(): Promise<LearningReport> {
  return request<LearningReport>("/api/v1/analytics/learning-report");
}

export function activatePrompt(
  agent: string,
  promptVersionId: string,
): Promise<PromptVersion> {
  return request<PromptVersion>(`/api/v1/prompts/${agent}/activate`, {
    method: "POST",
    body: JSON.stringify({ prompt_version_id: promptVersionId }),
  });
}
