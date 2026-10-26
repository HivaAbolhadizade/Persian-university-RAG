import {
  Clock3,
  MessageSquareText,
  MoreHorizontal,
  Search,
  Trash2,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import type { HistoryItem } from '../types';

interface HistoryPanelProps {
  items: HistoryItem[];
  onSelect: (item: HistoryItem) => void;
  onClear: () => void;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('fa-IR', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

export default function HistoryPanel({ items, onSelect, onClear }: HistoryPanelProps) {
  const [filter, setFilter] = useState('');
  const filtered = useMemo(
    () => items.filter((item) => item.question.includes(filter.trim())),
    [items, filter],
  );

  return (
    <aside className="history-card premium-history-card">
      <div className="history-title premium-history-title">
        <div>
          <Clock3 size={19} />
          <h2>گفتگوهای اخیر</h2>
        </div>
        <button type="button" aria-label="گزینه‌های تاریخچه"><MoreHorizontal size={19} /></button>
      </div>

      <label className="history-search">
        <Search size={15} />
        <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="جست‌وجو در تاریخچه" />
      </label>

      <div className="history-list premium-history-list">
        {filtered.length === 0 ? (
          <div className="history-empty">
            <div className="history-empty-orb"><MessageSquareText size={25} /></div>
            <p>{items.length === 0 ? 'هنوز گفتگویی ثبت نشده است.' : 'نتیجه‌ای پیدا نشد.'}</p>
          </div>
        ) : (
          filtered.map((item, index) => (
            <button key={item.id} onClick={() => onSelect(item)} className={index === 0 ? 'is-latest' : ''}>
              <span className="history-message-icon"><MessageSquareText size={15} /></span>
              <span className="history-question">{item.question}</span>
              <small>{formatTime(item.createdAt)}</small>
              {index === 0 && <em>جدید</em>}
            </button>
          ))
        )}
      </div>

      <button className="clear-history premium-clear-history" onClick={onClear} disabled={items.length === 0}>
        <Trash2 size={16} />
        پاک کردن تاریخچه
      </button>
    </aside>
  );
}
