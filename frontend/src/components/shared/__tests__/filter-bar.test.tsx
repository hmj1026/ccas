/**
 * FilterBar 測試 -- 條件渲染、year/month 互斥、各維度 onChange、延遲提交搜尋。
 */
import { fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FilterBar, type FilterBarParams } from '../filter-bar'
import { renderWithProviders } from '@/test-utils'

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
}))

import { apiGet } from '@/lib/api-client'

const mockApiGet = vi.mocked(apiGet)

const EMPTY_VALUES: FilterBarParams = {
  year: '',
  month: '',
  bank: '',
  status: '',
  category: '',
  q: '',
}

const YEARS_RESPONSE = { success: true, data: [2025, 2024], message: '' }

const BANKS_RESPONSE = {
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

// Two keywords share 餐飲 to exercise the category de-dup useMemo.
const CATEGORIES_RESPONSE = {
  success: true,
  data: [
    { id: 1, keyword: 'starbucks', category: '餐飲' },
    { id: 2, keyword: 'mrt', category: '交通' },
    { id: 3, keyword: 'mcd', category: '餐飲' },
  ],
  message: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockApiGet.mockImplementation((path: string) => {
    if (path === '/api/analytics/years') return Promise.resolve(YEARS_RESPONSE)
    if (path === '/api/settings/banks') return Promise.resolve(BANKS_RESPONSE)
    if (path === '/api/settings/categories')
      return Promise.resolve(CATEGORIES_RESPONSE)
    return Promise.reject(new Error(`unexpected path: ${path}`))
  })
})

/**
 * Pick an option from a SelectField (base-ui) by its trigger label and the
 * visible option text. base-ui renders options in a portal listbox on open.
 */
async function pickOption(
  user: ReturnType<typeof userEvent.setup>,
  triggerLabel: string,
  optionName: string,
) {
  await user.click(screen.getByLabelText(triggerLabel))
  const listbox = await screen.findByRole('listbox')
  await user.click(await within(listbox).findByRole('option', { name: optionName }))
}

describe('FilterBar rendering', () => {
  it('renders every configured filter control', () => {
    renderWithProviders(
      <FilterBar
        show={['year', 'month', 'bank', 'status', 'category', 'q']}
        values={EMPTY_VALUES}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByLabelText('年度篩選')).toBeInTheDocument()
    expect(screen.getByLabelText('月份篩選')).toBeInTheDocument()
    expect(screen.getByLabelText('銀行篩選')).toBeInTheDocument()
    expect(screen.getByLabelText('付款狀態篩選')).toBeInTheDocument()
    expect(screen.getByLabelText('分類篩選')).toBeInTheDocument()
    expect(screen.getByLabelText('商家搜尋')).toBeInTheDocument()
  })

  it('renders only the filters listed in show', () => {
    renderWithProviders(
      <FilterBar show={['bank']} values={EMPTY_VALUES} onChange={vi.fn()} />,
    )
    expect(screen.getByLabelText('銀行篩選')).toBeInTheDocument()
    expect(screen.queryByLabelText('年度篩選')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('月份篩選')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('付款狀態篩選')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('分類篩選')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('商家搜尋')).not.toBeInTheDocument()
  })

  it('renders the extra slot', () => {
    renderWithProviders(
      <FilterBar
        show={[]}
        values={EMPTY_VALUES}
        onChange={vi.fn()}
        extra={<button type="button">匯出</button>}
      />,
    )
    expect(screen.getByRole('button', { name: '匯出' })).toBeInTheDocument()
  })
})

describe('FilterBar year/month mutual exclusion', () => {
  it('clears month and sets year when a year is selected', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <FilterBar show={['year']} values={EMPTY_VALUES} onChange={onChange} />,
    )
    await pickOption(user, '年度篩選', '2025 年')
    expect(onChange).toHaveBeenCalledWith('month', '')
    expect(onChange).toHaveBeenCalledWith('year', '2025')
  })

  it('clears the year without touching month when 全部年度 is chosen', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <FilterBar
        show={['year']}
        values={{ ...EMPTY_VALUES, year: '2025' }}
        onChange={onChange}
      />,
    )
    await pickOption(user, '年度篩選', '全部年度')
    expect(onChange).toHaveBeenCalledWith('year', '')
    expect(onChange).not.toHaveBeenCalledWith('month', '')
  })

  it('clears year and sets month when a month is picked', () => {
    const onChange = vi.fn()
    renderWithProviders(
      <FilterBar show={['month']} values={EMPTY_VALUES} onChange={onChange} />,
    )
    fireEvent.change(screen.getByLabelText('月份篩選'), {
      target: { value: '2025-03' },
    })
    expect(onChange).toHaveBeenCalledWith('year', '')
    expect(onChange).toHaveBeenCalledWith('month', '2025-03')
  })

  it('clears the month without touching year when the month input is emptied', () => {
    const onChange = vi.fn()
    renderWithProviders(
      <FilterBar
        show={['month']}
        values={{ ...EMPTY_VALUES, month: '2025-03' }}
        onChange={onChange}
      />,
    )
    fireEvent.change(screen.getByLabelText('月份篩選'), { target: { value: '' } })
    expect(onChange).toHaveBeenCalledWith('month', '')
    expect(onChange).not.toHaveBeenCalledWith('year', '')
  })
})

describe('FilterBar select dimensions', () => {
  it('fires onChange with the bank code', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <FilterBar show={['bank']} values={EMPTY_VALUES} onChange={onChange} />,
    )
    await pickOption(user, '銀行篩選', '中國信託')
    expect(onChange).toHaveBeenCalledWith('bank', 'CTBC')
  })

  it('fires onChange with the status value', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <FilterBar show={['status']} values={EMPTY_VALUES} onChange={onChange} />,
    )
    await pickOption(user, '付款狀態篩選', '已繳')
    expect(onChange).toHaveBeenCalledWith('status', 'paid')
  })

  it('de-duplicates categories and fires onChange with the chosen category', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <FilterBar show={['category']} values={EMPTY_VALUES} onChange={onChange} />,
    )
    await user.click(screen.getByLabelText('分類篩選'))
    const listbox = await screen.findByRole('listbox')
    const options = within(listbox)
      .getAllByRole('option')
      .map((o) => o.textContent)
    expect(options).toEqual(['全部分類', '餐飲', '交通'])

    await user.click(within(listbox).getByRole('option', { name: '餐飲' }))
    expect(onChange).toHaveBeenCalledWith('category', '餐飲')
  })
})

describe('FilterBar debounced search', () => {
  it('commits the trimmed query on blur when it meets the minimum length', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <FilterBar show={['q']} values={EMPTY_VALUES} onChange={onChange} />,
    )
    const input = screen.getByLabelText('商家搜尋')
    await user.type(input, 'sta')
    await user.tab()
    expect(onChange).toHaveBeenCalledWith('q', 'sta')
  })

  it('does not commit a non-empty query shorter than the minimum length', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <FilterBar show={['q']} values={EMPTY_VALUES} onChange={onChange} />,
    )
    const input = screen.getByLabelText('商家搜尋')
    await user.type(input, 'a')
    await user.tab()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('commits the query when Enter is pressed', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <FilterBar show={['q']} values={EMPTY_VALUES} onChange={onChange} />,
    )
    const input = screen.getByLabelText('商家搜尋')
    await user.type(input, 'cafe{Enter}')
    expect(onChange).toHaveBeenCalledWith('q', 'cafe')
  })

  it('does not re-commit when the value is unchanged', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <FilterBar show={['q']} values={EMPTY_VALUES} onChange={onChange} />,
    )
    const input = screen.getByLabelText('商家搜尋')
    await user.type(input, 'cafe{Enter}')
    expect(onChange).toHaveBeenCalledTimes(1)
    // blur with the same committed value -> guard skips a duplicate onChange.
    await user.tab()
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('syncs the input when the external value changes', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    const { rerender } = renderWithProviders(
      <FilterBar show={['q']} values={EMPTY_VALUES} onChange={onChange} />,
    )
    const input = screen.getByLabelText('商家搜尋') as HTMLInputElement
    await user.type(input, 'temp')
    expect(input.value).toBe('temp')

    rerender(
      <FilterBar
        show={['q']}
        values={{ ...EMPTY_VALUES, q: '外部值' }}
        onChange={onChange}
      />,
    )
    expect((screen.getByLabelText('商家搜尋') as HTMLInputElement).value).toBe(
      '外部值',
    )
  })
})
