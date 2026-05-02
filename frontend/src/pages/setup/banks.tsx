/**
 * Bank-management 設定頁（oauth-onboarding-ui §9）。
 *
 * 列出 `bank_configs` × `bank_settings` 合併視圖，提供啟用/停用切換按鈕。
 * 寫入路徑：`PUT /api/setup/banks/{code}`，採樂觀更新；失敗時 revert 並顯示
 * 錯誤訊息。「孤兒」（DB 有 settings row 但 banks.yaml 無對應）以橙色 badge
 * 標記，提醒使用者 metadata 已被移除。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { useState } from 'react'
import { apiGet, apiPut } from '@/lib/api-client'
import type { ApiResponse } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/states'

interface SetupBankItem {
  readonly code: string
  readonly display_name: string | null
  readonly enabled: boolean
  readonly has_settings_row: boolean
  readonly metadata_missing: boolean
  readonly total_pdfs: number
  readonly last_ingest_at: string | null
}

const QUERY_KEY = ['setup', 'banks'] as const

function SetupBanksPage() {
  const queryClient = useQueryClient()
  const [mutationError, setMutationError] = useState('')

  const banksQuery = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () =>
      apiGet<ApiResponse<readonly SetupBankItem[]>>('/api/setup/banks'),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ code, enabled }: { code: string; enabled: boolean }) =>
      apiPut<ApiResponse<SetupBankItem>>(`/api/setup/banks/${code}`, {
        enabled,
      }),
    onMutate: async ({ code, enabled }) => {
      setMutationError('')
      await queryClient.cancelQueries({ queryKey: QUERY_KEY })
      const previous = queryClient.getQueryData<
        ApiResponse<readonly SetupBankItem[]>
      >(QUERY_KEY)
      if (previous) {
        queryClient.setQueryData<ApiResponse<readonly SetupBankItem[]>>(
          QUERY_KEY,
          {
            ...previous,
            data: previous.data.map((item) =>
              item.code === code
                ? { ...item, enabled, has_settings_row: true }
                : item,
            ),
          },
        )
      }
      return { previous }
    },
    onError: (error: Error, _vars, ctx) => {
      if (ctx?.previous) {
        queryClient.setQueryData(QUERY_KEY, ctx.previous)
      }
      setMutationError(error.message)
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })

  if (banksQuery.isLoading) return <LoadingState message="讀取銀行設定..." />
  if (banksQuery.isError) {
    return <ErrorState message={(banksQuery.error as Error).message} />
  }
  const items = banksQuery.data?.data ?? []
  if (items.length === 0) {
    return (
      <EmptyState message="尚未初始化銀行設定，請先執行 python -m ccas.tools.bank_configs --apply" />
    )
  }

  const enabledCount = items.filter((b) => b.enabled).length
  const orphanCount = items.filter((b) => b.metadata_missing).length

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold">銀行啟用</h2>
        <p className="text-sm text-muted-foreground">
          已啟用 {enabledCount} / {items.length} 家銀行
          {orphanCount > 0 ? `（含 ${orphanCount} 個孤兒條目）` : ''}
        </p>
      </header>

      {mutationError ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {mutationError}
        </p>
      ) : null}

      <ul className="space-y-2" aria-label="銀行列表">
        {items.map((item) => (
          <li
            key={item.code}
            className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-base font-medium">
                  {item.display_name ?? item.code}
                </span>
                <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                  {item.code}
                </code>
                {item.metadata_missing ? (
                  <span
                    className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300"
                    title="banks.yaml 已無此銀行的 metadata"
                  >
                    <AlertTriangle className="size-3" />
                    孤兒
                  </span>
                ) : null}
              </div>
              <p className="text-xs text-muted-foreground">
                已收 PDF：{item.total_pdfs} 份 ｜ 最後一次：
                {item.last_ingest_at
                  ? new Date(item.last_ingest_at).toLocaleString('zh-TW')
                  : '尚無'}
              </p>
            </div>
            <Button
              variant={item.enabled ? 'secondary' : 'outline'}
              size="sm"
              disabled={
                toggleMutation.isPending &&
                toggleMutation.variables?.code === item.code
              }
              onClick={() =>
                toggleMutation.mutate({
                  code: item.code,
                  enabled: !item.enabled,
                })
              }
              aria-label={`${item.enabled ? '停用' : '啟用'} ${item.code}`}
              aria-pressed={item.enabled}
            >
              {item.enabled ? '已啟用' : '已停用'}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default SetupBanksPage
