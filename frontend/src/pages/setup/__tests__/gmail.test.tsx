/**
 * Gmail OAuth 設定頁測試（oauth-onboarding-ui §8.8）。
 *
 * Mock fetch 與 apiGet/apiPost；覆蓋三條主路徑：
 * - 未連線時顯示三步驟 step card
 * - 已連線時顯示 connected view + revoke
 * - revoke 後 invalidate status
 *
 * Authorize 按鈕不在此測試實際跳轉（會觸發 window.location.href，由 Playwright 覆蓋）。
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GmailSetupPage from '../gmail'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

import { apiGet, apiPost } from '@/lib/api-client'

const mockApiGet = vi.mocked(apiGet)
const mockApiPost = vi.mocked(apiPost)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('GmailSetupPage', () => {
  it('shows three-step setup when not connected', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: { connected: false, email: null, granted_scopes: [] },
      message: '',
    })

    renderWithProviders(<GmailSetupPage />, { initialEntries: ['/setup/gmail'] })

    await waitFor(() => {
      expect(screen.getByText('上傳 credentials.json')).toBeInTheDocument()
    })
    expect(screen.getByText('確認 redirect URI')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '授權 Google' })).toBeDisabled()
  })

  it('renders connected view with scopes when connected', async () => {
    mockApiGet.mockResolvedValue({
      success: true,
      data: {
        connected: true,
        email: 'paul@example.com',
        granted_scopes: ['https://www.googleapis.com/auth/gmail.readonly'],
      },
      message: '',
    })

    renderWithProviders(<GmailSetupPage />, { initialEntries: ['/setup/gmail'] })

    await waitFor(() => {
      expect(screen.getByText('Gmail 已連線')).toBeInTheDocument()
    })
    expect(screen.getByText('paul@example.com')).toBeInTheDocument()
    expect(
      screen.getByText('https://www.googleapis.com/auth/gmail.readonly'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '解除 Gmail 連線' }),
    ).toBeInTheDocument()
  })

  it('calls revoke API when user confirms in dialog', async () => {
    const user = userEvent.setup()
    mockApiGet.mockResolvedValue({
      success: true,
      data: {
        connected: true,
        email: 'paul@example.com',
        granted_scopes: [],
      },
      message: '',
    })
    mockApiPost.mockResolvedValue({
      success: true,
      data: { connected: false, email: null, granted_scopes: [] },
      message: '',
    })

    renderWithProviders(<GmailSetupPage />, { initialEntries: ['/setup/gmail'] })

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: '解除 Gmail 連線' }),
      ).toBeInTheDocument(),
    )

    await user.click(screen.getByRole('button', { name: '解除 Gmail 連線' }))
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: '確認解除連線' }),
      ).toBeInTheDocument(),
    )

    await user.click(screen.getByRole('button', { name: '確認解除連線' }))
    await waitFor(() =>
      expect(mockApiPost).toHaveBeenCalledWith('/api/setup/gmail/revoke', {}),
    )
  })
})
