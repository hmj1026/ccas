/**
 * App 元件冒煙測試。
 *
 * 驗證根元件可正常渲染，並顯示系統名稱與健康狀態。
 */
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the CCAS heading', () => {
    render(<App />)
    expect(screen.getByText('CCAS')).toBeInTheDocument()
  })

  it('shows health status', () => {
    render(<App />)
    expect(screen.getByText('Health: OK')).toBeInTheDocument()
  })
})
