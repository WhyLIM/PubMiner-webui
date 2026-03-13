const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
  article_report?: Array<{
    pmid: string;
    pmcid?: string;
    title: string;
    journal?: string;
    year?: string | number | null;
    has_fulltext: boolean;
    fulltext_status: string;
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
