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
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}))

import { apiGet, apiPost, apiPatch, apiDelete } from '@/lib/api-client'
const mockApiGet = vi.mocked(apiGet)
const mockApiPost = vi.mocked(apiPost)
const mockApiPatch = vi.mocked(apiPatch)
const mockApiDelete = vi.mocked(apiDelete)

const MOCK_BANKS = {
  success: true,
  data: [
    {
      id: 1,
      bank_code: 'CTBC',
      bank_name: '中國信託',
      gmail_filter: 'from:ctbc',
      active_parser_version: 'v1',
      is_active: true,
    },
  ],
  message: '',
}

const MOCK_CATEGORIES = {
  success: true,
  data: [
    { id: 1, keyword: 'starbucks', category: '餐飲' },
  ],
  message: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApiGet.mockImplementation((path: string) => {
    if (path.includes('banks')) return Promise.resolve(MOCK_BANKS)
    return Promise.resolve(MOCK_CATEGORIES)
  })
})

describe('SettingsPage', () => {
  it('renders bank config and category sections', async () => {
    renderWithProviders(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByText('中國信託')).toBeInTheDocument()
    })
    expect(screen.getByText('starbucks')).toBeInTheDocument()
    expect(screen.getByText('餐飲')).toBeInTheDocument()
  })

  it('toggles bank active status', async () => {
    const user = userEvent.setup()
    mockApiPatch.mockResolvedValue({
      success: true,
      data: { ...MOCK_BANKS.data[0], is_active: false },
      message: '',
    })

    renderWithProviders(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByText('啟用中')).toBeInTheDocument()
    })

    await user.click(screen.getByLabelText('停用銀行'))

    expect(mockApiPatch).toHaveBeenCalledWith('/api/settings/banks/1', {
      is_active: false,
    })
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
    mockApiGet.mockImplementation((path: string) => {
      if (path.includes('banks')) return Promise.resolve(MOCK_BANKS)
      return Promise.resolve({ success: true, data: [], message: '' })
    })

    renderWithProviders(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByText('尚無分類關鍵字')).toBeInTheDocument()
    })
  })
})
