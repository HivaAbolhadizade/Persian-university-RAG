import { FileSearch, FileText, Filter, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { getDocuments } from '../api/client';
import type { DocumentItem } from '../types';

const extractionLabels = {
  direct: 'استخراج مستقیم',
  ocr: 'OCR',
  mixed: 'ترکیبی',
};

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');

  useEffect(() => {
    getDocuments().then(setDocuments).finally(() => setLoading(false));
  }, []);

  const categories = useMemo(
    () => Array.from(new Set(documents.map((item) => item.category))),
    [documents],
  );

  const filtered = useMemo(
    () =>
      documents.filter((item) => {
        const matchesSearch = item.title.includes(search.trim());
        const matchesCategory = !category || item.category === category;
        return matchesSearch && matchesCategory;
      }),
    [documents, search, category],
  );

  return (
    <div className="page secondary-page">
      <header className="section-header">
        <div>
          <span className="eyebrow">مدیریت داده</span>
          <h1>اسناد و منابع</h1>
          <p>مشاهده وضعیت پردازش، تعداد صفحات و تعداد چانک‌های هر سند.</p>
        </div>
        <div className="header-stat">
          <FileText size={25} />
          <strong>{documents.length.toLocaleString('fa-IR')}</strong>
          <span>سند</span>
        </div>
      </header>

      <section className="toolbar-card">
        <label className="search-field">
          <Search size={19} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="جست‌وجوی نام سند..."
          />
        </label>
        <label className="filter-field">
          <Filter size={18} />
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="">همه دسته‌ها</option>
            {categories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </section>

      {loading ? (
        <div className="documents-grid">
          {Array.from({ length: 6 }).map((_, index) => (
            <div className="document-card loading-card" key={index} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-panel">
          <FileSearch size={38} />
          <h2>سندی پیدا نشد</h2>
          <p>عبارت جست‌وجو یا فیلتر را تغییر دهید.</p>
        </div>
      ) : (
        <div className="documents-grid">
          {filtered.map((item) => (
            <article className="document-card" key={item.id}>
              <div className="document-topline">
                <div className="document-icon">
                  <FileText size={24} />
                </div>
                <span className={`document-status status-${item.status}`}>
                  {item.status === 'ready' ? 'آماده' : 'نیازمند بررسی'}
                </span>
              </div>
              <h2>{item.title}</h2>
              <span className="category-chip">{item.category}</span>
              <dl>
                <div>
                  <dt>صفحات</dt>
                  <dd>{item.pages.toLocaleString('fa-IR')}</dd>
                </div>
                <div>
                  <dt>چانک‌ها</dt>
                  <dd>{item.chunks.toLocaleString('fa-IR')}</dd>
                </div>
                <div>
                  <dt>استخراج</dt>
                  <dd>{extractionLabels[item.extraction]}</dd>
                </div>
              </dl>
              <small>بروزرسانی: {item.updatedAt}</small>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
