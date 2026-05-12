import { useCallback } from 'react'
import { useSearchParams } from 'react-router'
import type { FilterKey } from '@/components/shared/filter-bar'

/**
 * URL search-param 變更 callback hook。
 *
 * 集中 `bank → bank_code` 別名與分頁重置，避免每個頁面重複實作。
 *
 * @param resetPage - 變更篩選時是否清除 `page` 參數（列表頁需要）
 */
export function useFilterParams(
  resetPage = false,
): (key: FilterKey, value: string) => void {
  const [, setSearchParams] = useSearchParams()
  return useCallback(
    (key, value) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        const paramKey = key === 'bank' ? 'bank_code' : key
        if (value) next.set(paramKey, value)
        else next.delete(paramKey)
        if (resetPage) next.delete('page')
        return next
      })
    },
    [setSearchParams, resetPage],
  )
}
