import { BrainCircuit, Database, FileStack, GraduationCap, Network } from 'lucide-react';

export default function AboutPage() {
  return (
    <div className="page secondary-page">
      <header className="about-hero">
        <img src="/university-rag-mark.svg" alt="نشان پروژه University RAG" />
        <div>
          <span className="eyebrow">پروژه درس پردازش زبان طبیعی</span>
          <h1>سامانه پرسش و پاسخ مستند دانشگاه</h1>
          <p>
            این سامانه با استفاده از Retrieval-Augmented Generation، اسناد رسمی دانشگاه را جست‌وجو کرده و پاسخ همراه با منبع و شماره صفحه تولید می‌کند.
          </p>
        </div>
      </header>

      <section className="architecture-grid">
        <article>
          <FileStack size={29} />
          <h2>آماده‌سازی داده</h2>
          <p>استخراج متن، OCR، نرمال‌سازی فارسی و Chunking ساختارمحور.</p>
        </article>
        <article>
          <Database size={29} />
          <h2>Retrieval</h2>
          <p>BM25، Dense Retrieval، FAISS، Hybrid RRF و Reranking.</p>
        </article>
        <article>
          <BrainCircuit size={29} />
          <h2>Generation</h2>
          <p>پاسخ مستند فارسی، Citation Validation و No-answer behavior.</p>
        </article>
        <article>
          <Network size={29} />
          <h2>Full Stack</h2>
          <p>FastAPI در Backend و React + TypeScript در Frontend.</p>
        </article>
      </section>

      <section className="project-note">
        <GraduationCap size={28} />
        <div>
          <h2>دانشگاه شهید باهنر کرمان</h2>
          <p>این سامانه یک پروژه آموزشی مستقل است و سرویس رسمی یا مورد تأیید دانشگاه نیست.</p>
        </div>
      </section>
    </div>
  );
}
