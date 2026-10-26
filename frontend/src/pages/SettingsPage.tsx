import {
  AlertTriangle,
  CheckCircle2,
  CloudCog,
  Eye,
  EyeOff,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  Save,
  ServerCog,
  ShieldCheck,
  Sparkles,
  Trash2,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { FormEvent, useEffect, useMemo, useState } from 'react';
import {
  LLMSettingsApi,
  type LLMProvider,
  type LLMSettingsResponse,
  type ModelInfo,
} from '../api/llmSettings';
import { API_BASE_URL } from '../api/client';
import type { FrontendSettings } from '../types';
import { loadSettings, saveSettings } from '../utils/storage';

type ConnectionState = 'idle' | 'testing' | 'success' | 'error';

const providerMeta: Record<
  LLMProvider,
  { title: string; description: string; badge: string }
> = {
  gemini: {
    title: 'Gemini',
    description: 'مدل‌های Google Gemini API',
    badge: 'Google',
  },
  openai: {
    title: 'OpenAI',
    description: 'مدل‌های OpenAI API',
    badge: 'OpenAI',
  },
  mock: {
    title: 'Mock',
    description: 'حالت توسعه بدون API واقعی',
    badge: 'Development',
  },
};

export default function SettingsPage() {
  const [frontendSettings, setFrontendSettings] =
    useState<FrontendSettings>(loadSettings);

  const [serverSettings, setServerSettings] =
    useState<LLMSettingsResponse | null>(null);
  const [provider, setProvider] = useState<LLMProvider>('gemini');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [model, setModel] = useState('');
  const [rememberOnDevice, setRememberOnDevice] = useState(false);

  const [initialLoading, setInitialLoading] = useState(true);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [connectionState, setConnectionState] =
    useState<ConnectionState>('idle');
  const [connectionMessage, setConnectionMessage] = useState('');
  const [pageMessage, setPageMessage] = useState<{
    kind: 'success' | 'error' | 'info';
    text: string;
  } | null>(null);
  const [frontendSaved, setFrontendSaved] = useState(false);

  const selectedProviderStatus = useMemo(
    () =>
      serverSettings?.providers.find(
        (item) => item.provider === provider,
      ) ?? null,
    [provider, serverSettings],
  );

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setInitialLoading(true);
      try {
        const result = await LLMSettingsApi.get();
        if (cancelled) return;

        setServerSettings(result);
        setProvider(result.active_provider);
        const active = result.providers.find(
          (item) => item.provider === result.active_provider,
        );
        setModel(active?.model ?? '');
        setRememberOnDevice(active?.remembered_on_device ?? false);
      } catch (error) {
        if (cancelled) return;
        setPageMessage({
          kind: 'error',
          text:
            error instanceof Error
              ? error.message
              : 'دریافت تنظیمات Backend ناموفق بود.',
        });
      } finally {
        if (!cancelled) setInitialLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  function selectProvider(nextProvider: LLMProvider) {
    setProvider(nextProvider);
    const status = serverSettings?.providers.find(
      (item) => item.provider === nextProvider,
    );

    setApiKey('');
    setShowApiKey(false);
    setModels([]);
    setModel(status?.model ?? (nextProvider === 'mock' ? 'mock' : ''));
    setRememberOnDevice(status?.remembered_on_device ?? false);
    setConnectionState(nextProvider === 'mock' ? 'success' : 'idle');
    setConnectionMessage(
      nextProvider === 'mock'
        ? 'حالت Mock به اتصال خارجی نیاز ندارد.'
        : '',
    );
    setPageMessage(null);
  }

  function onSensitiveFieldChange(value: string) {
    setApiKey(value);
    if (provider !== 'mock') {
      setConnectionState('idle');
      setConnectionMessage('');
    }
  }

  function onModelChange(value: string) {
    setModel(value);
    if (provider !== 'mock') {
      setConnectionState('idle');
      setConnectionMessage('');
    }
  }

  async function loadModels() {
    if (provider === 'mock') return;

    if (!apiKey.trim() && !selectedProviderStatus?.configured) {
      setPageMessage({
        kind: 'error',
        text: 'ابتدا API Key را وارد کنید.',
      });
      return;
    }

    setModelsLoading(true);
    setPageMessage(null);
    setConnectionState('idle');

    try {
      const result = await LLMSettingsApi.listModels(
        provider,
        apiKey || undefined,
      );
      setModels(result.models);

      if (
        result.models.length > 0 &&
        !result.models.some((item) => item.id === model)
      ) {
        setModel(result.models[0].id);
      }

      setPageMessage({
        kind: 'success',
        text: `${result.models.length.toLocaleString(
          'fa-IR',
        )} مدل قابل‌دسترسی دریافت شد.`,
      });
    } catch (error) {
      setPageMessage({
        kind: 'error',
        text:
          error instanceof Error
            ? error.message
            : 'دریافت فهرست مدل‌ها ناموفق بود.',
      });
    } finally {
      setModelsLoading(false);
    }
  }

  async function testConnection() {
    if (provider === 'mock') {
      setConnectionState('success');
      setConnectionMessage('حالت Mock آماده است.');
      return;
    }

    if (!model) {
      setPageMessage({
        kind: 'error',
        text: 'ابتدا یک مدل را انتخاب کنید.',
      });
      return;
    }

    if (!apiKey.trim() && !selectedProviderStatus?.configured) {
      setPageMessage({
        kind: 'error',
        text: 'برای آزمایش اتصال، API Key را وارد کنید.',
      });
      return;
    }

    setConnectionState('testing');
    setConnectionMessage('در حال آزمایش اتصال...');
    setPageMessage(null);

    try {
      const result = await LLMSettingsApi.testConnection(
        provider,
        model,
        apiKey || undefined,
      );

      setConnectionState(result.ok ? 'success' : 'error');
      setConnectionMessage(
        result.ok
          ? `${result.message} — ${result.latency_seconds.toFixed(2)} ثانیه`
          : result.message,
      );
    } catch (error) {
      setConnectionState('error');
      setConnectionMessage(
        error instanceof Error
          ? error.message
          : 'آزمایش اتصال ناموفق بود.',
      );
    }
  }

  async function saveLlmSettings(event: FormEvent) {
    event.preventDefault();

    if (
      provider !== 'mock' &&
      connectionState !== 'success'
    ) {
      setPageMessage({
        kind: 'error',
        text: 'قبل از ذخیره، اتصال مدل را با موفقیت آزمایش کنید.',
      });
      return;
    }

    if (provider !== 'mock' && !model) {
      setPageMessage({
        kind: 'error',
        text: 'مدل فعال را انتخاب کنید.',
      });
      return;
    }

    setSaving(true);
    setPageMessage(null);

    try {
      const result = await LLMSettingsApi.save({
        provider,
        model: provider === 'mock' ? 'mock' : model,
        apiKey: apiKey || undefined,
        rememberOnDevice,
      });

      setServerSettings(result);
      setApiKey('');
      setShowApiKey(false);
      setPageMessage({
        kind: 'success',
        text: 'تنظیمات مدل با موفقیت ذخیره شد.',
      });
    } catch (error) {
      setPageMessage({
        kind: 'error',
        text:
          error instanceof Error
            ? error.message
            : 'ذخیره تنظیمات مدل ناموفق بود.',
      });
    } finally {
      setSaving(false);
    }
  }

  async function deleteCurrentKey() {
    if (provider === 'mock') {
      setPageMessage({
        kind: 'info',
        text: 'حالت Mock کلید API ندارد.',
      });
      return;
    }

    setDeleting(true);
    setPageMessage(null);

    try {
      const result = await LLMSettingsApi.delete(provider);
      setServerSettings(result);
      setApiKey('');
      setModels([]);
      setModel('');
      setRememberOnDevice(false);
      setConnectionState('idle');
      setConnectionMessage('');
      setPageMessage({
        kind: 'success',
        text: `کلید ${providerMeta[provider].title} حذف شد.`,
      });
    } catch (error) {
      setPageMessage({
        kind: 'error',
        text:
          error instanceof Error
            ? error.message
            : 'حذف کلید ناموفق بود.',
      });
    } finally {
      setDeleting(false);
    }
  }

  async function deleteAllKeys() {
    setDeleting(true);
    setPageMessage(null);

    try {
      const result = await LLMSettingsApi.delete();
      setServerSettings(result);
      setApiKey('');
      setModels([]);
      setModel(provider === 'mock' ? 'mock' : '');
      setRememberOnDevice(false);
      setConnectionState(provider === 'mock' ? 'success' : 'idle');
      setConnectionMessage('');
      setPageMessage({
        kind: 'success',
        text: 'تمام کلیدهای ذخیره‌شده حذف شدند.',
      });
    } catch (error) {
      setPageMessage({
        kind: 'error',
        text:
          error instanceof Error
            ? error.message
            : 'حذف کلیدها ناموفق بود.',
      });
    } finally {
      setDeleting(false);
    }
  }

  function saveFrontendConfiguration(event: FormEvent) {
    event.preventDefault();
    saveSettings(frontendSettings);
    setFrontendSaved(true);
    window.setTimeout(() => setFrontendSaved(false), 1600);
  }

  const saveEnabled =
    provider === 'mock' || connectionState === 'success';

  return (
    <div className="page secondary-page llm-settings-page">
      <header className="section-header llm-settings-header">
        <div>
          <span className="eyebrow">اتصال امن مدل زبانی</span>
          <h1>تنظیمات مدل و API</h1>
          <p>
            Provider، مدل و نحوه نگه‌داری امن کلید را برای همین
            Backend محلی انتخاب کنید.
          </p>
        </div>

        <div className="active-llm-summary">
          <span
            className={`settings-status-chip ${
              selectedProviderStatus?.configured
                ? 'is-connected'
                : 'is-disconnected'
            }`}
          >
            {selectedProviderStatus?.configured ? (
              <Wifi size={16} />
            ) : (
              <WifiOff size={16} />
            )}
            {selectedProviderStatus?.configured
              ? 'پیکربندی‌شده'
              : 'پیکربندی‌نشده'}
          </span>
          <small>Provider فعال</small>
          <strong>
            {serverSettings
              ? providerMeta[serverSettings.active_provider].title
              : '—'}
          </strong>
          <span>
            {serverSettings?.providers.find((item) => item.selected)
              ?.model ?? 'مدلی انتخاب نشده است'}
          </span>
        </div>
      </header>

      {pageMessage && (
        <div
          className={`settings-message is-${pageMessage.kind}`}
          role="status"
        >
          {pageMessage.kind === 'success' ? (
            <CheckCircle2 size={19} />
          ) : pageMessage.kind === 'error' ? (
            <AlertTriangle size={19} />
          ) : (
            <Sparkles size={19} />
          )}
          <span>{pageMessage.text}</span>
        </div>
      )}

      <section className="settings-security-note">
        <ShieldCheck size={24} />
        <div>
          <strong>کلید API در فرانت ذخیره نمی‌شود</strong>
          <p>
            کلید API داخل مرورگر، LocalStorage یا Cookie ذخیره
            نمی‌شود. در حالت موقت فقط در حافظه Backend محلی
            نگه‌داری می‌شود. با فعال‌کردن «به خاطر سپردن»، کلید
            در Windows Credential Manager ذخیره خواهد شد. کلید
            کامل پس از ذخیره دوباره نمایش داده نمی‌شود.
          </p>
          <small>
            اشتراک ChatGPT یا Gemini App به‌تنهایی اعتبار API
            محسوب نمی‌شود و هزینه API ممکن است جداگانه محاسبه
            شود.
          </small>
        </div>
      </section>

      <form
        className="llm-settings-card"
        onSubmit={saveLlmSettings}
      >
        <div className="settings-card-title">
          <CloudCog size={24} />
          <div>
            <h2>مدل تولید پاسخ</h2>
            <p>جریان: انتخاب Provider ← مدل ← تست ← ذخیره</p>
          </div>
        </div>

        {initialLoading ? (
          <div className="settings-loading-state">
            <LoaderCircle className="spin" size={25} />
            دریافت وضعیت فعلی...
          </div>
        ) : (
          <>
            <fieldset className="provider-selector">
              <legend>۱. Provider را انتخاب کنید</legend>
              <div className="provider-options">
                {(Object.keys(providerMeta) as LLMProvider[]).map(
                  (item) => {
                    const status = serverSettings?.providers.find(
                      (providerStatus) =>
                        providerStatus.provider === item,
                    );

                    return (
                      <button
                        key={item}
                        type="button"
                        className={`provider-option ${
                          provider === item ? 'is-selected' : ''
                        }`}
                        onClick={() => selectProvider(item)}
                      >
                        <span className="provider-option-icon">
                          {item === 'mock' ? (
                            <ServerCog size={22} />
                          ) : (
                            <Sparkles size={22} />
                          )}
                        </span>
                        <span>
                          <strong>{providerMeta[item].title}</strong>
                          <small>
                            {providerMeta[item].description}
                          </small>
                        </span>
                        <em>{providerMeta[item].badge}</em>
                        {status?.configured && (
                          <CheckCircle2
                            className="provider-configured-icon"
                            size={18}
                          />
                        )}
                      </button>
                    );
                  },
                )}
              </div>
            </fieldset>

            {provider !== 'mock' && (
              <div className="llm-form-grid">
                <label className="llm-field llm-key-field">
                  <span>۲. API Key</span>
                  <div className="password-input-wrapper">
                    <KeyRound size={18} />
                    <input
                      value={apiKey}
                      onChange={(event) =>
                        onSensitiveFieldChange(event.target.value)
                      }
                      type={showApiKey ? 'text' : 'password'}
                      autoComplete="off"
                      spellCheck={false}
                      placeholder={
                        selectedProviderStatus?.configured
                          ? 'برای حفظ کلید قبلی خالی بگذارید'
                          : 'کلید API را وارد کنید'
                      }
                      dir="ltr"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setShowApiKey((current) => !current)
                      }
                      aria-label={
                        showApiKey
                          ? 'پنهان‌کردن کلید'
                          : 'نمایش کلید'
                      }
                    >
                      {showApiKey ? (
                        <EyeOff size={19} />
                      ) : (
                        <Eye size={19} />
                      )}
                    </button>
                  </div>

                  {selectedProviderStatus?.key_preview && (
                    <small className="key-preview">
                      کلید ذخیره‌شده:
                      <code dir="ltr">
                        {selectedProviderStatus.key_preview}
                      </code>
                    </small>
                  )}
                </label>

                <div className="llm-field model-fetch-field">
                  <span>۳. مدل‌های قابل‌دسترسی</span>
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void loadModels()}
                    disabled={modelsLoading}
                  >
                    {modelsLoading ? (
                      <LoaderCircle className="spin" size={18} />
                    ) : (
                      <RefreshCw size={18} />
                    )}
                    دریافت مدل‌ها
                  </button>
                  <small>
                    در صورت خالی‌بودن فیلد Key، از کلید ذخیره‌شده
                    استفاده می‌شود.
                  </small>
                </div>

                <label className="llm-field">
                  <span>۴. مدل فعال</span>
                  <select
                    value={model}
                    onChange={(event) =>
                      onModelChange(event.target.value)
                    }
                    disabled={
                      models.length === 0 &&
                      !selectedProviderStatus?.model
                    }
                  >
                    <option value="">مدل را انتخاب کنید</option>
                    {selectedProviderStatus?.model &&
                      !models.some(
                        (item) =>
                          item.id === selectedProviderStatus.model,
                      ) && (
                        <option value={selectedProviderStatus.model}>
                          {selectedProviderStatus.model}
                        </option>
                      )}
                    {models.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.display_name || item.id}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="llm-field connection-test-field">
                  <span>۵. آزمایش اتصال</span>
                  <button
                    className="secondary-button test-connection-button"
                    type="button"
                    onClick={() => void testConnection()}
                    disabled={
                      connectionState === 'testing' || !model
                    }
                  >
                    {connectionState === 'testing' ? (
                      <LoaderCircle className="spin" size={18} />
                    ) : (
                      <Wifi size={18} />
                    )}
                    آزمایش اتصال
                  </button>
                </div>
              </div>
            )}

            {provider === 'mock' && (
              <div className="mock-provider-note">
                <ServerCog size={23} />
                <div>
                  <strong>حالت توسعه فعال است</strong>
                  <span>
                    این حالت بدون API Key اجرا می‌شود و برای تست
                    رابط مناسب است.
                  </span>
                </div>
              </div>
            )}

            <div
              className={`connection-result is-${connectionState}`}
              aria-live="polite"
            >
              {connectionState === 'testing' ? (
                <LoaderCircle className="spin" size={19} />
              ) : connectionState === 'success' ? (
                <CheckCircle2 size={19} />
              ) : connectionState === 'error' ? (
                <AlertTriangle size={19} />
              ) : (
                <Wifi size={19} />
              )}
              <div>
                <strong>
                  {connectionState === 'success'
                    ? 'اتصال آماده است'
                    : connectionState === 'error'
                      ? 'اتصال ناموفق'
                      : connectionState === 'testing'
                        ? 'در حال بررسی'
                        : 'هنوز آزمایش نشده'}
                </strong>
                <span>
                  {connectionMessage ||
                    'بعد از انتخاب مدل، اتصال را آزمایش کنید.'}
                </span>
              </div>
            </div>

            <label className="remember-device-row">
              <input
                type="checkbox"
                checked={rememberOnDevice}
                onChange={(event) =>
                  setRememberOnDevice(event.target.checked)
                }
                disabled={provider === 'mock'}
              />
              <span>
                <strong>روی این دستگاه به خاطر سپرده شود</strong>
                <small>
                  در Windows Credential Manager ذخیره می‌شود.
                </small>
              </span>
            </label>

            <div className="llm-settings-actions">
              <button
                className="primary-button"
                type="submit"
                disabled={!saveEnabled || saving}
              >
                {saving ? (
                  <LoaderCircle className="spin" size={19} />
                ) : (
                  <Save size={19} />
                )}
                ذخیره تنظیمات
              </button>

              <button
                className="danger-outline-button"
                type="button"
                onClick={() => void deleteCurrentKey()}
                disabled={
                  deleting ||
                  provider === 'mock' ||
                  !selectedProviderStatus?.configured
                }
              >
                <Trash2 size={18} />
                حذف کلید این Provider
              </button>

              <button
                className="text-danger-button"
                type="button"
                onClick={() => void deleteAllKeys()}
                disabled={deleting}
              >
                حذف همه کلیدها
              </button>
            </div>
          </>
        )}
      </form>

      <form
        className="settings-card frontend-preferences-card"
        onSubmit={saveFrontendConfiguration}
      >
        <div className="settings-card-title">
          <ServerCog size={23} />
          <div>
            <h2>تنظیمات رابط و Retrieval</h2>
            <p>این موارد محرمانه نیستند و فقط در مرورگر ذخیره می‌شوند.</p>
          </div>
        </div>

        <label>
          <span>آدرس Backend</span>
          <input value={API_BASE_URL} readOnly dir="ltr" />
          <small>از فایل frontend/.env خوانده می‌شود.</small>
        </label>

        <label>
          <span>تعداد منابع Top-k</span>
          <input
            type="number"
            min={1}
            max={20}
            value={frontendSettings.topK}
            onChange={(event) =>
              setFrontendSettings((current) => ({
                ...current,
                topK: Number(event.target.value),
              }))
            }
          />
        </label>

        <label>
          <span>فیلتر پیش‌فرض دسته</span>
          <select
            value={frontendSettings.category}
            onChange={(event) =>
              setFrontendSettings((current) => ({
                ...current,
                category: event.target.value,
              }))
            }
          >
            <option value="">بدون فیلتر</option>
            <option value="regulations">مقررات آموزشی</option>
            <option value="undergraduate">کارشناسی</option>
            <option value="master_phd">کارشناسی ارشد</option>
            <option value="transfer">مهمانی و انتقال</option>
            <option value="tuition">شهریه</option>
            <option value="exams">امتحانات</option>
          </select>
        </label>

        <label className="switch-row">
          <span>
            نمایش امتیاز شباهت
            <small>
              امتیاز Retrieval کنار هر منبع نمایش داده شود.
            </small>
          </span>
          <input
            type="checkbox"
            checked={frontendSettings.showScores}
            onChange={(event) =>
              setFrontendSettings((current) => ({
                ...current,
                showScores: event.target.checked,
              }))
            }
          />
        </label>

        <button className="secondary-button" type="submit">
          <Save size={19} />
          {frontendSaved
            ? 'تنظیمات رابط ذخیره شد'
            : 'ذخیره تنظیمات رابط'}
        </button>
      </form>
    </div>
  );
}
