import type { AdminMetric } from '../../types/admin'

import { StatusBadge } from './StatusBadge'

type MetricCardProps = {
  metric: AdminMetric
}

export function MetricCard({ metric }: MetricCardProps) {
  return (
    <article className={`metric-card metric-card--${metric.tone}`}>
      <div className="metric-card__top">
        <span>{metric.label}</span>
        <StatusBadge tone={metric.tone}>{metric.delta}</StatusBadge>
      </div>
      <strong>{metric.value}</strong>
    </article>
  )
}
