/**
 * Active budget alerts banner (bills-management-and-insights §12.4)。
 *
 * 顯示當月未確認的預算超支警示，每筆 alert 含 acknowledge 按鈕。
 * 若無 alert 則不渲染。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, X } from 'lucide-react'
import { apiGet, apiPost } from '@/lib/api-client'
import type { ApiResponse, BudgetAlertItem, BudgetScope } from '@/lib/types'
import { formatAmount } from '@/lib/utils'
import { Button } from '@/components/ui/button'

const SCOPE_LABEL: Record<BudgetScope, string> = {
  monthly_total: '整月支出',
  monthly_category: '類別',
  monthly_bank: '銀行',
}

function describeAlert(alert: BudgetAlertItem): string {
  const scope = alert.scope_ref
    ? `${SCOPE_LABEL[alert.scope]}「${alert.scope_ref}」`
    : SCOPE_LABEL[alert.scope]
  const cur = formatAmount(alert.current_amount_ntd)
  const cap = formatAmount(alert.amount_ntd)
  return `${scope}：${cur} / ${cap}（${alert.threshold_breached_percent}% 已達）`
}

export function BudgetAlertBanner() {
  const queryClient = useQueryClient()
  const { data } = useQuery({
    queryKey: ['budgets', 'alerts', 'active'],
    queryFn: () =>
      apiGet<ApiResponse<readonly BudgetAlertItem[]>>(
        '/api/budgets/alerts/active',
      ),
  })

  const ackMutation = useMutation({
    mutationFn: (alertId: number) =>
      apiPost<ApiResponse<{ acknowledged_id: number }>>(
        `/api/budgets/alerts/${alertId}/acknowledge`,
        {},
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['budgets', 'alerts', 'active'],
      })
    },
  })

  const alerts = data?.data ?? []
  if (alerts.length === 0) return null

  return (
    <div
      role="alert"
      className="rounded-lg border border-orange-300 bg-orange-500/10 p-3 space-y-2 dark:border-orange-500/40"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-orange-700 dark:text-orange-300">
        <AlertTriangle className="size-4" />
        預算超支警示
      </div>
      <ul className="space-y-1 text-sm text-orange-900 dark:text-orange-200">
        {alerts.map((alert) => (
          <li
            key={alert.id}
            className="flex items-center justify-between gap-2"
          >
            <span>{describeAlert(alert)}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => ackMutation.mutate(alert.id)}
              disabled={ackMutation.isPending}
              aria-label={`確認已知曉：${describeAlert(alert)}`}
            >
              <X className="size-4" data-icon="inline-start" />
              已知曉
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}
