/**
 * 交易詳情頁（bills-management-and-insights §9）。
 *
 * 路由：``/transactions/:id``
 *
 * 功能：
 * - inline 編輯 category（select，立刻 PUT，樂觀更新，失敗 revert）
 * - note textarea，debounce 500ms 自動儲存，失焦時 flush
 * - tags multi-select chip：新增 / 移除即時送出 PUT
 * - merchant_alias text field（debounce 500ms）
 * - 分類來源徽章：manual_override / engine（含 hover tooltip）
 * - 「重置覆寫」按鈕：呼叫 DELETE /manual-override
 */
import { ArrowLeft, RefreshCcw, Tag, X } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { SelectField } from '@/components/ui/select-field'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { LoadingState, ErrorState } from '@/components/shared/states'
import { useTransactionEdit } from '@/hooks/use-transaction-edit'
import type { TransactionDetailItem } from '@/lib/types'
import { formatAmount, formatDate } from '@/lib/utils'

function classificationSourceLabel(detail: TransactionDetailItem): {
  readonly label: string
  readonly variant: 'default' | 'secondary'
  readonly tooltip: string
} {
  if (detail.manual_category_override) {
    return {
      label: '手動覆寫',
      variant: 'default',
      tooltip:
        '使用者手動指定的分類，pipeline 重跑時不會被覆蓋。按下「重置覆寫」可恢復自動分類。',
    }
  }
  return {
    label: '自動分類',
    variant: 'secondary',
    tooltip:
      '由 user_rules 或內建 engine 自動套用的分類。下次 pipeline 重跑可能更新。',
  }
}

function TransactionDetailPage() {
  const params = useParams<{ id: string }>()
  const transactionId = Number(params.id)
  const navigate = useNavigate()

  const edit = useTransactionEdit(transactionId)
  const {
    detail,
    categories,
    isLoading,
    queryError: error,
    refetch,
    isFetching,
    saveStatus,
    error: saveError,
    isResetting,
    noteValue,
    aliasValue,
    tagInput,
    setNoteDraft,
    flushNote,
    setAliasDraft,
    flushAlias,
    changeCategory,
    addTag,
    removeTag,
    resetOverride,
    setTagInput,
  } = edit

  // -- Render --------------------------------------------------------------

  if (!Number.isFinite(transactionId) || transactionId <= 0) {
    return <ErrorState message="無效的交易 ID" />
  }
  if (isLoading) return <LoadingState />
  if (error)
    return (
      <ErrorState
        message={error.message}
        onRetry={() => refetch()}
        isRetrying={isFetching}
      />
    )
  if (!detail)
    return (
      <ErrorState
        message="交易不存在"
        onRetry={() => refetch()}
        isRetrying={isFetching}
      />
    )

  const source = classificationSourceLabel(detail)
  const uniqueCategories = Array.from(
    new Map(categories.map((c) => [c.category, c])).values(),
  )

  return (
    <div className="space-y-6 max-w-3xl">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(-1)}
            aria-label="返回"
          >
            <ArrowLeft className="size-4" />
            返回
          </Button>
          <h1 className="text-2xl font-bold">交易詳情</h1>
        </div>

        <section className="rounded-lg border border-border p-4 space-y-2">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-lg font-semibold">{detail.merchant}</div>
              {detail.merchant_alias && (
                <div className="text-sm text-muted-foreground">
                  別名：{detail.merchant_alias}
                </div>
              )}
            </div>
            <div className="text-right text-2xl font-bold">
              {formatAmount(detail.amount, detail.currency)}
            </div>
          </div>
          <div className="text-sm text-muted-foreground">
            {formatDate(detail.trans_date)} · {detail.bank_code} ·{' '}
            {formatDate(detail.billing_month)}
          </div>
          {detail.installment_current !== null &&
            detail.installment_total !== null && (
              <div className="text-sm text-muted-foreground">
                分期 {detail.installment_current}/{detail.installment_total}
              </div>
            )}
        </section>

        <section className="space-y-2">
          <div className="flex items-center gap-2">
            <label htmlFor="category" className="text-sm font-medium">
              分類
            </label>
            <Tooltip>
              <TooltipTrigger className="cursor-help">
                <Badge variant={source.variant}>{source.label}</Badge>
              </TooltipTrigger>
              <TooltipContent>{source.tooltip}</TooltipContent>
            </Tooltip>
            {detail.manual_category_override && (
              <Button
                variant="outline"
                size="sm"
                onClick={resetOverride}
                disabled={isResetting}
                aria-label="重置覆寫"
              >
                <RefreshCcw className="size-3" />
                重置覆寫
              </Button>
            )}
          </div>
          <SelectField
            id="category"
            aria-label="分類"
            triggerClassName="w-full rounded-md px-3 py-2"
            value={String(
              uniqueCategories.find((c) => c.category === detail.category)?.id ??
                '',
            )}
            onValueChange={(v) => {
              // The placeholder item ('' = current category) is a no-op; only
              // a real category id triggers the update mutation.
              if (v) changeCategory(Number(v))
            }}
            options={[
              { value: '', label: detail.category ?? '未分類' },
              ...uniqueCategories.map((c) => ({
                value: String(c.id),
                label: c.category,
              })),
            ]}
          />
        </section>

        <section className="space-y-2">
          <label htmlFor="merchant-alias" className="text-sm font-medium">
            商家別名（顯示用，不影響 classify）
          </label>
          <input
            id="merchant-alias"
            type="text"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={aliasValue}
            maxLength={200}
            onChange={(e) => setAliasDraft(e.target.value)}
            onBlur={flushAlias}
            aria-label="商家別名"
          />
        </section>

        <section className="space-y-2">
          <label htmlFor="note" className="text-sm font-medium">
            備註
          </label>
          <textarea
            id="note"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm min-h-24"
            value={noteValue}
            maxLength={2000}
            onChange={(e) => setNoteDraft(e.target.value)}
            onBlur={flushNote}
            aria-label="備註"
          />
          <div
            className="text-xs text-muted-foreground"
            aria-live="polite"
          >
            {saveStatus === 'saving'
              ? '儲存中…'
              : saveStatus === 'saved'
                ? '已儲存 ✓'
                : '自動儲存（500ms）'}
          </div>
        </section>

        <section className="space-y-2">
          <div className="text-sm font-medium flex items-center gap-1">
            <Tag className="size-4" /> 標籤
          </div>
          <div className="flex flex-wrap gap-2">
            {detail.tags.map((tag) => (
              <Badge key={tag} variant="secondary" className="gap-1">
                {tag}
                <button
                  type="button"
                  onClick={() => removeTag(tag)}
                  aria-label={`移除標籤 ${tag}`}
                  className="ml-1 hover:text-destructive"
                >
                  <X className="size-3" />
                </button>
              </Badge>
            ))}
            {detail.tags.length === 0 && (
              <span className="text-sm text-muted-foreground">尚無標籤</span>
            )}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="新標籤..."
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addTag()
                }
              }}
              maxLength={100}
              aria-label="新增標籤"
              className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
            <Button variant="outline" size="sm" onClick={addTag}>
              新增
            </Button>
          </div>
        </section>

        {saveError !== null && (
          <div
            role="alert"
            className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm"
          >
            儲存失敗：
            {saveError.message}
            <Button
              variant="link"
              size="sm"
              onClick={() => refetch()}
              className="ml-2"
            >
              重新整理
            </Button>
          </div>
        )}

        <div className="text-xs text-muted-foreground">
          最後更新：{new Date(detail.updated_at).toLocaleString('zh-TW')}
        </div>

        <div>
          <Link to="/transactions" className="text-sm text-primary hover:underline">
            返回交易列表
          </Link>
        </div>
      </div>
  )
}

export default TransactionDetailPage
