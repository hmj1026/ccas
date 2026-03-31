/**
 * App 元件冒煙測試。
 *
 * 驗證根元件可正常渲染，顯示導覽項目。
 */
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import App from './App'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(() => new Promise(() => {})),
}))

describe('App', () => {
  it('renders the sidebar with navigation', async () => {
    render(<App />)
    await waitFor(() => {
      expect(screen.getByText('總覽')).toBeInTheDocument()
    })
    expect(screen.getByText('交易')).toBeInTheDocument()
    expect(screen.getByText('分析')).toBeInTheDocument()
    expect(screen.getByText('帳單')).toBeInTheDocument()
    expect(screen.getByText('設定')).toBeInTheDocument()
  })
})
