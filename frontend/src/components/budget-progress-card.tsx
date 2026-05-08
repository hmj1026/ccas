/**
 * Budget progress card (bills-management-and-insights §12.5)。
 *
 * 顯示「當月已花 / 預算 / 百分比」進度條（綠/黃/紅三色階）+
 * scope 標題 + threshold 標記。
 */
import type { BudgetItem, BudgetCurrentPeriod } from '@/lib/types'

const SCOPE_LABELS: Record<BudgetItem['scope'], string> = {
  monthly_total: '整月支出',
  monthly_category: '類別',
  monthly_bank: '銀行',
}

function formatCurrency(amount: number): string {
  return `$${amount.toLocaleString('zh-Hant')}`
}

function colorByPercent(percent: number): {
  readonly bar: string
  readonly text: string
} {
  if (percent >= 100) return { bar: 'bg-red-500', text: 'text-red-600' }
  if (percent >= 80) return { bar: 'bg-yellow-500', text: 'text-yellow-700' }
  return { bar: 'bg-green-500', text: 'text-green-700' }
}

export function BudgetProgressCard({
  budget,
  current,
}: {
  readonly budget: BudgetItem
  readonly current: BudgetCurrentPeriod | null
}) {
  const percent = current?.percent ?? 0
  const cur = current?.current_amount_minor_units ?? 0
  const colors = colorByPercent(percent)
  const scopeTitle = budget.scope_ref
    ? `${SCOPE_LABELS[budget.scope]}：${budget.scope_ref}`
    : SCOPE_LABELS[budget.scope]

  return (
    <div className="rounded-lg border border-border p-4 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">{scopeTitle}</p>
        <span className={`text-xs font-medium ${colors.text}`}>
          {percent.toFixed(1)}%
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted">
        <div
          className={`h-2 rounded-full ${colors.bar}`}
          style={{ width: `${Math.min(percent, 100)}%` }}
          aria-label="預算進度"
          role="progressbar"
          aria-valuenow={Math.round(percent)}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          已花 {formatCurrency(cur)} / {formatCurrency(budget.amount_minor_units)}
        </span>
        <span>警示閾值 {budget.alert_threshold_percent}%</span>
      </div>
      {!budget.enabled && (
        <p className="text-xs text-muted-foreground">（已停用）</p>
      )}
    </div>
  )
}
