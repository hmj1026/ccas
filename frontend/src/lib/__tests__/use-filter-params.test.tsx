/**
 * useFilterParams 測試 -- 驗證 URL search-param 變更的所有分支：
 * 一般 key 設定、bank → bank_code 別名、空值刪除、resetPage 對 page 的處理。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, useSearchParams } from 'react-router'
import type { FilterKey } from '@/components/shared/filter-bar'
import { useFilterParams } from '@/lib/use-filter-params'

interface HarnessProps {
  readonly resetPage?: boolean
  readonly paramKey: FilterKey
  readonly value: string
}

function Harness({ resetPage = false, paramKey, value }: HarnessProps) {
  const setFilter = useFilterParams(resetPage)
  const [params] = useSearchParams()
  return (
    <>
      <output data-testid="search">{params.toString()}</output>
      <button type="button" onClick={() => setFilter(paramKey, value)}>
        set
      </button>
    </>
  )
}

function renderHarness(props: HarnessProps, initialEntry = '/') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Harness {...props} />
    </MemoryRouter>,
  )
}

function searchString() {
  return screen.getByTestId('search').textContent ?? ''
}

describe('useFilterParams', () => {
  it('sets a normal key as a search param', async () => {
    const user = userEvent.setup()
    renderHarness({ paramKey: 'year', value: '2026' })
    await user.click(screen.getByRole('button', { name: 'set' }))
    expect(searchString()).toBe('year=2026')
  })

  it('aliases the bank key to bank_code', async () => {
    const user = userEvent.setup()
    renderHarness({ paramKey: 'bank', value: 'CTBC' })
    await user.click(screen.getByRole('button', { name: 'set' }))
    expect(searchString()).toBe('bank_code=CTBC')
  })

  it('deletes the param when the value is empty', async () => {
    const user = userEvent.setup()
    renderHarness({ paramKey: 'category', value: '' }, '/?category=food')
    await user.click(screen.getByRole('button', { name: 'set' }))
    expect(searchString()).toBe('')
  })

  it('deletes page when resetPage is true', async () => {
    const user = userEvent.setup()
    renderHarness({ resetPage: true, paramKey: 'year', value: '2026' }, '/?page=3')
    await user.click(screen.getByRole('button', { name: 'set' }))
    const params = new URLSearchParams(searchString())
    expect(params.has('page')).toBe(false)
    expect(params.get('year')).toBe('2026')
  })

  it('keeps page when resetPage is false', async () => {
    const user = userEvent.setup()
    renderHarness({ resetPage: false, paramKey: 'year', value: '2026' }, '/?page=3')
    await user.click(screen.getByRole('button', { name: 'set' }))
    const params = new URLSearchParams(searchString())
    expect(params.get('page')).toBe('3')
    expect(params.get('year')).toBe('2026')
  })
})
