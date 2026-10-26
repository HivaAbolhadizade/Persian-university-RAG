import {
  BookOpenCheck,
  ChevronDown,
  ExternalLink,
  FileText,
  Hash,
} from 'lucide-react';
import { useState } from 'react';
import type { RagSource } from '../types';

interface SourceCardProps {
  source: RagSource;
  showScore: boolean;
  index?: number;
}

export default function SourceCard({ source, showScore, index = 0 }: SourceCardProps) {
  const [open, setOpen] = useState(false);
  const pageLabel =
    source.page_start === source.page_end
      ? `صفحه ${source.page_start.toLocaleString('fa-IR')}`
      : `صفحات ${source.page_start.toLocaleString('fa-IR')} تا ${source.page_end.toLocaleString('fa-IR')}`;

  return (
    <article className={`source-card premium-source-card ${open ? 'is-open' : ''}`}>
      <button className="source-main premium-source-main" onClick={() => setOpen((value) => !value)}>
        <div className="source-rank">{(index + 1).toLocaleString('fa-IR')}</div>
        <div className="source-file-icon premium-source-icon">
          <FileText size={20} />
        </div>
        <div className="source-info premium-source-info">
          <strong>{source.title}</strong>
          <span>
            {pageLabel}
            {source.article ? ` · ماده ${source.article}` : ''}
            {source.note ? ` · تبصره ${source.note}` : ''}
          </span>
          <div className="source-progress"><span style={{ width: `${Math.min(100, Math.max(0, source.score * 100))}%` }} /></div>
        </div>
        <div className="source-badges premium-source-badges">
          {showScore && <span className="score-badge">{source.score.toFixed(2)}</span>}
          <span className="page-badge">{pageLabel}</span>
          <ChevronDown size={17} className="source-chevron" />
        </div>
      </button>

      {open && (
        <div className="source-excerpt premium-source-excerpt">
          <div className="source-excerpt-head">
            <span><BookOpenCheck size={16} /> متن بازیابی‌شده</span>
            <button type="button"><ExternalLink size={15} /> مشاهده سند</button>
          </div>
          <p>{source.text}</p>
          <div className="source-meta-footer">
            <span><Hash size={13} /> {source.chunk_id}</span>
            <span>{source.category}</span>
          </div>
        </div>
      )}
    </article>
  );
}
