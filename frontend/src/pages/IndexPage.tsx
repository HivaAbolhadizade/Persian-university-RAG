import { CheckCircle2, Database, RefreshCw, SearchCheck } from 'lucide-react';
import { useState } from 'react';
import { rebuildIndex } from '../api/client';

export default function IndexPage() {
  const [building, setBuilding] = useState(false);
  const [message, setMessage] = useState('');

  async function handleRebuild() {
    setBuilding(true);
    setMessage('');
    try {
      const result = await rebuildIndex();
      setMessage(result.message);
    } finally {
      setBuilding(false);
    }
  }

  return (
    <div className="page secondary-page">
      <header className="section-header">
        <div>
          <span className="eyebrow">بازیابی و ایندکس</span>
          <h1>ساخت ایندکس</h1>
          <p>مدیریت BM25، بردارهای Embedding و ایندکس FAISS.</p>
        </div>
      </header>

      <div className="index-overview-grid">
        <article className="overview-card">
          <Database size={28} />
          <span>نوع ایندکس برداری</span>
          <strong>FAISS IndexFlatIP</strong>
        </article>
        <article className="overview-card">
          <SearchCheck size={28} />
          <span>روش بازیابی</span>
          <strong>Hybrid + Rerank</strong>
        </article>
        <article className="overview-card">
          <CheckCircle2 size={28} />
          <span>وضعیت</span>
          <strong className="green-text">آماده</strong>
        </article>
      </div>

      <section className="index-action-card">
        <div>
          <h2>بازسازی کامل ایندکس</h2>
          <p>
            بعد از اضافه شدن سند جدید، این عملیات Embeddingها و ایندکس‌های بازیابی را بروزرسانی می‌کند.
          </p>
        </div>
        <button className="primary-button" onClick={handleRebuild} disabled={building}>
          <RefreshCw size={19} className={building ? 'spin' : ''} />
          {building ? 'در حال بازسازی...' : 'بازسازی ایندکس'}
        </button>
      </section>

      {message && <div className="success-banner">{message}</div>}
    </div>
  );
}
