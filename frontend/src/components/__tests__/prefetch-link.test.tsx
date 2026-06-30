/**
 * PrefetchLink 測試 -- 渲染 NavLink、hover/focus 觸發一次預載、失敗後可重試。
 */
import { fireEvent, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { PrefetchLink } from '../prefetch-link'
import { renderWithProviders } from '@/test-utils'

describe('PrefetchLink', () => {
  it('renders the link with children and href', () => {
    const onPrefetch = vi.fn().mockResolvedValue(undefined)
    renderWithProviders(
      <PrefetchLink to="/overview" onPrefetch={onPrefetch}>
        總覽
      </PrefetchLink>,
    )
    const link = screen.getByRole('link', { name: '總覽' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/overview')
  })

  it('prefetches once on mouse enter and ignores repeat triggers', () => {
    const onPrefetch = vi.fn().mockResolvedValue(undefined)
    renderWithProviders(
      <PrefetchLink to="/overview" onPrefetch={onPrefetch}>
        總覽
      </PrefetchLink>,
    )
    const link = screen.getByRole('link', { name: '總覽' })
    fireEvent.mouseEnter(link)
    fireEvent.mouseEnter(link)
    fireEvent.focus(link)
    expect(onPrefetch).toHaveBeenCalledTimes(1)
  })

  it('prefetches on focus', () => {
    const onPrefetch = vi.fn().mockResolvedValue(undefined)
    renderWithProviders(
      <PrefetchLink to="/overview" onPrefetch={onPrefetch}>
        總覽
      </PrefetchLink>,
    )
    fireEvent.focus(screen.getByRole('link', { name: '總覽' }))
    expect(onPrefetch).toHaveBeenCalledTimes(1)
  })

  it('allows a retry after a failed prefetch', async () => {
    const onPrefetch = vi
      .fn()
      .mockRejectedValueOnce(new Error('chunk error'))
      .mockResolvedValue(undefined)
    renderWithProviders(
      <PrefetchLink to="/overview" onPrefetch={onPrefetch}>
        總覽
      </PrefetchLink>,
    )
    const link = screen.getByRole('link', { name: '總覽' })

    fireEvent.mouseEnter(link)
    expect(onPrefetch).toHaveBeenCalledTimes(1)

    // Let the rejected promise's catch reset the guard flag.
    await Promise.resolve()
    await Promise.resolve()

    fireEvent.mouseEnter(link)
    expect(onPrefetch).toHaveBeenCalledTimes(2)
  })
})
