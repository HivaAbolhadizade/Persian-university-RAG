import { BarChart3, CheckCircle2, Clock3, Quote } from 'lucide-react';

const rows = [
  { method: 'BM25', recall: 0.71, mrr: 0.63, ndcg: 0.68, latency: 18 },
  { method: 'Dense E5', recall: 0.84, mrr: 0.76, ndcg: 0.79, latency: 42 },
  { method: 'Hybrid RRF', recall: 0.91, mrr: 0.83, ndcg: 0.86, latency: 58 },
  { method: 'Hybrid + Reranker', recall: 0.92, mrr: 0.88, ndcg: 0.90, latency: 126 },
];

export default function EvaluationPage() {
  return (
    <div className="page secondary-page">
      <header className="section-header">
        <div>
          <span className="eyebrow">ارزیابی پژوهشی</span>
          <h1>ارزیابی سیستم</h1>
          <p>مقایسه روش‌های بازیابی، کیفیت پاسخ و زمان اجرا.</p>
        </div>
      </header>

      <div className="evaluation-kpis">
        <article>
          <CheckCircle2 size={25} />
          <span>Faithfulness</span>
          <strong>0.91</strong>
        </article>
        <article>
          <Quote size={25} />
          <span>Citation Coverage</span>
          <strong>0.94</strong>
        </article>
        <article>
          <BarChart3 size={25} />
          <span>Recall@5</span>
          <strong>0.92</strong>
        </article>
        <article>
          <Clock3 size={25} />
          <span>Mean Latency</span>
          <strong>2.34s</strong>
        </article>
      </div>

      <section className="table-card">
        <div className="table-title">
          <h2>مقایسه روش‌های Retrieval</h2>
          <span>اعداد نمونه تا اتصال خروجی Notebook 02</span>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>روش</th>
                <th>Recall@5</th>
                <th>MRR@5</th>
                <th>nDCG@5</th>
                <th>Latency (ms)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.method}>
                  <td>{row.method}</td>
                  <td>{row.recall.toFixed(2)}</td>
                  <td>{row.mrr.toFixed(2)}</td>
                  <td>{row.ndcg.toFixed(2)}</td>
                  <td>{row.latency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
