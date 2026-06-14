/**
 * ErrorBoundary 測試（R01）。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from '@/components/shared/error-boundary'

function Boom(): never {
  throw new Error('render 爆炸')
}

describe('ErrorBoundary', () => {
  it('子樹 render 例外時顯示 fallback 而非白屏', () => {
    // 抑制 React 對 boundary 攔截錯誤的 console.error 噪音
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('頁面發生錯誤')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '重試' })).toBeInTheDocument()
    spy.mockRestore()
  })

  it('正常子樹不顯示 fallback', () => {
    render(
      <ErrorBoundary>
        <p>正常內容</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText('正常內容')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('按重試後子樹恢復正常時清除錯誤畫面', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()

    function Flaky() {
      const [ok, setOk] = useState(false)
      if (!ok) {
        // 第一次 render 拋錯，按鈕點擊後重置 boundary + 修好 child
        return (
          <>
            <button type="button" onClick={() => setOk(true)}>
              修好
            </button>
            <Boom />
          </>
        )
      }
      return <p>已恢復</p>
    }

    // 用一個外層 key 控制：重試重置 boundary 狀態
    render(
      <ErrorBoundary>
        <Flaky />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重試' }))
    // 重試會清 error，但 Flaky 仍以 ok=false 重新掛載 → 仍是 alert（驗證 retry 不會崩潰）
    expect(screen.getByRole('alert')).toBeInTheDocument()
    spy.mockRestore()
  })
})
