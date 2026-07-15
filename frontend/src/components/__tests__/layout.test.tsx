/**
 * Layout 測試 -- 導覽連結、active 路由標記、行動選單開關、登出。
 */
import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Layout from '../layout'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiDelete: vi.fn(),
}))

import { apiDelete } from '@/lib/api-client'
const mockApiDelete = vi.mocked(apiDelete)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Layout', () => {
  it('renders all navigation groups and links', () => {
    renderWithProviders(<Layout />, { initialEntries: ['/overview'] })

    expect(screen.getByText('主要功能')).toBeInTheDocument()
    expect(screen.getByText('操作')).toBeInTheDocument()
    expect(screen.getByText('設定')).toBeInTheDocument()

    expect(screen.getByRole('link', { name: '總覽' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '交易' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '消費分析' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '帳單' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '操作中心' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '預算' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '設定中心' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登出' })).toBeInTheDocument()
  })

  it('marks the current route link as active', () => {
    renderWithProviders(<Layout />, { initialEntries: ['/overview'] })
    const active = screen.getByRole('link', { name: '總覽' })
    expect(active).toHaveAttribute('aria-current', 'page')
    // A non-active link carries no aria-current.
    expect(
      screen.getByRole('link', { name: '交易' }),
    ).not.toHaveAttribute('aria-current')
  })

  it('opens the mobile menu and closes it via the overlay click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Layout />, { initialEntries: ['/overview'] })

    // Only the sidebar X button matches before opening.
    expect(
      screen.getAllByRole('button', { name: 'Close navigation' }),
    ).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: 'Open navigation' }))

    // Overlay adds a second "Close navigation" control.
    const closers = screen.getAllByRole('button', { name: 'Close navigation' })
    expect(closers).toHaveLength(2)

    // Overlay is rendered first in the DOM order.
    await user.click(closers[0])
    await waitFor(() => {
      expect(
        screen.getAllByRole('button', { name: 'Close navigation' }),
      ).toHaveLength(1)
    })
  })

  it('closes the mobile menu when Escape is pressed on the overlay', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Layout />, { initialEntries: ['/overview'] })

    await user.click(screen.getByRole('button', { name: 'Open navigation' }))
    const overlay = screen.getAllByRole('button', {
      name: 'Close navigation',
    })[0]
    fireEvent.keyDown(overlay, { key: 'Escape' })

    await waitFor(() => {
      expect(
        screen.getAllByRole('button', { name: 'Close navigation' }),
      ).toHaveLength(1)
    })
  })

  it('closes the mobile menu via the sidebar X button', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Layout />, { initialEntries: ['/overview'] })

    await user.click(screen.getByRole('button', { name: 'Open navigation' }))
    // [overlay, sidebar X button] — close via the trailing X button.
    const closers = screen.getAllByRole('button', { name: 'Close navigation' })
    await user.click(closers[closers.length - 1])

    await waitFor(() => {
      expect(
        screen.getAllByRole('button', { name: 'Close navigation' }),
      ).toHaveLength(1)
    })
  })

  it('closes the mobile menu when a nav link is clicked', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Layout />, { initialEntries: ['/overview'] })

    await user.click(screen.getByRole('button', { name: 'Open navigation' }))
    expect(
      screen.getAllByRole('button', { name: 'Close navigation' }),
    ).toHaveLength(2)

    await user.click(screen.getByRole('link', { name: '交易' }))
    await waitFor(() => {
      expect(
        screen.getAllByRole('button', { name: 'Close navigation' }),
      ).toHaveLength(1)
    })
  })

  it('calls the logout endpoint when 登出 is clicked', async () => {
    mockApiDelete.mockResolvedValue({ success: true, data: null, message: '' })
    const user = userEvent.setup()
    renderWithProviders(<Layout />, { initialEntries: ['/overview'] })

    await user.click(screen.getByRole('button', { name: '登出' }))
    await waitFor(() => {
      expect(mockApiDelete).toHaveBeenCalledWith('/api/auth/session')
    })
  })
})
