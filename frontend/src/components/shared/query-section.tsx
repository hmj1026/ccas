import type { ReactNode } from 'react'
import type { ApiResponse } from '@/lib/types'
import { LoadingState, ErrorState } from '@/components/shared/states'

export type SectionQuery<T> = {
  readonly isLoading: boolean
  readonly error: Error | null
  readonly isFetching?: boolean
  readonly data?: ApiResponse<readonly T[]>
}

interface QuerySectionProps<T> {
  readonly query: SectionQuery<T>
  /** 提供時於 error 狀態渲染重試按鈕，通常傳入 `() => query.refetch()`。 */
  readonly onRetry?: () => void
  readonly children: (data: readonly T[]) => ReactNode
}

/**
 * 區段 loading/error 統一閘門：
 * 1) `query.isLoading` → `<LoadingState />`
 * 2) `query.error` → `<ErrorState />`（傳入 `onRetry` 時附重試按鈕，
 *    重試中 `query.isFetching` 為 true 則停用按鈕避免重複觸發）
 * 3) 解構 `ApiResponse.data ?? []` 給 children render-prop
 *
 * 各區段查詢彼此獨立，單一 query 失敗只會讓該區段顯示錯誤/重試，
 * 不影響其餘成功區段。子元件可自行處理空陣列（chart 元件已內建 EmptyState）。
 */
export function QuerySection<T>({
  query,
  onRetry,
  children,
}: QuerySectionProps<T>) {
  if (query.isLoading) return <LoadingState />
  if (query.error)
    return (
      <ErrorState
        message={query.error.message}
        onRetry={onRetry}
        isRetrying={query.isFetching ?? false}
      />
    )
  return <>{children(query.data?.data ?? [])}</>
}
