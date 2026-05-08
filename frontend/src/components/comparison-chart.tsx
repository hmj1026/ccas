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
import { EmptyState } from '@/components/shared/states'

const currencyFormatter = (
  v: number | string | readonly (number | string)[] | undefined,
) => `$${Number(v).toLocaleString()}`

export function BankComparisonBarChart({
  data,
}: {
  readonly data: readonly BankCompareItem[]
}) {
  if (data.length === 0) return <EmptyState message="尚無銀行資料" />
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data as BankCompareItem[]}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={(d: BankCompareItem) => d.bank_name ?? d.bank_code} />
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
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data as YearCompareItem[]}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="year" />
        <YAxis />
        <Tooltip
          formatter={(v: number | string) =>
            metricLabel === '金額' ? currencyFormatter(v) : v
          }
        />
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
  )
}
