import type { LucideIcon } from 'lucide-react';

interface MetricCardProps {
  icon: LucideIcon;
  label: string;
  value: string;
  accent?: 'blue' | 'green' | 'purple' | 'amber' | 'cyan';
  detail?: string;
}

export default function MetricCard({
  icon: Icon,
  label,
  value,
  accent = 'blue',
  detail,
}: MetricCardProps) {
  return (
    <article className={`metric-card premium-metric-card metric-${accent}`}>
      <div className="metric-glow" />
      <div className="metric-icon">
        <Icon size={20} />
      </div>
      <div className="metric-copy">
        <span>{label}</span>
        <strong>{value}</strong>
        {detail && <small>{detail}</small>}
      </div>
    </article>
  );
}
