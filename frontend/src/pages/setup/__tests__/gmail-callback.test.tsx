/**
 * Gmail OAuth 回呼頁測試（oauth-onboarding-ui §8.4）。
 *
 * 覆蓋三條分支：
 * - 成功路徑：讀取 code/state 後 window.location.replace 轉發至後端 callback
 * - 錯誤路徑：error param 存在時顯示錯誤狀態 + 回設定頁連結
 * - 缺參數路徑：無 code/state 時 Navigate 重導，不顯示狀態也不轉發
 */
import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import GmailCallbackPage from '../gmail-callback'
import { renderWithProviders } from '@/test-utils'

// jsdom 的 window.location.replace 不可重新定義且未實作導航；整段替換為
// 含 replace mock 的 stub，測試結束後還原，以便斷言轉發目標。
const replaceMock = vi.fn()
const originalLocation = window.location

beforeEach(() => {
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: {
      origin: originalLocation.origin,
      href: originalLocation.href,
      replace: replaceMock,
      assign: vi.fn(),
    },
  })
})

afterEach(() => {
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: originalLocation,
  })
  replaceMock.mockReset()
})

describe('GmailCallbackPage', () => {
  it('forwards code and state to the backend callback on the success path', async () => {
    renderWithProviders(<GmailCallbackPage />, {
      initialEntries: ['/setup/gmail/callback?code=abc&state=xyz'],
    })

    expect(screen.getByText('正在完成授權，請稍候...')).toBeInTheDocument()
    await waitFor(() =>
      expect(replaceMock).toHaveBeenCalledWith(
        '/api/setup/gmail/callback?code=abc&state=xyz',
      ),
    )
  })

  it('renders the error branch when Google reports an error param', () => {
    renderWithProviders(<GmailCallbackPage />, {
      initialEntries: ['/setup/gmail/callback?error=access_denied'],
    })

    expect(
      screen.getByText('Google 回報授權失敗：access_denied'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: '回到 Gmail 設定頁' }),
    ).toBeInTheDocument()
    expect(replaceMock).not.toHaveBeenCalled()
  })

  it('does not forward or show status when code/state are missing', () => {
    renderWithProviders(<GmailCallbackPage />, {
      initialEntries: ['/setup/gmail/callback'],
    })

    expect(
      screen.queryByText('正在完成授權，請稍候...'),
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/Google 回報授權失敗/)).not.toBeInTheDocument()
    expect(replaceMock).not.toHaveBeenCalled()
  })
})
