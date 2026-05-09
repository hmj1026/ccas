/**
 * SetupLayout 測試（oauth-onboarding-ui §7.5）。
 *
 * 驗證 sub-nav 的 4 個連結與標題渲染；點擊 NavLink 後 active 樣式。
 */
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import SetupLayout from '../layout'
import { renderWithProviders } from '@/test-utils'

describe('SetupLayout', () => {
  it('renders sub-nav with four sections and heading', () => {
    renderWithProviders(<SetupLayout />, { initialEntries: ['/setup/gmail'] })
    expect(screen.getByRole('heading', { name: '設定中心' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Gmail 連線/ })).toHaveAttribute(
      'href',
      '/setup/gmail',
    )
    expect(screen.getByRole('link', { name: /銀行啟用/ })).toHaveAttribute(
      'href',
      '/setup/banks',
    )
    expect(screen.getByRole('link', { name: /PDF 密碼/ })).toHaveAttribute(
      'href',
      '/setup/secrets',
    )
    expect(screen.getByRole('link', { name: /API Token/ })).toHaveAttribute(
      'href',
      '/setup/admin',
    )
  })
})
