/**
 * Comparison charts for Insights page (§13.3 §13.4)。
 *
 * - BankComparisonBarChart：堆疊長條圖呈現各銀行金額
 * - YearComparisonLineChart：折線圖呈現年度趨勢
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { BankCompareItem, YearCompareItem } from '@/lib/types'
import { currencyFormatter } from '@/lib/utils'
import { EmptyState } from '@/components/shared/states'

// 提升到 module scope，避免每次 render 產生新的 closure，
// Recharts 內部會因 prop referential equality 改變而觸發子樹重渲染。
const bankAxisLabel = (d: BankCompareItem) => d.bank_name ?? d.bank_code

const countFormatter = (
  v: number | string | readonly (number | string)[] | undefined,
): string => String(v ?? '')

export function BankComparisonBarChart({
  data,
}: {
  readonly data: readonly BankCompareItem[]
}) {
  if (data.length === 0) return <EmptyState message="尚無銀行資料" />
  return (
    <div role="img" aria-label="各銀行消費金額對比圖">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data as BankCompareItem[]} accessibilityLayer>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={bankAxisLabel} />
          <YAxis />
          <Tooltip formatter={currencyFormatter} />
          <Legend />
          <Bar
            dataKey="total"
            fill="var(--chart-3)"
            radius={[4, 4, 0, 0]}
            name="金額"
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function YearComparisonLineChart({
  data,
  metricLabel,
}: {
  readonly data: readonly YearCompareItem[]
  readonly metricLabel: string
}) {
  if (data.length === 0) return <EmptyState message="尚無年度資料" />
  const tooltipFormatter =
    metricLabel === '金額' ? currencyFormatter : countFormatter
  return (
    <div role="img" aria-label={`年度${metricLabel}對比圖`}>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data as YearCompareItem[]} accessibilityLayer>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="year" />
          <YAxis />
          <Tooltip formatter={tooltipFormatter} />
          <Legend />
          <Line
            type="monotone"
            dataKey="value"
            stroke="var(--chart-2)"
            strokeWidth={2}
            name={metricLabel}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
