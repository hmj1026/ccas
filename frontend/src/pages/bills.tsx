/**
 * Bills 頁面 -- 帳單列表、付款狀態切換與 PDF 連結。
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Check, Clock } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { apiGet, apiPatch } from '@/lib/api-client'
import type { ApiResponse, BillItem } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { LoadingState, ErrorState, EmptyState } from '@/components/shared/states'

function formatAmount(amount: number): string {
  return `$${amount.toLocaleString()}`
}

function BillsPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const month = searchParams.get('month') ?? ''
  const status = searchParams.get('status') ?? 'all'

  const { data, isLoading, error } = useQuery({
    queryKey: ['bills', month, status],
    queryFn: () =>
      apiGet<ApiResponse<readonly BillItem[]>>('/api/bills', {
        month: month || undefined,
        status,
      }),
  })

  const togglePaid = useMutation({
    mutationFn: ({ id, is_paid }: { id: number; is_paid: boolean }) =>
      apiPatch<ApiResponse<BillItem>>(`/api/bills/${id}`, { is_paid }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bills'] })
      queryClient.invalidateQueries({ queryKey: ['overview'] })
    },
  })

  function updateParam(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value && value !== 'all') {
        next.set(key, value)
      } else {
        next.delete(key)
      }
      return next
    })
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">帳單管理</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <input
          type="month"
          value={month}
          onChange={(e) => updateParam('month', e.target.value)}
          className="h-8 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="月份篩選"
        />
        <select
          value={status}
          onChange={(e) => updateParam('status', e.target.value)}
          className="h-8 rounded-lg border border-input bg-background px-3 text-sm"
          aria-label="付款狀態篩選"
        >
          <option value="all">全部</option>
          <option value="paid">已繳</option>
          <option value="unpaid">未繳</option>
        </select>
      </div>

      {/* Bill list */}
      {isLoading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error.message} />
      ) : !data?.data.length ? (
        <EmptyState message="沒有符合條件的帳單" />
      ) : (
        <div className="space-y-3">
          {data.data.map((bill) => (
            <div
              key={bill.id}
              className="flex items-center justify-between rounded-lg border border-border p-4"
            >
              <div className="space-y-1">
                <p className="font-medium">
                  {bill.bank_name ?? bill.bank_code}
                </p>
                <p className="text-sm text-muted-foreground">
                  {bill.billing_month} / 到期日: {bill.due_date}
                </p>
                <p className="text-lg font-bold">
                  {formatAmount(bill.total_amount)}
                </p>
              </div>

              <div className="flex items-center gap-2">
                {bill.pdf_url && (
                  <a
                    href={bill.pdf_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                    aria-label={`開啟 ${bill.bank_name ?? bill.bank_code} PDF`}
                  >
                    <ExternalLink className="size-4" />
                    PDF
                  </a>
                )}
                <Button
                  variant={bill.is_paid ? 'secondary' : 'outline'}
                  size="sm"
                  disabled={togglePaid.isPending}
                  onClick={() =>
                    togglePaid.mutate({ id: bill.id, is_paid: !bill.is_paid })
                  }
                  aria-label={
                    bill.is_paid ? '標記為未繳' : '標記為已繳'
                  }
                >
                  {bill.is_paid ? (
                    <>
                      <Check className="size-4" data-icon="inline-start" />
                      已繳
                    </>
                  ) : (
                    <>
                      <Clock className="size-4" data-icon="inline-start" />
                      未繳
                    </>
                  )}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default BillsPage
