export type RetrievalMode = 'best' | 'hybrid';

export interface RetrievalModeOption {
  value: RetrievalMode;
  label: string;
  description: string;
  resolved_method: string;
  available: boolean;
}

export interface QuestionSuggestion {
  id: number;
  question: string;
  source?: string | null;
  difficulty?: string | null;
  question_type?: string | null;
  score: number;
  match_type: 'exact' | 'prefix' | 'contains' | 'token' | 'fuzzy';
}

export interface QuestionSuggestionsResponse {
  query: string;
  count: number;
  suggestions: QuestionSuggestion[];
}

export interface RagSource {
  source_id: string;
  title: string;
  category: string;
  page_start: number;
  page_end: number;
  article?: string | null;
  note?: string | null;
  chunk_id: string;
  score: number;
  text: string;
}

export interface RagResponse {
  question: string;
  answer: string;
  citations: string[];
  no_answer: boolean;
  confidence: number | null;
  provider_alias: string;
  model: string;
  prompt_variant?: string;
  retriever_method: string;
  latency_seconds: number;
  cached?: boolean;
  sources: RagSource[];
  demo_mode?: boolean;
  diagnostics?: {
    requested_retrieval_mode?: RetrievalMode;
    resolved_retriever_method?: string;
    [key: string]: unknown;
  } | null;
}

export interface QueryRequest {
  question: string;
  top_k?: number;
  category?: string | null;
  retrieval_mode?: RetrievalMode;
  provider?: 'mock' | 'openai' | 'gemini';
  model?: string | null;
}

export interface HistoryItem {
  id: string;
  question: string;
  answer: string;
  createdAt: string;
  response: RagResponse;
}

export interface DocumentItem {
  id: string;
  title: string;
  category: string;
  pages: number;
  chunks: number;
  extraction: 'direct' | 'ocr' | 'mixed';
  status: 'ready' | 'needs_review';
  updatedAt: string;
}

export interface SystemHealth {
  status: 'ready' | 'degraded' | 'offline';
  documents: number;
  chunks: number;
  model: string;
  retriever: string;
  updatedAt: string;
}

export interface FrontendSettings {
  topK: number;
  category: string;
  showScores: boolean;
  autoOpenSources: boolean;
  mockFallback: boolean;
}


export interface ClientConfig {
  active_provider?: string | null;
  provider?: string | null;
  active_model?: string | null;
  model?: string | null;
  configured?: boolean;
  default_top_k?: number;
  maximum_top_k?: number;
  categories?: string[];
  upload_enabled?: boolean;
  rebuild_enabled?: boolean;
  llm_settings_enabled?: boolean;
  default_retrieval_mode?: RetrievalMode;
  retrieval_modes?: RetrievalModeOption[];
  best_retriever_method?: string;
  hybrid_available?: boolean;
}
