import { useRef } from 'react'
import { NavLink, type NavLinkProps } from 'react-router'

interface PrefetchLinkProps extends NavLinkProps {
  /**
   * 此 factory 應與 `route-imports.ts` 共用同一個 dynamic import specifier；
   * rolldown 依此 dedup chunk，使 hover 預載的 module 在點擊時被 `lazy()`
   * 直接取用，避免二次下載。
   */
  readonly onPrefetch: () => Promise<unknown>
}

/**
 * 在 hover/focus 時預載 lazy route chunk 的 NavLink wrapper。
 *
 * 透過 ref 旗標保證每個元件實體只觸發一次預載；若預載失敗會允許下次再試。
 * 注意：欄位命名為 `onPrefetch` 以避開 React Router 7 自帶的 `prefetch` prop。
 */
export function PrefetchLink({ onPrefetch, ...props }: PrefetchLinkProps) {
  const triggered = useRef(false)

  const handlePrefetch = () => {
    if (triggered.current) return
    triggered.current = true
    onPrefetch().catch(() => {
      triggered.current = false
    })
  }

  return (
    <NavLink
      {...props}
      onMouseEnter={handlePrefetch}
      onFocus={handlePrefetch}
    />
  )
}
