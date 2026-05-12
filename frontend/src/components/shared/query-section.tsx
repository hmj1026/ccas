import type { ReactNode } from 'react'
import type { ApiResponse } from '@/lib/types'
import { LoadingState, ErrorState } from '@/components/shared/states'

export type SectionQuery<T> = {
  readonly isLoading: boolean
  readonly error: Error | null
  readonly data?: ApiResponse<readonly T[]>
}

interface QuerySectionProps<T> {
  readonly query: SectionQuery<T>
  readonly children: (data: readonly T[]) => ReactNode
}

/**
 * 區段 loading/error 統一閘門：
 * 1) `query.isLoading` → `<LoadingState />`
 * 2) `query.error` → `<ErrorState />`
 * 3) 解構 `ApiResponse.data ?? []` 給 children render-prop
 *
 * 子元件可自行處理空陣列（例如 chart 元件已內建 EmptyState）。
 */
export function QuerySection<T>({ query, children }: QuerySectionProps<T>) {
  if (query.isLoading) return <LoadingState />
  if (query.error) return <ErrorState message={query.error.message} />
  return <>{children(query.data?.data ?? [])}</>
}
