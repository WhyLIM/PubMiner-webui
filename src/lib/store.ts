import { create } from 'zustand';

export interface Task {
  id: string;
  query?: string;
  pmids?: string[];
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'partial';
  progress: number;
  total: number;
  completed: number;
  failed: number;
  createdAt: string;
  duration?: string;
  resultFile?: string;
  error?: string;
  message?: string;
  fullTextReport?: {
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
  citationReport?: {
    enabled: boolean;
    status: string;
    message: string;
    cited_by_status: string;
    references_status: string;
    cited_by_total: number;
    references_total: number;
  };
  extractionReport?: {
    attempted: number;
    cached_hits: number;
    fresh_runs: number;
    success: number;
    failed: number;
  };
  chunkReport?: Array<{
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
  articleReport?: Array<{
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

export interface ExtractionResult {
  pmid: string;
  [key: string]: any;
}

export interface SearchSession {
  source: 'query' | 'pmid' | null;
  query: string;
  totalAvailable: number;
  loadedCount: number;
  pageSize: number;
  hasMore: boolean;
}

export interface OAPdfCandidateState {
  source: "pmc" | "unpaywall" | "europepmc";
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

export interface OAPdfResolutionState {
  pmid: string;
  doi?: string | null;
  pmcid?: string | null;
  availability: "available" | "unavailable" | "ambiguous";
  best_candidate?: OAPdfCandidateState | null;
  candidates: OAPdfCandidateState[];
  reason: string;
  resolved_at: string;
}

interface AppState {
  // Tasks
  tasks: Task[];
  currentTask: Task | null;
  addTask: (task: Task) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  removeTask: (id: string) => void;
  setCurrentTask: (task: Task | null) => void;

  // Search results
  searchResults: SearchResult[];
  setSearchResults: (results: SearchResult[]) => void;
  appendSearchResults: (results: SearchResult[]) => void;
  selectedSearchPmids: string[];
  setSelectedSearchPmids: (pmids: string[]) => void;
  toggleSelectedSearchPmid: (pmid: string) => void;
  searchSession: SearchSession;
  setSearchSession: (session: SearchSession) => void;
  clearSearchResults: () => void;
  unpaywallEmail: string;
  setUnpaywallEmail: (email: string) => void;
  oaPdfByPmid: Record<string, OAPdfResolutionState>;
  setOaPdfResolutions: (resolutions: OAPdfResolutionState[]) => void;
  clearOaPdfResolutions: () => void;

  // Extraction results
  extractionResults: ExtractionResult[];
  setExtractionResults: (results: ExtractionResult[]) => void;

  // UI state
  showTasks: boolean;
  setShowTasks: (show: boolean) => void;
  showResults: boolean;
  setShowResults: (show: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Tasks
  tasks: [],
  currentTask: null,
  addTask: (task) => set((state) => ({ tasks: [task, ...state.tasks] })),
  updateTask: (id, updates) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.id === id ? { ...t, ...updates } : t)),
      currentTask: state.currentTask?.id === id ? { ...state.currentTask, ...updates } : state.currentTask,
    })),
  removeTask: (id) => set((state) => ({ tasks: state.tasks.filter((t) => t.id !== id) })),
  setCurrentTask: (task) => set({ currentTask: task }),

  // Search results
  searchResults: [],
  setSearchResults: (results) => set({ searchResults: results }),
  appendSearchResults: (results) =>
    set((state) => {
      const existing = new Set(state.searchResults.map((item) => item.pmid));
      const appended = results.filter((item) => !existing.has(item.pmid));
      return { searchResults: [...state.searchResults, ...appended] };
    }),
  selectedSearchPmids: [],
  setSelectedSearchPmids: (pmids) => set({ selectedSearchPmids: pmids }),
  toggleSelectedSearchPmid: (pmid) =>
    set((state) => ({
      selectedSearchPmids: state.selectedSearchPmids.includes(pmid)
        ? state.selectedSearchPmids.filter((item) => item !== pmid)
        : [...state.selectedSearchPmids, pmid],
    })),
  searchSession: {
    source: null,
    query: "",
    totalAvailable: 0,
    loadedCount: 0,
    pageSize: 0,
    hasMore: false,
  },
  setSearchSession: (session) => set({ searchSession: session }),
  clearSearchResults: () =>
    set({
      searchResults: [],
      selectedSearchPmids: [],
      oaPdfByPmid: {},
      searchSession: {
        source: null,
        query: "",
        totalAvailable: 0,
        loadedCount: 0,
        pageSize: 0,
        hasMore: false,
      },
    }),
  unpaywallEmail: "1632787660@qq.com",
  setUnpaywallEmail: (email) => set({ unpaywallEmail: email }),
  oaPdfByPmid: {},
  setOaPdfResolutions: (resolutions) =>
    set((state) => {
      const next = { ...state.oaPdfByPmid };
      for (const resolution of resolutions) {
        next[resolution.pmid] = resolution;
      }
      return { oaPdfByPmid: next };
    }),
  clearOaPdfResolutions: () => set({ oaPdfByPmid: {} }),

  // Extraction results
  extractionResults: [],
  setExtractionResults: (results) => set({ extractionResults: results }),

  // UI state
  showTasks: false,
  setShowTasks: (show) => set({ showTasks: show }),
  showResults: false,
  setShowResults: (show) => set({ showResults: show }),
}));
