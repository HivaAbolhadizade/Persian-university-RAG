import type {
  ClientConfig,
  DocumentItem,
  QueryRequest,
  QuestionSuggestionsResponse,
  RagResponse,
  SystemHealth,
} from '../types';
import { mockDocuments, mockHealth, mockResponse } from '../mocks/data';

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
).replace(/\/$/, '');

const MOCK_FALLBACK =
  String(import.meta.env.VITE_USE_MOCK_FALLBACK ?? 'false').toLowerCase() ===
  'true';

async function request<T>(
  path: string,
  options?: RequestInit,
  timeoutMs = 30000,
): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(options?.headers || {}),
      },
      signal: controller.signal,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail =
        payload?.detail ||
        payload?.message ||
        `خطای ارتباط با سرور (HTTP ${response.status})`;
      throw new Error(detail);
    }

    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
  }
}

function delayed<T>(value: T, ms = 650): Promise<T> {
  return new Promise((resolve) => window.setTimeout(() => resolve(value), ms));
}

export async function queryRag(payload: QueryRequest): Promise<RagResponse> {
  try {
    return await request<RagResponse>(
      '/api/query',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      90000,
    );
  } catch (error) {
    if (!MOCK_FALLBACK) throw error;

    return delayed(
      {
        ...mockResponse,
        question: payload.question,
        retriever_method:
          payload.retrieval_mode === 'hybrid'
            ? 'hybrid_rrf:multilingual_e5_base'
            : 'bm25',
        diagnostics: {
          requested_retrieval_mode: payload.retrieval_mode || 'best',
          resolved_retriever_method:
            payload.retrieval_mode === 'hybrid'
              ? 'hybrid_rrf:multilingual_e5_base'
              : 'bm25',
        },
        demo_mode: true,
      },
      1200,
    );
  }
}

export async function getSystemHealth(): Promise<SystemHealth> {
  try {
    return await request<SystemHealth>('/api/health');
  } catch (error) {
    if (!MOCK_FALLBACK) throw error;
    return delayed(mockHealth, 250);
  }
}

export async function getClientConfig(): Promise<ClientConfig> {
  return request<ClientConfig>('/api/config/client');
}

export async function suggestQuestions(
  query: string,
  limit = 5,
): Promise<QuestionSuggestionsResponse> {
  const normalized = query.trim();
  if (normalized.length < 2) {
    return { query: normalized, count: 0, suggestions: [] };
  }

  const params = new URLSearchParams({
    q: normalized,
    limit: String(Math.max(1, Math.min(limit, 10))),
  });
  return request<QuestionSuggestionsResponse>(
    `/api/questions/suggest?${params.toString()}`,
    undefined,
    10000,
  );
}

export async function getDocuments(): Promise<DocumentItem[]> {
  try {
    return await request<DocumentItem[]>('/api/documents');
  } catch (error) {
    if (!MOCK_FALLBACK) throw error;
    return delayed(mockDocuments, 350);
  }
}

export async function uploadDocument(file: File): Promise<{ message: string }> {
  const controller = new AbortController();
  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
      signal: controller.signal,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(
        payload?.detail ||
          payload?.message ||
          `خطای آپلود فایل (HTTP ${response.status})`,
      );
    }

    return (await response.json()) as { message: string };
  } catch (error) {
    if (!MOCK_FALLBACK) throw error;
    return delayed({ message: `${file.name} در حالت نمایشی دریافت شد.` }, 900);
  }
}

export async function rebuildIndex(): Promise<{ message: string }> {
  try {
    return await request<{ message: string }>(
      '/api/index/rebuild',
      { method: 'POST' },
      120000,
    );
  } catch (error) {
    if (!MOCK_FALLBACK) throw error;
    return delayed({ message: 'بازسازی ایندکس در حالت نمایشی انجام شد.' }, 1600);
  }
}

export { API_BASE_URL };
