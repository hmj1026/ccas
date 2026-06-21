/**
 * Settings 子頁：預算管理（bills-management-and-insights §12）。
 *
 * 列出所有預算 + 每筆當月進度卡。提供新增 / 編輯 / 刪除。
 * 預算 scope：monthly_total / monthly_category / monthly_bank。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { apiDelete, apiGet, apiPost, apiPut } from '@/lib/api-client'
import { BudgetProgressCard } from '@/components/budget-progress-card'
import { Button } from '@/components/ui/button'
import { SelectField } from '@/components/ui/select-field'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from '@/components/shared/states'
import type {
  ApiResponse,
  BudgetCreateRequest,
  BudgetCurrentPeriod,
  BudgetItem,
  BudgetScope,
  BudgetUpdateRequest,
} from '@/lib/types'

const SCOPE_OPTIONS: ReadonlyArray<{ value: BudgetScope; label: string }> = [
  { value: 'monthly_total', label: '整月支出' },
  { value: 'monthly_category', label: '單一類別' },
  { value: 'monthly_bank', label: '單一銀行' },
]

function CreateBudgetDialog({
  onCreate,
  isPending,
}: {
  readonly onCreate: (
    body: BudgetCreateRequest,
    opts: { onSuccess: () => void },
  ) => void
  readonly isPending: boolean
}) {
  const [open, setOpen] = useState(false)
  const [scope, setScope] = useState<BudgetScope>('monthly_total')
  const [scopeRef, setScopeRef] = useState('')
  const [amount, setAmount] = useState('')
  const [threshold, setThreshold] = useState('80')
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const amountNum = Number.parseInt(amount, 10)
    const thresholdNum = Number.parseInt(threshold, 10)
    if (!Number.isFinite(amountNum) || amountNum <= 0) {
      setError('金額必須為正整數')
      return
    }
    if (!Number.isFinite(thresholdNum) || thresholdNum < 1 || thresholdNum > 100) {
      setError('閾值必須在 1-100 之間')
      return
    }
    if (scope !== 'monthly_total' && !scopeRef.trim()) {
      setError(`${scope} 必須指定範圍（類別名 / 銀行代碼）`)
      return
    }
    // 僅在 API 成功後才關閉並清空表單；失敗時保留輸入並由父層顯示錯誤。
    onCreate(
      {
        scope,
        scope_ref: scope === 'monthly_total' ? null : scopeRef.trim(),
        amount_ntd: amountNum,
        alert_threshold_percent: thresholdNum,
        enabled: true,
      },
      {
        onSuccess: () => {
          setOpen(false)
          setScope('monthly_total')
          setScopeRef('')
          setAmount('')
          setThreshold('80')
        },
      },
    )
  }

  if (!open) {
    return (
      <Button onClick={() => setOpen(true)}>
        <Plus className="size-4" data-icon="inline-start" />
        新增預算
      </Button>
    )
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-lg border border-border p-4"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">新增預算</h3>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setOpen(false)}
        >
          取消
        </Button>
      </div>
      <SelectField
        label="範圍"
        triggerClassName="h-auto rounded px-2 py-1"
        value={scope}
        onValueChange={(v) => setScope(v as BudgetScope)}
        options={SCOPE_OPTIONS}
      />
      {scope !== 'monthly_total' && (
        <label className="flex flex-col text-sm">
          <span className="text-muted-foreground">
            {scope === 'monthly_category' ? '類別名稱' : '銀行代碼'}
          </span>
          <input
            type="text"
            className="rounded border border-input bg-background px-2 py-1"
            value={scopeRef}
            onChange={(e) => setScopeRef(e.target.value)}
            placeholder={
              scope === 'monthly_category' ? '例如：餐飲' : '例如：CTBC'
            }
          />
        </label>
      )}
      <label className="flex flex-col text-sm">
        <span className="text-muted-foreground">月度上限金額（元）</span>
        <input
          id="budget-amount"
          type="number"
          min={1}
          className="rounded border border-input bg-background px-2 py-1"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          aria-describedby="budget-error"
          aria-invalid={error !== null}
          required
        />
      </label>
      <label className="flex flex-col text-sm">
        <span className="text-muted-foreground">
          警示閾值（%）— {threshold}%
        </span>
        <input
          type="range"
          min={1}
          max={100}
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
        />
      </label>
      {/* 持續掛載的 live region：min-h 預留高度避免 layout shift。 */}
      <p
        id="budget-error"
        role="alert"
        className="min-h-4 text-xs text-destructive"
      >
        {error ?? ''}
      </p>
      <Button type="submit" disabled={isPending}>
        建立
      </Button>
    </form>
  )
}

function BudgetCard({
  budget,
  current,
  onUpdate,
  onDeleteRequest,
  isPending,
}: {
  readonly budget: BudgetItem
  readonly current: BudgetCurrentPeriod | null
  readonly onUpdate: (body: BudgetUpdateRequest) => void
  readonly onDeleteRequest: () => void
  readonly isPending: boolean
}) {
  return (
    <div className="space-y-2">
      <BudgetProgressCard budget={budget} current={current} />
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1 text-xs">
          <input
            type="checkbox"
            checked={budget.enabled}
            disabled={isPending}
            onChange={(e) => onUpdate({ enabled: e.target.checked })}
          />
          啟用
        </label>
        <Button
          variant="ghost"
          size="sm"
          onClick={onDeleteRequest}
          disabled={isPending}
        >
          <Trash2 className="size-4" data-icon="inline-start" />
          刪除
        </Button>
      </div>
    </div>
  )
}

function SettingsBudgetsPage() {
  const queryClient = useQueryClient()
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<BudgetItem | null>(null)
  const { data, isLoading, error } = useQuery({
    queryKey: ['budgets', 'list'],
    queryFn: () =>
      apiGet<ApiResponse<readonly BudgetItem[]>>(
        // include_current_period：後端單次批次聚合內聯各筆當月累計，免逐筆 1+N。
        '/api/budgets?include_current_period=true',
      ),
  })

  const createMutation = useMutation({
    mutationFn: (body: BudgetCreateRequest) =>
      apiPost<ApiResponse<BudgetItem>>('/api/budgets', body),
    onSuccess: () => {
      setMutationError(null)
      queryClient.invalidateQueries({ queryKey: ['budgets'] })
    },
    onError: (err: Error) => setMutationError(err.message),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: BudgetUpdateRequest }) =>
      apiPut<ApiResponse<BudgetItem>>(`/api/budgets/${id}`, body),
    onSuccess: () => {
      setMutationError(null)
      queryClient.invalidateQueries({ queryKey: ['budgets'] })
    },
    onError: (err: Error) => setMutationError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      apiDelete<ApiResponse<{ deleted_id: number }>>(`/api/budgets/${id}`),
    onSuccess: () => {
      setMutationError(null)
      queryClient.invalidateQueries({ queryKey: ['budgets'] })
    },
    onError: (err: Error) => setMutationError(err.message),
  })

  if (isLoading) return <LoadingState />
  if (error) return <ErrorState message={error.message} />

  const budgets = data?.data ?? []

  const isPending =
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">預算管理</h1>
        <p className="text-sm text-muted-foreground">
          設定每月支出上限與警示閾值；超過閾值會推 Telegram + dashboard banner。
        </p>
      </div>
      {mutationError ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {mutationError}
        </p>
      ) : null}
      <CreateBudgetDialog
        onCreate={(body, opts) => createMutation.mutate(body, opts)}
        isPending={createMutation.isPending}
      />
      {budgets.length === 0 ? (
        <EmptyState message="尚未設定任何預算，建立第一筆來啟用警示。" />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {budgets.map((b) => (
            <BudgetCard
              key={b.id}
              budget={b}
              current={b.current_period ?? null}
              onUpdate={(body) =>
                updateMutation.mutate({ id: b.id, body })
              }
              onDeleteRequest={() => setDeleteTarget(b)}
              isPending={isPending}
            />
          ))}
        </div>
      )}

      {/* Delete confirmation dialog */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>刪除預算</DialogTitle>
            <DialogDescription>
              刪除預算後已記錄的交易分類不變，但超支警示將停止觸發。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
            <Button
              variant="destructive"
              disabled={deleteMutation.isPending}
              onClick={() => {
                if (deleteTarget) deleteMutation.mutate(deleteTarget.id)
                setDeleteTarget(null)
              }}
            >
              確認刪除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default SettingsBudgetsPage
