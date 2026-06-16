/**
 * Bills 頁面 -- 帳單列表、付款狀態切換、PDF 連結與手風琴展開明細。
 * 預設：全部帳單，依 billing_month 降序。
 */
import { memo, useCallback, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Check, Clock, ChevronLeft, ChevronRight, ChevronDown, ChevronUp } from 'lucide-react'
import { useSearchParams } from 'react-router'
import { apiGet, apiPatch } from '@/lib/api-client'
import type { ApiResponse, BillItem, PaginatedResponse, TransactionItem } from '@/lib/types'
import { cn, formatAmount, formatDate } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleTrigger, CollapsiblePanel } from '@/components/ui/collapsible'
import { LoadingState, ErrorState, EmptyState } from '@/components/shared/states'
import { FilterBar, type FilterBarParams } from '@/components/shared/filter-bar'
import { StagedAttachmentsWarning } from '@/components/staged-attachments-warning'
import { useFilterParams } from '@/lib/use-filter-params'

const FILTER_SHOW = ['year', 'month', 'bank', 'status'] as const

function BillsPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const [mutationError, setMutationError] = useState<string | null>(null)

  const year = searchParams.get('year') ?? ''
  const month = searchParams.get('month') ?? ''
  const bankCode = searchParams.get('bank_code') ?? ''
  const status = searchParams.get('status') ?? ''
  const page = Number(searchParams.get('page') ?? '1')

  const filterValues = useMemo<FilterBarParams>(
    () => ({ year, month, bank: bankCode, status, category: '', q: '' }),
    [year, month, bankCode, status],
  )

  const handleFilterChange = useFilterParams(true)

  const { data, isLoading, error } = useQuery({
    queryKey: ['bills', year, month, bankCode, status, page],
    queryFn: () =>
      apiGet<PaginatedResponse<BillItem>>('/api/bills', {
        year: year ? Number(year) : undefined,
        month: month || undefined,
        bank_code: bankCode || undefined,
        status: status || undefined,
        page,
        page_size: 20,
      }),
  })

  const togglePaid = useMutation({
    mutationFn: ({ id, is_paid }: { id: number; is_paid: boolean }) =>
      apiPatch<ApiResponse<BillItem>>(`/api/bills/${id}`, { is_paid }),
    onSuccess: () => {
      setMutationError(null)
      queryClient.invalidateQueries({ queryKey: ['bills'] })
      queryClient.invalidateQueries({ queryKey: ['overview'] })
    },
    onError: (err: Error) => setMutationError(err.message),
  })

  // mutate is referentially stable per TanStack Query v5; destructuring lets
  // useCallback below produce a stable handler so memo(BillRow) is effective.
  const { mutate: toggleMutate } = togglePaid
  const handleTogglePaid = useCallback(
    (id: number, isPaid: boolean) => toggleMutate({ id, is_paid: isPaid }),
    [toggleMutate],
  )
  const pendingBillId = togglePaid.isPending ? togglePaid.variables?.id : undefined

  function setPage(p: number) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (p === 1) next.delete('page')
      else next.set('page', String(p))
      return next
    })
  }

  const pagination = data?.pagination

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">帳單管理</h1>

      <StagedAttachmentsWarning />

      <FilterBar
        show={FILTER_SHOW}
        values={filterValues}
        onChange={handleFilterChange}
        extra={
          pagination && (
            <span className="text-sm text-muted-foreground">共 {pagination.total} 筆</span>
          )
        }
      />

      {isLoading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState message={error.message} />
      ) : !data?.data.length ? (
        <EmptyState message="沒有符合條件的帳單" />
      ) : (
        <div className="space-y-3">
          {mutationError ? (
            <p
              role="alert"
              className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {mutationError}
            </p>
          ) : null}
          {data.data.map((bill) => (
            <BillRow
              key={bill.id}
              bill={bill}
              onTogglePaid={handleTogglePaid}
              isPending={pendingBillId === bill.id}
            />
          ))}
        </div>
      )}

      {pagination && pagination.total_pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            aria-label="上一頁"
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="text-sm">
            {page} / {pagination.total_pages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pagination.total_pages}
            onClick={() => setPage(page + 1)}
            aria-label="下一頁"
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      )}
    </div>
  )
}

interface BillRowProps {
  readonly bill: BillItem
  readonly onTogglePaid: (id: number, isPaid: boolean) => void
  readonly isPending: boolean
}

const BillRow = memo(function BillRow({ bill, onTogglePaid, isPending }: BillRowProps) {
  const [isOpen, setIsOpen] = useState(false)
  const name = bill.bank_name ?? bill.bank_code

  const { data: txData, isLoading: txLoading } = useQuery({
    queryKey: ['bill-transactions', bill.id],
    queryFn: () => apiGet<ApiResponse<TransactionItem[]>>(`/api/bills/${bill.id}/transactions`),
    enabled: isOpen,
    staleTime: 5 * 60_000,
  })

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="rounded-lg border border-border">
        <div className="flex items-center justify-between p-4">
          <div className="space-y-1">
            <p className="font-medium">{name}</p>
            <p className="text-sm text-muted-foreground">
              {formatDate(bill.billing_month)} / 到期日: {formatDate(bill.due_date)}
            </p>
            <p className="text-lg font-bold">{formatAmount(bill.total_amount)}</p>
          </div>

          <div className="flex items-center gap-2">
            <CollapsibleTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={isOpen ? `收起 ${name} 帳單明細` : `展開 ${name} 帳單明細`}
                />
              }
            >
              {isOpen ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
            </CollapsibleTrigger>

            {bill.pdf_url && (
              <a
                href={bill.pdf_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                aria-label={`開啟 ${name} PDF`}
              >
                <ExternalLink className="size-4" />
                PDF
              </a>
            )}

            <Button
              variant={bill.is_paid ? 'secondary' : 'outline'}
              size="sm"
              disabled={isPending}
              onClick={() => onTogglePaid(bill.id, !bill.is_paid)}
              aria-label={bill.is_paid ? '標記為未繳' : '標記為已繳'}
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

        <CollapsiblePanel>
          <div className="border-t border-border px-4 pb-4 pt-3 space-y-3">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
              <dt className="text-muted-foreground">帳單月份</dt>
              <dd className="font-medium">{formatDate(bill.billing_month)}</dd>
              <dt className="text-muted-foreground">繳費截止日</dt>
              <dd className="font-medium">{formatDate(bill.due_date)}</dd>
              <dt className="text-muted-foreground">應繳總額</dt>
              <dd className="font-bold">{formatAmount(bill.total_amount)}</dd>
              <dt className="text-muted-foreground">付款狀態</dt>
              <dd className={cn('font-medium', bill.is_paid ? 'text-green-600' : 'text-amber-600')}>
                {bill.is_paid ? '已繳' : '未繳'}
              </dd>
            </dl>

            {txLoading ? (
              <p className="text-sm text-muted-foreground">載入交易明細...</p>
            ) : txData?.data.length ? (
              <div className="overflow-x-auto rounded-md border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-muted text-left">
                    <tr>
                      <th className="px-3 py-1.5">日期</th>
                      <th className="px-3 py-1.5">商家</th>
                      <th className="px-3 py-1.5">分類</th>
                      <th className="px-3 py-1.5">卡末4碼</th>
                      <th className="px-3 py-1.5 text-right">金額</th>
                    </tr>
                  </thead>
                  <tbody>
                    {txData.data.map((tx) => (
                      <tr key={tx.id} className="border-t border-border">
                        <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(tx.trans_date)}</td>
                        <td className="px-3 py-1.5">{tx.merchant}</td>
                        <td className="px-3 py-1.5">
                          {tx.category ? (
                            <span className="rounded-full bg-secondary px-2 py-0.5 text-xs">
                              {tx.category}
                            </span>
                          ) : '-'}
                        </td>
                        <td className="px-3 py-1.5">{tx.card_last4 ?? '-'}</td>
                        <td className="px-3 py-1.5 text-right whitespace-nowrap">
                          {formatAmount(tx.amount, tx.currency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">此帳單無交易明細</p>
            )}
          </div>
        </CollapsiblePanel>
      </div>
    </Collapsible>
  )
})

export default BillsPage
