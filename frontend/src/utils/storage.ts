import type { FrontendSettings, HistoryItem } from '../types';

const HISTORY_KEY = 'university-rag-history-v1';
const SETTINGS_KEY = 'university-rag-settings-v1';

const defaultSettings: FrontendSettings = {
  topK: 5,
  category: '',
  showScores: true,
  autoOpenSources: true,
  mockFallback: false,
};

export function loadHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as HistoryItem[]) : [];
  } catch {
    return [];
  }
}

export function saveHistory(items: HistoryItem[]): void {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, 20)));
}

export function clearStoredHistory(): void {
  localStorage.removeItem(HISTORY_KEY);
}

export function loadSettings(): FrontendSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw
      ? { ...defaultSettings, ...(JSON.parse(raw) as FrontendSettings) }
      : defaultSettings;
  } catch {
    return defaultSettings;
  }
}

export function saveSettings(settings: FrontendSettings): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}
