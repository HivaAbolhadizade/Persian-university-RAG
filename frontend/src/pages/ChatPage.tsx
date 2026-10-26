import {
  BookOpenText,
  Clock3,
  Cpu,
  Database,
  History,
  ShieldCheck,
  X,
} from 'lucide-react';
import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  getClientConfig,
  queryRag,
} from '../api/client';
import AnswerPanel from '../components/AnswerPanel';
import HistoryPanel from '../components/HistoryPanel';
import SearchPanel from '../components/SearchPanel';
import type {
  ClientConfig,
  HistoryItem,
  RagResponse,
  RetrievalMode,
  RetrievalModeOption,
} from '../types';
import {
  clearStoredHistory,
  loadHistory,
  loadSettings,
  saveHistory,
} from '../utils/storage';

export default function ChatPage() {
  const settings = useMemo(loadSettings, []);
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState<RagResponse | null>(null);
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>('hybrid');
  const [history, setHistory] = useState<HistoryItem[]>(loadHistory);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clientConfig, setClientConfig] =
    useState<ClientConfig | null>(null);

  const retrievalModes = useMemo<RetrievalModeOption[]>(() => {
    if (clientConfig?.retrieval_modes?.length) {
      return clientConfig.retrieval_modes;
    }

    return [
      {
        value: 'best',
        label: 'روش مبنا (BM25)',
        description: 'روش برتر مرحله بازیابی Notebook 02 برای مقایسه.',
        resolved_method: clientConfig?.best_retriever_method || 'bm25',
        available: true,
      },
      {
        value: 'hybrid',
        label: 'روش برتر ارزیابی نهایی',
        description:
          'Hybrid منتخب آزمون ۱۰۰ سؤالی با RRF، بازرتبه‌بندی و فیلتر ارتباط.',
        resolved_method:
          'hybrid_rrf:multilingual_e5_base+reranker+relevance_guard',
        available: Boolean(clientConfig?.hybrid_available),
      },
    ];
  }, [clientConfig]);

  const answerSectionRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getClientConfig()
      .then((config) => {
        setClientConfig(config);
        const defaultMode = config.default_retrieval_mode;
        const defaultOption = config.retrieval_modes?.find(
          (option) => option.value === defaultMode && option.available,
        );
        if (defaultOption) setRetrievalMode(defaultOption.value);
      })
      .catch(() => setClientConfig(null));
  }, []);

  useEffect(() => {
    const selectedOption = retrievalModes.find(
      (option) => option.value === retrievalMode,
    );
    if (selectedOption && !selectedOption.available) {
      setRetrievalMode('best');
    }
  }, [retrievalMode, retrievalModes]);

  useEffect(() => {
    if (!response || loading) return;

    const timer = window.setTimeout(() => {
      answerSectionRef.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
    }, 90);

    return () => window.clearTimeout(timer);
  }, [response, loading]);

  async function submitQuestion() {
    if (!question.trim() || loading) return;

    setLoading(true);
    setError(null);

    try {
      // Refresh the runtime LLM configuration immediately before every query.
      // This prevents an old page state from silently sending a request with
      // the Mock provider after the user has selected Gemini/OpenAI.
      const runtimeConfig = await getClientConfig();
      setClientConfig(runtimeConfig);
      const runtimeProvider =
        runtimeConfig.provider === 'gemini' ||
        runtimeConfig.provider === 'openai' ||
        runtimeConfig.provider === 'mock'
          ? runtimeConfig.provider
          : undefined;

      const result = await queryRag({
        question: question.trim(),
        top_k: settings.topK,
        category: settings.category || null,
        retrieval_mode: retrievalMode,
        provider: runtimeProvider,
        model: runtimeConfig.model || null,
      });
      setResponse(result);

      const item: HistoryItem = {
        id: crypto.randomUUID(),
        question: question.trim(),
        answer: result.answer,
        createdAt: new Date().toISOString(),
        response: result,
      };
      const nextHistory = [item, ...history].slice(0, 20);
      setHistory(nextHistory);
      saveHistory(nextHistory);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : 'خطای ناشناخته',
      );
    } finally {
      setLoading(false);
    }
  }

  function clearHistory() {
    setHistory([]);
    clearStoredHistory();
  }

  function selectHistory(item: HistoryItem) {
    setQuestion(item.question);
    setResponse(item.response);
    const savedMode = item.response.diagnostics?.requested_retrieval_mode;
    if (savedMode === 'best' || savedMode === 'hybrid') {
      setRetrievalMode(savedMode);
    }
    setError(null);
    setHistoryOpen(false);
  }

  const activeProvider =
    response?.provider_alias ||
    clientConfig?.active_provider ||
    clientConfig?.provider ||
    '—';

  const activeModel =
    response?.model ||
    clientConfig?.active_model ||
    clientConfig?.model ||
    'مدلی انتخاب نشده است';

  const mockIsActive = activeProvider === 'mock' || activeProvider === 'mock_extractive';

  return (
    <div className="page chat-page user-friendly-chat-page">
      <section
        className="university-welcome-banner"
        aria-labelledby="welcome-title"
      >
        <div className="university-welcome-copy">
          <div className="university-welcome-kicker">
            <span className="welcome-live-dot" />
            دستیار هوشمند اسناد دانشگاه شهید باهنر کرمان
          </div>

          <h1 id="welcome-title">
            پاسخ دقیق و مستند برای
            <span> پرسش‌های دانشگاهی</span>
          </h1>

          <p>
            سؤال خود را بپرسید؛ سامانه در آیین‌نامه‌ها و اسناد
            رسمی جست‌وجو می‌کند و پاسخ را همراه با صفحه، ماده و
            منبع ارائه می‌دهد.
          </p>

          <div
            className="university-domain-row"
            aria-label="حوزه‌های محتوایی سامانه"
          >
            <span className="domain-chip domain-education">
              آموزش
            </span>
            <span className="domain-chip domain-research">
              پژوهش
            </span>
            <span className="domain-chip domain-student">
              امور دانشجویی
            </span>
            <span className="domain-chip domain-regulations">
              آیین‌نامه‌ها
            </span>
          </div>

          <div className="active-model-banner" aria-live="polite">
            <Cpu size={18} />
            <span>مدل فعال:</span>
            <strong>{activeProvider}</strong>
            <i />
            <b dir="ltr">{activeModel}</b>
          </div>
        </div>

        <div className="university-welcome-visual" aria-hidden="true">
          <span className="identity-orbit identity-orbit-one" />
          <span className="identity-orbit identity-orbit-two" />
          <div className="identity-logo-card">
            <img src="/university-rag-mark.svg" alt="" />
          </div>
          <div className="identity-mini-card identity-mini-card-top">
            <strong>اسناد رسمی</strong>
            <span>پاسخ قابل ارجاع</span>
          </div>
          <div className="identity-mini-card identity-mini-card-bottom">
            <strong>RAG</strong>
            <span>بازیابی + تولید</span>
          </div>
        </div>

        <button
          type="button"
          className="history-open-button banner-history-button"
          onClick={() => setHistoryOpen(true)}
        >
          <History size={18} />
          تاریخچه
          {history.length > 0 && (
            <small>{history.length.toLocaleString('fa-IR')}</small>
          )}
        </button>
      </section>

      {mockIsActive && (
        <div className="runtime-provider-warning" role="status">
          <ShieldCheck size={18} />
          <span>
            حالت آزمایشی Mock فعال است. برای پاسخ طبیعی، از صفحه تنظیمات
            Gemini یا OpenAI را انتخاب، آزمایش و ذخیره کنید. پاسخ Mock فقط
            یک baseline استخراجی است.
          </span>
        </div>
      )}

      <SearchPanel
        question={question}
        loading={loading}
        retrievalMode={retrievalMode}
        retrievalModes={retrievalModes}
        onQuestionChange={setQuestion}
        onRetrievalModeChange={setRetrievalMode}
        onSubmit={submitQuestion}
        onClear={() => {
          setQuestion('');
          setResponse(null);
          setError(null);
        }}
      />

      <div
        ref={answerSectionRef}
        className="answer-scroll-target"
      >
        <AnswerPanel
          response={response}
          loading={loading}
          error={error}
          showScores={settings.showScores}
        />
      </div>

      {response && (
        <details className="technical-details-card">
          <summary>جزئیات فنی پاسخ</summary>
          <div className="technical-details-grid">
            <div>
              <ShieldCheck size={18} />
              <span>اعتماد پاسخ</span>
              <strong>
                {response.confidence != null
                  ? response.confidence.toFixed(2)
                  : '—'}
              </strong>
            </div>
            <div>
              <BookOpenText size={18} />
              <span>تعداد منابع</span>
              <strong>
                {response.sources.length.toLocaleString('fa-IR')}
              </strong>
            </div>
            <div>
              <Database size={18} />
              <span>روش بازیابی</span>
              <strong>{response.retriever_method || '—'}</strong>
            </div>
            <div>
              <Clock3 size={18} />
              <span>زمان پاسخ</span>
              <strong>
                {response.latency_seconds.toFixed(2)} ثانیه
              </strong>
            </div>
          </div>
        </details>
      )}

      <div
        className={`history-drawer-overlay ${
          historyOpen ? 'is-open' : ''
        }`}
        onClick={() => setHistoryOpen(false)}
      />
      <aside
        className={`history-drawer ${
          historyOpen ? 'is-open' : ''
        }`}
        aria-hidden={!historyOpen}
      >
        <button
          type="button"
          className="history-drawer-close"
          onClick={() => setHistoryOpen(false)}
          aria-label="بستن تاریخچه"
        >
          <X size={20} />
        </button>
        <HistoryPanel
          items={history}
          onSelect={selectHistory}
          onClear={clearHistory}
        />
      </aside>
    </div>
  );
}
