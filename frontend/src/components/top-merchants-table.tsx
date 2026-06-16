/**
 * Top merchants table component (§13.5)。
 */
import type { TopMerchantItem } from '@/lib/types'
import { formatAmount } from '@/lib/utils'
import { EmptyState } from '@/components/shared/states'

export function TopMerchantsTable({
  data,
}: {
  readonly data: readonly TopMerchantItem[]
}) {
  if (data.length === 0) return <EmptyState message="尚無商家資料" />
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/40">
          <tr>
            <th className="px-3 py-2 text-left">#</th>
            <th className="px-3 py-2 text-left">商家</th>
            <th className="px-3 py-2 text-right">總金額</th>
            <th className="px-3 py-2 text-right">筆數</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row, idx) => (
            <tr key={row.merchant} className="tr-list border-t border-border">
              <td className="px-3 py-2">{idx + 1}</td>
              <td className="px-3 py-2 font-medium">{row.merchant}</td>
              <td className="px-3 py-2 text-right">
                {formatAmount(row.total)}
              </td>
              <td className="px-3 py-2 text-right text-muted-foreground">
                {row.count}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
