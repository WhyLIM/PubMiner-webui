const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function extractErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === "string" && data.detail) {
      return data.detail;
    }
  } catch {
    // Ignore JSON parse failures and use the fallback.
  }

  return fallback;
}

export interface SearchRequest {
  query: string;
  max_results?: number;
  offset?: number;
}

export interface SearchResult {
  pmid: string;
  title: string;
  authors: string[];
  firstAuthor?: string;
  affiliation?: string;
  journal: string;
  year: string;
  articleType?: string;
  publicationStatus?: string;
  language?: string;
  doi?: string;
  abstract?: string;
  hasFullText: boolean;
  pmcid?: string;
}

export interface OAPdfCandidate {
  source: "pmc" | "unpaywall";
  pdf_url?: string;
  landing_page_url?: string;
  license?: string;
  host_type?: "publisher" | "repository";
  version?: string;
  evidence: string;
  can_download: boolean;
  can_cache: boolean;
  score: number;
}

export interface OAPdfResolution {
  pmid: string;
  doi?: string | null;
  pmcid?: string | null;
  availability: "available" | "unavailable" | "ambiguous";
  best_candidate?: OAPdfCandidate | null;
  candidates: OAPdfCandidate[];
  reason: string;
  resolved_at: string;
}

export interface SearchResponse {
  success: boolean;
  query: string;
  total: number;
  total_available: number;
  offset: number;
  returned_count: number;
  has_more: boolean;
  results: SearchResult[];
}

export interface MetadataResponse {
  success: boolean;
  total: number;
  results: Array<{
    pmid: string;
    title?: string;
    authors?: string[];
    first_author?: string;
    affiliation?: string;
    journal?: string;
    year?: number | string;
    pub_date?: string;
    publication_date?: string;
    article_type?: string;
    publication_status?: string;
    language?: string;
    doi?: string;
    abstract?: string;
    pmcid?: string;
  }>;
}

export interface ExtractionRequest {
  pmids: string[];
  custom_fields?: Array<{
    name: string;
    description: string;
    type: string;
    enumValues?: string[];
  }> | null;
  fetch_citations?: boolean;
}

export interface ExtractionResponse {
  success: boolean;
  task_id: string;
  message: string;
  article_count?: number;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  progress: number;
  message: string;
  result_file?: string;
  fulltext_report?: {
    pmc_candidates: number;
    downloaded: number;
    failed: number;
    fallback_used: number;
    cache_hits: number;
    cache_misses: number;
    failure_counts: Record<string, number>;
    failure_labels: Record<string, string>;
    failed_items: Array<{
      pmcid: string;
      pmid?: string;
      reason: string;
      message: string;
      used_fallback: boolean;
    }>;
  };
  citation_report?: {
    enabled: boolean;
    status: string;
    message: string;
    cited_by_status: string;
    references_status: string;
    cited_by_total: number;
    references_total: number;
  };
  extraction_report?: {
    attempted: number;
    cached_hits: number;
    fresh_runs: number;
    success: number;
    failed: number;
  };
  chunk_report?: Array<{
    chunk_index: number;
    article_count: number;
    status: string;
    fulltext_downloaded: number;
    extraction_success: number;
    extraction_failed: number;
    cached_hits: number;
    pmids: string[];
    message: string;
  }>;
  article_report?: Array<{
    pmid: string;
    pmcid?: string;
    title: string;
    journal?: string;
    year?: string | number | null;
    has_fulltext: boolean;
    citation_status?: string;
    fulltext_status: string;
    oa_pdf_status?: string;
    extraction_status: string;
    result_status: string;
    error?: string;
  }>;
}

export interface DownloadResult {
  blob: Blob;
  filename: string;
}

export interface ResultPreviewResponse {
  filename: string;
  mode: string;
  columns: string[];
  rows: Array<Record<string, string | number | null>>;
  preview_rows: number;
  total_rows: number;
}

export interface ResolveOAPdfResponse {
  success: boolean;
  results: OAPdfResolution[];
}

export async function searchPubMed(request: SearchRequest): Promise<SearchResponse> {
  const response = await fetch(`${API_BASE_URL}/api/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Search failed: ${response.statusText}`);
  }

  return response.json();
}

export async function startExtraction(request: ExtractionRequest): Promise<ExtractionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/extract`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Extraction failed: ${response.statusText}`);
  }

  return response.json();
}

export async function retryTaskArticles(
  taskId: string,
  request: {
    pmids?: string[];
    mode?: "failed" | "incomplete" | "all";
  }
): Promise<ExtractionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/tasks/${taskId}/retry`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, `Retry failed: ${response.statusText}`));
  }

  return response.json();
}

export async function fetchMetadata(pmids: string[]): Promise<SearchResult[]> {
  const response = await fetch(`${API_BASE_URL}/api/fetch-metadata`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ pmids }),
  });

  if (!response.ok) {
    throw new Error(`Metadata fetch failed: ${response.statusText}`);
  }

  const data: MetadataResponse = await response.json();

  return data.results.map((item) => ({
    pmid: item.pmid,
    title: item.title || '',
    authors: item.authors || [],
    firstAuthor: item.first_author || '',
    affiliation: item.affiliation || '',
    journal: item.journal || '',
    year: String(item.year || item.pub_date?.slice(0, 4) || item.publication_date?.slice(0, 4) || ''),
    articleType: item.article_type || '',
    publicationStatus: item.publication_status || '',
    language: item.language || '',
    doi: item.doi || '',
    abstract: item.abstract || '',
    hasFullText: Boolean(item.pmcid),
    pmcid: item.pmcid,
  }));
}

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  const response = await fetch(`${API_BASE_URL}/api/tasks/${taskId}`);

  if (!response.ok) {
    throw new Error(`Failed to get task status: ${response.statusText}`);
  }

  return response.json();
}

export async function downloadResults(
  filename: string,
  mode: "all" | "metadata" | "extraction" = "all"
): Promise<DownloadResult> {
  const response = await fetch(`${API_BASE_URL}/api/results/${filename}?mode=${mode}`);

  if (!response.ok) {
    throw new Error(`Failed to download results: ${response.statusText}`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const matched = disposition.match(/filename="?([^"]+)"?/i);

  return {
    blob,
    filename: matched?.[1] || filename,
  };
}

export async function getResultPreview(
  filename: string,
  limit = 20,
  mode: "all" | "metadata" | "extraction" = "all"
): Promise<ResultPreviewResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/results/${filename}/preview?limit=${limit}&mode=${mode}`
  );

  if (!response.ok) {
    throw new Error(`Failed to preview results: ${response.statusText}`);
  }

  return response.json();
}

export async function resolveOAPdf(articles: Array<{
  pmid: string;
  doi?: string;
  pmcid?: string;
  title?: string;
}>, unpaywallEmail?: string): Promise<OAPdfResolution[]> {
  const response = await fetch(`${API_BASE_URL}/api/resolve-oa-pdf`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ articles, unpaywall_email: unpaywallEmail }),
  });

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, `OA PDF resolve failed: ${response.statusText}`));
  }

  const data: ResolveOAPdfResponse = await response.json();
  return data.results;
}

export async function downloadOAPdf(article: {
  pmid: string;
  doi?: string;
  pmcid?: string;
  title?: string;
}, unpaywallEmail?: string): Promise<DownloadResult> {
  const response = await fetch(`${API_BASE_URL}/api/download-oa-pdf`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ article, unpaywall_email: unpaywallEmail }),
  });

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, `Failed to download OA PDF: ${response.statusText}`));
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const matched = disposition.match(/filename="?([^"]+)"?/i);

  return {
    blob,
    filename: matched?.[1] || `${article.pmid}.pdf`,
  };
}

export async function downloadOAPdfs(
  articles: Array<{
    pmid: string;
    doi?: string;
    pmcid?: string;
    title?: string;
  }>,
  unpaywallEmail?: string
): Promise<DownloadResult> {
  const response = await fetch(`${API_BASE_URL}/api/download-oa-pdfs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ articles, unpaywall_email: unpaywallEmail }),
  });

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response, `Failed to batch download OA PDFs: ${response.statusText}`));
  }

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const matched = disposition.match(/filename="?([^"]+)"?/i);

  return {
    blob,
    filename: matched?.[1] || "oa_pdfs.zip",
  };
}
