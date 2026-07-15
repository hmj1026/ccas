/**
 * ``transaction-detail.tsx`` 的資料 + 編輯狀態 hook。
 *
 * 封裝 detail / categories 查詢，並將 ``createTransactionEditController``
 * 接上 React Query 快取與 ``useSyncExternalStore``，回傳頁面可直接消費的
 * 扁平 view model。
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useSyncExternalStore } from 'react'
import { createTransactionEditController } from '@/lib/transaction-edit'
import { apiDelete, apiGet, apiPatch } from '@/lib/api-client'
import type {
  ApiResponse,
  CategoryKeywordItem,
  TransactionDetailItem,
} from '@/lib/types'

export function useTransactionEdit(transactionId: number) {
  const queryClient = useQueryClient()

  const detailQueryKey = ['transactions', transactionId, 'detail'] as const

  const { data, isLoading, error, refetch, isFetching } = useQuery({
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

  const controller = useMemo(
    () =>
      createTransactionEditController({
        patch: (body) =>
          apiPatch<ApiResponse<TransactionDetailItem>>(
            `/api/transactions/${transactionId}`,
            body,
          ),
        reset: () =>
          apiDelete<ApiResponse<TransactionDetailItem>>(
            `/api/transactions/${transactionId}/manual-override`,
          ),
        setCache: (resp) => {
          queryClient.setQueryData(detailQueryKey, resp)
        },
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- detailQueryKey 為衍生自 transactionId 的穩定 tuple，刻意省略避免每 render 重建 controller
    [transactionId, queryClient],
  )

  // Sync latest server detail into the controller during render (no notify).
  controller.syncServerDetail(detail)

  const editState = useSyncExternalStore(
    controller.subscribe,
    controller.getSnapshot,
  )

  useEffect(() => {
    return () => controller.dispose()
  }, [controller])

  return {
    detail,
    categories: categoriesData?.data ?? [],
    isLoading,
    queryError: error,
    refetch,
    isFetching,
    saveStatus: editState.saveStatus,
    error: editState.error,
    isResetting: editState.isResetting,
    noteValue: controller.noteValue(),
    aliasValue: controller.aliasValue(),
    tagInput: editState.tagInput,
    setNoteDraft: controller.setNoteDraft,
    flushNote: controller.flushNote,
    setAliasDraft: controller.setAliasDraft,
    flushAlias: controller.flushAlias,
    setTagInput: controller.setTagInput,
    changeCategory: controller.changeCategory,
    addTag: controller.addTag,
    removeTag: controller.removeTag,
    resetOverride: controller.resetOverride,
  }
}
