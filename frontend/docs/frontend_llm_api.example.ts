const API_BASE =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

type Provider = 'mock' | 'openai' | 'gemini';

export interface ProviderStatus {
  provider: Provider;
  configured: boolean;
  selected: boolean;
  model: string | null;
  key_preview: string | null;
  remembered_on_device: boolean;
}

export interface LLMSettingsResponse {
  active_provider: Provider;
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

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `HTTP ${response.status}`);
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
        body: JSON.stringify({ provider, api_key: apiKey || null }),
      },
    );
  },

  testConnection(
    provider: 'openai' | 'gemini',
    model: string,
    apiKey?: string,
  ) {
    return apiFetch<{
      ok: boolean;
      provider: string;
      model: string;
      latency_seconds: number;
      message: string;
    }>('/api/settings/llm/test', {
      method: 'POST',
      body: JSON.stringify({
        provider,
        model,
        api_key: apiKey || null,
      }),
    });
  },

  save(payload: {
    provider: Provider;
    model?: string;
    apiKey?: string;
    rememberOnDevice: boolean;
  }): Promise<LLMSettingsResponse> {
    return apiFetch('/api/settings/llm', {
      method: 'PUT',
      body: JSON.stringify({
        provider: payload.provider,
        model: payload.model || null,
        api_key: payload.apiKey || null,
        remember_on_device: payload.rememberOnDevice,
      }),
    });
  },

  delete(provider?: 'openai' | 'gemini'): Promise<LLMSettingsResponse> {
    const suffix = provider ? `?provider=${provider}` : '';
    return apiFetch(`/api/settings/llm${suffix}`, { method: 'DELETE' });
  },
};
