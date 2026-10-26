import { API_BASE_URL } from './client';

export type LLMProvider = 'mock' | 'openai' | 'gemini';

export interface ProviderStatus {
  provider: LLMProvider;
  configured: boolean;
  selected: boolean;
  model: string | null;
  key_preview: string | null;
  remembered_on_device: boolean;
}

export interface LLMSettingsResponse {
  active_provider: LLMProvider;
  providers: ProviderStatus[];
  session_storage: string;
  persistent_storage: string;
  key_is_returned_to_frontend: false;
}

export interface ModelInfo {
  id: string;
  display_name: string;
  provider: 'openai' | 'gemini';
}

export interface ConnectionTestResponse {
  ok: boolean;
  provider: string;
  model: string;
  latency_seconds: number;
  message: string;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(
      payload?.detail ||
        payload?.message ||
        `خطای ارتباط با سرور (HTTP ${response.status})`,
    );
  }

  return response.json() as Promise<T>;
}

export const LLMSettingsApi = {
  get(): Promise<LLMSettingsResponse> {
    return apiFetch('/api/settings/llm');
  },

  listModels(provider: 'openai' | 'gemini', apiKey?: string) {
    return apiFetch<{ provider: string; models: ModelInfo[] }>(
      '/api/settings/llm/models',
      {
        method: 'POST',
        body: JSON.stringify({
          provider,
          api_key: apiKey?.trim() || null,
        }),
      },
    );
  },

  testConnection(
    provider: 'openai' | 'gemini',
    model: string,
    apiKey?: string,
  ): Promise<ConnectionTestResponse> {
    return apiFetch('/api/settings/llm/test', {
      method: 'POST',
      body: JSON.stringify({
        provider,
        model,
        api_key: apiKey?.trim() || null,
      }),
    });
  },

  save(payload: {
    provider: LLMProvider;
    model?: string;
    apiKey?: string;
    rememberOnDevice: boolean;
  }): Promise<LLMSettingsResponse> {
    return apiFetch('/api/settings/llm', {
      method: 'PUT',
      body: JSON.stringify({
        provider: payload.provider,
        model: payload.model || null,
        api_key: payload.apiKey?.trim() || null,
        remember_on_device: payload.rememberOnDevice,
      }),
    });
  },

  delete(provider?: 'openai' | 'gemini'): Promise<LLMSettingsResponse> {
    const suffix = provider ? `?provider=${provider}` : '';
    return apiFetch(`/api/settings/llm${suffix}`, {
      method: 'DELETE',
    });
  },
};
