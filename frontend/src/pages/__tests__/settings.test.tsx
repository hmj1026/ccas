/**
 * Settings 頁面測試 -- 銀行設定、分類關鍵字 CRUD 與 mutation/refetch。
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import SettingsPage from '../settings'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}))

import { apiGet, apiPost, apiDelete } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)
const mockApiPost = vi.mocked(apiPost)
const mockApiDelete = vi.mocked(apiDelete)

const MOCK_CATEGORIES = {
  success: true,
  data: [
    { id: 1, keyword: 'starbucks', category: '餐飲' },
  ],
  message: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApiGet.mockResolvedValue(MOCK_CATEGORIES)
})

describe('SettingsPage', () => {
  it('renders the category keyword section', async () => {
    renderWithProviders(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByText('starbucks')).toBeInTheDocument()
    })
    expect(screen.getByText('餐飲')).toBeInTheDocument()
  })

  it('creates a new category keyword', async () => {
    const user = userEvent.setup()
    mockApiPost.mockResolvedValue({
      success: true,
      data: { id: 2, keyword: 'uber', category: '交通' },
      message: '',
    })

    renderWithProviders(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByText('starbucks')).toBeInTheDocument()
    })

    await user.type(screen.getByLabelText('新增關鍵字'), 'uber')
    await user.type(screen.getByLabelText('新增分類'), '交通')
    await user.click(screen.getByLabelText('新增分類規則'))

    expect(mockApiPost).toHaveBeenCalledWith('/api/settings/categories', {
      keyword: 'uber',
      category: '交通',
    })
  })

  it('deletes a category keyword after confirming in the dialog', async () => {
    const user = userEvent.setup()
    mockApiDelete.mockResolvedValue({ success: true, data: null, message: '' })

    renderWithProviders(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByText('starbucks')).toBeInTheDocument()
    })

    await user.click(screen.getByLabelText('刪除 starbucks'))

    // Confirmation dialog opens; no DELETE before confirming.
    expect(mockApiDelete).not.toHaveBeenCalled()
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('不影響歷史交易分類')

    await user.click(screen.getByRole('button', { name: '確認刪除' }))

    expect(mockApiDelete).toHaveBeenCalledWith('/api/settings/categories/1')
  })

  it('does not delete when the confirmation dialog is cancelled', async () => {
    const user = userEvent.setup()
    mockApiDelete.mockResolvedValue({ success: true, data: null, message: '' })

    renderWithProviders(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByText('starbucks')).toBeInTheDocument()
    })

    await user.click(screen.getByLabelText('刪除 starbucks'))
    await screen.findByRole('dialog')
    await user.click(screen.getByRole('button', { name: '取消' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(mockApiDelete).not.toHaveBeenCalled()
  })

  it('shows error banner when category deletion fails', async () => {
    const user = userEvent.setup()
    mockApiDelete.mockRejectedValue(new Error('刪除分類失敗'))

    renderWithProviders(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByText('starbucks')).toBeInTheDocument()
    })

    await user.click(screen.getByLabelText('刪除 starbucks'))
    await screen.findByRole('dialog')
    await user.click(screen.getByRole('button', { name: '確認刪除' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('刪除分類失敗')
  })

  it('shows empty state when no categories', async () => {
    mockApiGet.mockResolvedValue({ success: true, data: [], message: '' })

    renderWithProviders(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByText('尚無分類關鍵字')).toBeInTheDocument()
    })
  })
})
