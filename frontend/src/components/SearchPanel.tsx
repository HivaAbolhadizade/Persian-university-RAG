import {
  Database,
  Eraser,
  GitMerge,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from 'react';
import { suggestQuestions } from '../api/client';
import { sampleQuestions } from '../mocks/data';
import type {
  QuestionSuggestion,
  RetrievalMode,
  RetrievalModeOption,
} from '../types';

interface SearchPanelProps {
  question: string;
  loading: boolean;
  retrievalMode: RetrievalMode;
  retrievalModes: RetrievalModeOption[];
  onQuestionChange: (value: string) => void;
  onRetrievalModeChange: (value: RetrievalMode) => void;
  onSubmit: () => void;
  onClear: () => void;
}

const quickQuestions = sampleQuestions.slice(0, 4);

function difficultyLabel(value?: string | null) {
  if (value === 'easy') return 'آسان';
  if (value === 'medium') return 'متوسط';
  if (value === 'hard') return 'سخت';
  return null;
}

export default function SearchPanel({
  question,
  loading,
  retrievalMode,
  retrievalModes,
  onQuestionChange,
  onRetrievalModeChange,
  onSubmit,
  onClear,
}: SearchPanelProps) {
  const [focused, setFocused] = useState(false);
  const [suggestions, setSuggestions] = useState<QuestionSuggestion[]>([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState(-1);
  const requestSerialRef = useRef(0);
  const lastSelectedQuestionRef = useRef<string | null>(null);
  const blurTimerRef = useRef<number | null>(null);

  useEffect(() => {
    const normalized = question.trim();

    if (
      loading ||
      normalized.length < 2 ||
      normalized === lastSelectedQuestionRef.current
    ) {
      requestSerialRef.current += 1;
      setSuggestions([]);
      setSuggestionsOpen(false);
      setSuggestionsLoading(false);
      setActiveSuggestion(-1);
      return;
    }

    const requestSerial = ++requestSerialRef.current;
    const timer = window.setTimeout(async () => {
      setSuggestionsLoading(true);
      try {
        const result = await suggestQuestions(normalized, 5);
        if (requestSerial !== requestSerialRef.current) return;
        setSuggestions(result.suggestions);
        setSuggestionsOpen(focused && result.suggestions.length > 0);
        setActiveSuggestion(-1);
      } catch {
        if (requestSerial !== requestSerialRef.current) return;
        setSuggestions([]);
        setSuggestionsOpen(false);
      } finally {
        if (requestSerial === requestSerialRef.current) {
          setSuggestionsLoading(false);
        }
      }
    }, 230);

    return () => window.clearTimeout(timer);
  }, [question, loading, focused]);

  useEffect(() => {
    return () => {
      if (blurTimerRef.current != null) {
        window.clearTimeout(blurTimerRef.current);
      }
    };
  }, []);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSuggestionsOpen(false);
    onSubmit();
  }

  function selectSuggestion(item: QuestionSuggestion) {
    lastSelectedQuestionRef.current = item.question;
    onQuestionChange(item.question);
    setSuggestions([]);
    setSuggestionsOpen(false);
    setActiveSuggestion(-1);
  }

  function handleQuestionChange(value: string) {
    if (value !== lastSelectedQuestionRef.current) {
      lastSelectedQuestionRef.current = null;
    }
    onQuestionChange(value);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      setSuggestionsOpen(false);
      onSubmit();
      return;
    }

    if (!suggestionsOpen || suggestions.length === 0) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveSuggestion((current) =>
        current >= suggestions.length - 1 ? 0 : current + 1,
      );
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveSuggestion((current) =>
        current <= 0 ? suggestions.length - 1 : current - 1,
      );
    } else if (event.key === 'Enter' && activeSuggestion >= 0) {
      event.preventDefault();
      selectSuggestion(suggestions[activeSuggestion]);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      setSuggestionsOpen(false);
      setActiveSuggestion(-1);
    }
  }

  function handleFocus() {
    if (blurTimerRef.current != null) {
      window.clearTimeout(blurTimerRef.current);
      blurTimerRef.current = null;
    }
    setFocused(true);
    if (suggestions.length > 0) setSuggestionsOpen(true);
  }

  function handleBlur() {
    setFocused(false);
    blurTimerRef.current = window.setTimeout(() => {
      setSuggestionsOpen(false);
      setActiveSuggestion(-1);
    }, 140);
  }

  function clearQuestion() {
    lastSelectedQuestionRef.current = null;
    setSuggestions([]);
    setSuggestionsOpen(false);
    setActiveSuggestion(-1);
    onClear();
  }

  return (
    <section className={`query-card user-query-card ${focused ? 'is-focused' : ''}`}>
      <div className="user-query-heading">
        <div>
          <h2>سؤال خود را بپرسید</h2>
          <p>پاسخ فقط بر اساس اسناد رسمی دانشگاه و همراه با منبع ارائه می‌شود.</p>
        </div>
        <span><ShieldCheck size={16} /> پاسخ مستند</span>
      </div>

      <div className="retrieval-mode-selector" aria-label="انتخاب روش بازیابی">
        <div className="retrieval-mode-selector-heading">
          <div>
            <strong>روش بازیابی</strong>
            <span>می‌توانید روش نهایی Hybrid را با BM25 مبنا مقایسه کنید.</span>
          </div>
          <small>انتخاب برای همین سؤال</small>
        </div>

        <div className="retrieval-mode-options" role="radiogroup">
          {retrievalModes.map((option) => {
            const selected = option.value === retrievalMode;
            const Icon = option.value === 'hybrid' ? GitMerge : Database;

            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={selected}
                className={`retrieval-mode-option ${selected ? 'is-selected' : ''}`}
                disabled={loading || !option.available}
                onClick={() => onRetrievalModeChange(option.value)}
                title={!option.available ? 'فایل‌های Embedding و FAISS در دسترس نیستند.' : option.description}
              >
                <span className="retrieval-mode-option-icon"><Icon size={18} /></span>
                <span className="retrieval-mode-option-copy">
                  <span className="retrieval-mode-option-title">
                    <strong>{option.label}</strong>
                    {option.value === 'hybrid' && <em>منتخب نهایی</em>}
                    {!option.available && <em className="is-unavailable">غیرفعال</em>}
                  </span>
                  <small>{option.description}</small>
                  <span className="retrieval-mode-resolved">
                    روش اجرایی: <b dir="ltr">{option.resolved_method}</b>
                  </span>
                </span>
                <span className="retrieval-mode-radio" aria-hidden="true" />
              </button>
            );
          })}
        </div>
      </div>

      <form className="user-query-form" onSubmit={handleSubmit}>
        <div className="query-autocomplete-shell">
          <textarea
            value={question}
            onChange={(event) => handleQuestionChange(event.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={handleFocus}
            onBlur={handleBlur}
            placeholder="مثلاً: شرایط مهمانی دانشجو چیست؟"
            aria-label="سؤال کاربر"
            aria-autocomplete="list"
            aria-expanded={suggestionsOpen}
            aria-controls="question-suggestion-list"
            aria-activedescendant={
              activeSuggestion >= 0
                ? `question-suggestion-${suggestions[activeSuggestion]?.id}`
                : undefined
            }
            disabled={loading}
            rows={3}
          />

          {suggestionsLoading && question.trim().length >= 2 && (
            <div className="question-suggestion-loading" aria-live="polite">
              <span className="button-spinner" />
              در حال یافتن سؤال‌های مشابه…
            </div>
          )}

          {suggestionsOpen && suggestions.length > 0 && (
            <div
              id="question-suggestion-list"
              className="question-suggestion-list"
              role="listbox"
              aria-label="سؤال‌های پیشنهادی"
            >
              <div className="question-suggestion-heading">
                <span><Search size={15} /> پرسش‌های مرتبط</span>
                <small>از مجموعه ۱۰۰ سؤال تأییدشده</small>
              </div>
              {suggestions.map((item, index) => {
                const difficulty = difficultyLabel(item.difficulty);
                return (
                  <button
                    key={item.id}
                    id={`question-suggestion-${item.id}`}
                    type="button"
                    role="option"
                    aria-selected={index === activeSuggestion}
                    className={index === activeSuggestion ? 'is-active' : ''}
                    onMouseDown={(event) => event.preventDefault()}
                    onMouseEnter={() => setActiveSuggestion(index)}
                    onClick={() => selectSuggestion(item)}
                  >
                    <span className="question-suggestion-index">
                      {item.id.toLocaleString('fa-IR')}
                    </span>
                    <span className="question-suggestion-copy">
                      <strong>{item.question}</strong>
                      <small>
                        {item.source || 'منبع آیین‌نامه‌ای'}
                        {difficulty ? ` • ${difficulty}` : ''}
                      </small>
                    </span>
                  </button>
                );
              })}
              <div className="question-suggestion-keyboard-hint">
                با کلیدهای ↑ و ↓ انتخاب کنید و Enter بزنید.
              </div>
            </div>
          )}
        </div>

        <div className="user-query-footer">
          <span className="query-hint">برای ارسال سریع، Ctrl + Enter را بزنید.</span>
          <div className="query-footer-actions">
            <button type="button" className="clear-button" onClick={clearQuestion} disabled={!question && !loading}>
              <Eraser size={16} />
              پاک کردن
            </button>
            <button className="send-button" disabled={loading || !question.trim()}>
              {loading ? <span className="button-spinner" /> : <Send size={18} />}
              <span>{loading ? 'در حال بررسی...' : 'ارسال سؤال'}</span>
            </button>
          </div>
        </div>
      </form>

      <div className="quick-questions-row">
        <span><Sparkles size={15} /> نمونه سؤال:</span>
        <div>
          {quickQuestions.map((item) => (
            <button key={item} type="button" onClick={() => handleQuestionChange(item)}>
              {item}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
