import {
  BadgeCheck,
  BookOpen,
  Check,
  Copy,
  MessageCircleQuestion,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  TriangleAlert,
} from 'lucide-react';
import { Fragment, useMemo, useState } from 'react';
import type { RagResponse } from '../types';
import SourceCard from './SourceCard';

interface AnswerPanelProps {
  response: RagResponse | null;
  loading: boolean;
  error: string | null;
  showScores: boolean;
}

function renderAnswer(answer: string) {
  const parts = answer.split(/(\[S\d+\])/g);
  return parts.map((part, index) => {
    if (/^\[S\d+\]$/.test(part)) {
      return <span className="inline-citation" key={`${part}-${index}`}>{part}</span>;
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}

export default function AnswerPanel({ response, loading, error, showScores }: AnswerPanelProps) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);

  const verified = useMemo(
    () =>
      Boolean(
        response &&
          !response.no_answer &&
          response.sources.length > 0 &&
          response.provider_alias !== 'mock' &&
          response.provider_alias !== 'mock_extractive',
      ),
    [response],
  );

  const generationError =
    typeof response?.diagnostics?.generation_error === 'string'
      ? response.diagnostics.generation_error
      : null;

  async function copyAnswer() {
    if (!response) return;
    await navigator.clipboard.writeText(response.answer);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  if (loading) {
    return (
      <section className="answer-card user-answer-card loading-card">
        <div className="loading-head" />
        <div className="loading-line wide" />
        <div className="loading-line" />
        <div className="loading-line short" />
        <div className="loading-source" />
        <div className="loading-source" />
      </section>
    );
  }

  if (error) {
    return (
      <section className="answer-card user-answer-card error-state">
        <div className="state-icon error-icon"><TriangleAlert size={30} /></div>
        <h2>ارتباط با سامانه برقرار نشد</h2>
        <p>{error}</p>
        <small>اتصال FastAPI و مقدار VITE_API_BASE_URL را بررسی کنید.</small>
      </section>
    );
  }

  if (!response) {
    return (
      <section className="answer-card user-answer-card empty-answer user-empty-answer">
        <div className="simple-empty-icon"><MessageCircleQuestion size={27} /></div>
        <h2>پاسخ اینجا نمایش داده می‌شود</h2>
        <p>پس از ارسال سؤال، پاسخ مستند و منابع مرتبط را در همین بخش می‌بینید.</p>
        <div className="empty-feature-row">
          <span><BadgeCheck size={15} /> فقط بر اساس اسناد</span>
          <span><BookOpen size={15} /> همراه با صفحه و ماده</span>
        </div>
      </section>
    );
  }

  return (
    <section className="answer-card user-answer-card">
      <div className="user-answer-heading">
        <div>
          <span className="answer-icon"><Sparkles size={18} /></span>
          <div>
            <span>پاسخ سامانه</span>
            <h2>{response.no_answer ? 'پاسخی در اسناد پیدا نشد' : 'پاسخ مستند'}</h2>
          </div>
        </div>
        <button type="button" onClick={copyAnswer} className="copy-answer-button">
          {copied ? <Check size={17} /> : <Copy size={17} />}
          {copied ? 'کپی شد' : 'کپی پاسخ'}
        </button>
      </div>

      <div className={`answer-text user-answer-text ${response.no_answer ? 'no-answer' : ''}`}>
        <p>{renderAnswer(response.answer)}</p>
      </div>

      {verified && (
        <div className="grounded-badge user-grounded-badge">
          <BadgeCheck size={19} />
          <span>این پاسخ با {response.sources.length.toLocaleString('fa-IR')} منبع دانشگاهی پشتیبانی شده است.</span>
        </div>
      )}

      {response.demo_mode && (
        <div className="demo-notice user-demo-notice">
          حالت نمایشی فعال است؛ پس از اتصال Backend، داده‌های واقعی جایگزین می‌شوند.
        </div>
      )}

      {(response.provider_alias === 'mock' ||
        response.provider_alias === 'mock_extractive') && (
        <div className="demo-notice user-demo-notice">
          این پاسخ با baseline استخراجی ساخته شده است، نه Gemini/OpenAI؛ آن را
          پاسخ نهایی هوشمند در نظر نگیرید.
        </div>
      )}

      {generationError && (
        <div className="generation-error-notice">
          تولید پاسخ توسط مدل واقعی ناموفق بود و سامانه برای جلوگیری از پاسخ
          ساختگی، پاسخ را متوقف کرد.
        </div>
      )}

      <div className="sources-section user-sources-section">
        <div className="sources-title user-sources-title">
          <div>
            <BookOpen size={20} />
            <div>
              <h3>منابع استفاده‌شده</h3>
              <span>برای مشاهده متن کامل هر منبع، کارت آن را باز کنید.</span>
            </div>
          </div>
          <span>{response.sources.length.toLocaleString('fa-IR')} منبع</span>
        </div>

        <div className="sources-list user-sources-list">
          {response.sources.map((source, index) => (
            <SourceCard key={source.source_id} source={source} showScore={showScores} index={index} />
          ))}
        </div>
      </div>

      <div className="answer-feedback-row user-feedback-row">
        <span>این پاسخ مفید بود؟</span>
        <div>
          <button type="button" className={feedback === 'up' ? 'is-selected' : ''} onClick={() => setFeedback('up')}><ThumbsUp size={16} /> بله</button>
          <button type="button" className={feedback === 'down' ? 'is-selected negative' : ''} onClick={() => setFeedback('down')}><ThumbsDown size={16} /> خیر</button>
        </div>
      </div>
    </section>
  );
}
