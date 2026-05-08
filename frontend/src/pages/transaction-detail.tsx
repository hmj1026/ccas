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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, RefreshCcw, Tag, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { LoadingState, ErrorState } from '@/components/shared/states'
import { apiDelete, apiGet, apiPut } from '@/lib/api-client'
import type {
  ApiResponse,
  CategoryKeywordItem,
  TransactionDetailItem,
  TransactionUpdateRequest,
} from '@/lib/types'
import { formatAmount } from '@/lib/utils'

const NOTE_DEBOUNCE_MS = 500
const ALIAS_DEBOUNCE_MS = 500

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
  const queryClient = useQueryClient()

  const detailQueryKey = ['transactions', transactionId, 'detail'] as const

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: detailQueryKey,
    queryFn: () =>
      apiGet<ApiResponse<TransactionDetailItem>>(
        `/api/transactions/${transactionId}`,
      ),
    enabled: Number.isFinite(transactionId) && transactionId > 0,
  })

  const detail = data?.data

  const { data: categoriesData } = useQuery({
    queryKey: ['settings', 'categories'],
    queryFn: () =>
      apiGet<ApiResponse<readonly CategoryKeywordItem[]>>(
        '/api/settings/categories',
      ),
  })

  // -- Mutations -----------------------------------------------------------

  const updateMutation = useMutation({
    mutationFn: (body: TransactionUpdateRequest) =>
      apiPut<ApiResponse<TransactionDetailItem>>(
        `/api/transactions/${transactionId}`,
        body,
      ),
    onSuccess: (resp) => {
      queryClient.setQueryData(detailQueryKey, resp)
    },
  })

  const resetOverrideMutation = useMutation({
    mutationFn: () =>
      apiDelete<ApiResponse<TransactionDetailItem>>(
        `/api/transactions/${transactionId}/manual-override`,
      ),
    onSuccess: (resp) => {
      queryClient.setQueryData(detailQueryKey, resp)
    },
  })

  // -- Local debounced fields ---------------------------------------------
  //
  // Drafts use ``string | null`` 初值 null：尚未由使用者編輯時 fallback 到 server
  // 端值；一旦使用者輸入就成為 controlled state。這樣可避免在 useEffect 裡呼叫
  // setState（react-hooks/set-state-in-effect 規則）來同步 props → state。

  const [noteDraft, setNoteDraft] = useState<string | null>(null)
  const [aliasDraft, setAliasDraft] = useState<string | null>(null)
  const [tagInput, setTagInput] = useState('')

  const noteValue = noteDraft ?? detail?.note ?? ''
  const aliasValue = aliasDraft ?? detail?.merchant_alias ?? ''

  // Debounced note auto-save：只有 noteDraft 已被使用者改過才送
  useEffect(() => {
    if (!detail || noteDraft === null) return
    if (noteDraft === (detail.note ?? '')) return
    const t = setTimeout(() => {
      updateMutation.mutate({ note: noteDraft })
    }, NOTE_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [noteDraft, detail, updateMutation])

  // Debounced merchant_alias auto-save
  useEffect(() => {
    if (!detail || aliasDraft === null) return
    if (aliasDraft === detail.merchant_alias) return
    const t = setTimeout(() => {
      updateMutation.mutate({ merchant_alias: aliasDraft })
    }, ALIAS_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [aliasDraft, detail, updateMutation])

  // -- Handlers ------------------------------------------------------------

  function handleCategoryChange(categoryId: number) {
    updateMutation.mutate({ category_id: categoryId })
  }

  function handleAddTag() {
    const trimmed = tagInput.trim()
    if (!trimmed || !detail) return
    if (detail.tags.includes(trimmed)) {
      setTagInput('')
      return
    }
    updateMutation.mutate({ tags: [...detail.tags, trimmed] })
    setTagInput('')
  }

  function handleRemoveTag(tag: string) {
    if (!detail) return
    updateMutation.mutate({ tags: detail.tags.filter((t) => t !== tag) })
  }

  function handleResetOverride() {
    resetOverrideMutation.mutate()
  }

  // -- Render --------------------------------------------------------------

  if (!Number.isFinite(transactionId) || transactionId <= 0) {
    return <ErrorState message="無效的交易 ID" />
  }
  if (isLoading) return <LoadingState />
  if (error) return <ErrorState message={error.message} />
  if (!detail) return <ErrorState message="交易不存在" />

  const source = classificationSourceLabel(detail)
  const categoryOptions = categoriesData?.data ?? []
  const uniqueCategories = Array.from(
    new Map(categoryOptions.map((c) => [c.category, c])).values(),
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
            {detail.trans_date} · {detail.bank_code} · {detail.billing_month}
          </div>
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
                onClick={handleResetOverride}
                disabled={resetOverrideMutation.isPending}
                aria-label="重置覆寫"
              >
                <RefreshCcw className="size-3" />
                重置覆寫
              </Button>
            )}
          </div>
          <select
            id="category"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={
              uniqueCategories.find((c) => c.category === detail.category)?.id ??
              ''
            }
            onChange={(e) => handleCategoryChange(Number(e.target.value))}
            aria-label="分類選擇"
          >
            <option value="">{detail.category ?? '未分類'}</option>
            {uniqueCategories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.category}
              </option>
            ))}
          </select>
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
            onBlur={() => {
              if (detail && noteDraft !== null && noteDraft !== (detail.note ?? '')) {
                updateMutation.mutate({ note: noteDraft })
              }
            }}
            aria-label="備註"
          />
          <div className="text-xs text-muted-foreground">
            自動儲存（500ms）
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
                  onClick={() => handleRemoveTag(tag)}
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
                  handleAddTag()
                }
              }}
              maxLength={100}
              aria-label="新增標籤"
              className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
            <Button variant="outline" size="sm" onClick={handleAddTag}>
              新增
            </Button>
          </div>
        </section>

        {updateMutation.isError && (
          <div className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm">
            儲存失敗：{updateMutation.error?.message ?? '未知錯誤'}
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
