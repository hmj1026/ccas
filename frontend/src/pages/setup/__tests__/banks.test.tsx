/**
 * Setup banks 頁測試（oauth-onboarding-ui §9.5）。
 *
 * 覆蓋：
 * - 列表渲染（含啟用統計與孤兒 badge）
 * - toggle 觸發 PUT 並樂觀更新
 * - mutation 失敗時顯示錯誤訊息（revert 由 React Query 處理）
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SetupBanksPage from '../banks'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
}))

import { apiGet, apiPut } from '@/lib/api-client'

const mockApiGet = vi.mocked(apiGet)
const mockApiPut = vi.mocked(apiPut)

const baseItems = [
  {
    code: 'CTBC',
    display_name: '中國信託',
    enabled: true,
    has_settings_row: false,
    metadata_missing: false,
    total_pdfs: 5,
    last_ingest_at: '2026-04-15T10:00:00+00:00',
  },
  {
    code: 'HSBC',
    display_name: null,
    enabled: true,
    has_settings_row: true,
    metadata_missing: true,
    total_pdfs: 0,
    last_ingest_at: null,
  },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SetupBanksPage', () => {
  it('renders the bank list with enabled summary and orphan badge', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: baseItems,
      message: '',
    })

    renderWithProviders(<SetupBanksPage />)

    await waitFor(() =>
      expect(screen.getByText('中國信託')).toBeInTheDocument(),
    )
    expect(screen.getByText(/已啟用 2 \/ 2/)).toBeInTheDocument()
    expect(screen.getByText('孤兒')).toBeInTheDocument()
  })

  it('toggles bank enabled state via PUT and refetches updated state', async () => {
    const user = userEvent.setup()
    let currentEnabled = true
    mockApiGet.mockImplementation(() =>
      Promise.resolve({
        success: true,
        data: baseItems.map((item) =>
          item.code === 'CTBC' ? { ...item, enabled: currentEnabled } : item,
        ),
        message: '',
      }),
    )
    mockApiPut.mockImplementation((path: string, body: unknown) => {
      currentEnabled = (body as { enabled: boolean }).enabled
      const item = baseItems.find((i) => path.endsWith(i.code))!
      return Promise.resolve({
        success: true,
        data: { ...item, enabled: currentEnabled, has_settings_row: true },
        message: '',
      })
    })

    renderWithProviders(<SetupBanksPage />)

    const toggle = await screen.findByRole('button', { name: '停用 CTBC' })
    await user.click(toggle)

    await waitFor(() =>
      expect(mockApiPut).toHaveBeenCalledWith('/api/setup/banks/CTBC', {
        enabled: false,
      }),
    )
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: '啟用 CTBC' }),
      ).toBeInTheDocument(),
    )
  })

  it('surfaces mutation error message when PUT fails', async () => {
    const user = userEvent.setup()
    mockApiGet.mockResolvedValue({
      success: true,
      data: baseItems,
      message: '',
    })
    mockApiPut.mockRejectedValue(new Error('伺服器拒絕變更'))

    renderWithProviders(<SetupBanksPage />)

    const toggle = await screen.findByRole('button', { name: /停用 CTBC/ })
    await user.click(toggle)

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('伺服器拒絕變更'),
    )
  })

  it('shows empty state when API returns no banks', async () => {
    mockApiGet.mockResolvedValue({ success: true, data: [], message: '' })

    renderWithProviders(<SetupBanksPage />)

    await waitFor(() =>
      expect(
        screen.getByText(/尚未初始化銀行設定/),
      ).toBeInTheDocument(),
    )
  })
})
