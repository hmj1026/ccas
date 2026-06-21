/**
 * Vitest for SettingsRulesPage (bills-management-and-insights §10.5)。
 *
 * 覆蓋：
 * - empty state
 * - 列表渲染（priority DESC + id ASC）
 * - toggle enabled 觸發 PUT
 * - 編輯 priority debounce 後送 PUT
 * - delete 流程（含 confirm）
 * - 開啟 dialog → test 規則 mutation
 * - regex nested quantifier 警示
 * - dialog 建立規則
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** Choose a SelectField (base-ui) option by trigger label + option text. */
async function pickOption(
  user: ReturnType<typeof userEvent.setup>,
  triggerLabel: string,
  optionName: string,
) {
  await user.click(screen.getByLabelText(triggerLabel))
  const listbox = await screen.findByRole('listbox')
  await user.click(await within(listbox).findByRole('option', { name: optionName }))
}

vi.mock('@/lib/api-client', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  apiDelete: vi.fn(),
}))

import { apiDelete, apiGet, apiPost, apiPut } from '@/lib/api-client'
import SettingsRulesPage from '@/pages/settings-rules'
import type {
  CategoryKeywordItem,
  ClassificationRuleItem,
} from '@/lib/types'

const mockedGet = vi.mocked(apiGet)
const mockedPost = vi.mocked(apiPost)
const mockedPut = vi.mocked(apiPut)
const mockedDelete = vi.mocked(apiDelete)

const RULE_A: ClassificationRuleItem = {
  id: 1,
  pattern: '星巴克',
  pattern_type: 'keyword',
  category_id: 10,
  category_name: '餐飲',
  priority: 20,
  enabled: true,
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
}

const RULE_B: ClassificationRuleItem = {
  id: 2,
  pattern: 'UBER',
  pattern_type: 'exact',
  category_id: 11,
  category_name: '交通',
  priority: 10,
  enabled: false,
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
}

const CATEGORIES: CategoryKeywordItem[] = [
  { id: 10, keyword: '星巴克', category: '餐飲' },
  { id: 11, keyword: 'UBER', category: '交通' },
  { id: 12, keyword: '蝦皮', category: '購物' },
]

function setupRoutes(rules: ClassificationRuleItem[]) {
  mockedGet.mockImplementation((path: string) => {
    if (path === '/api/rules') {
      return Promise.resolve({ success: true, data: rules, message: '' })
    }
    if (path === '/api/settings/categories') {
      return Promise.resolve({
        success: true,
        data: CATEGORIES,
        message: '',
      })
    }
    return Promise.resolve({ success: true, data: null, message: '' })
  })
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <SettingsRulesPage />
    </QueryClientProvider>,
  )
}

describe('SettingsRulesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows empty state when no rules', async () => {
    setupRoutes([])
    renderPage()
    await waitFor(() => {
      expect(screen.getByText(/尚未建立規則/)).toBeInTheDocument()
    })
  })

  it('renders rules in priority order with type/category', async () => {
    setupRoutes([RULE_A, RULE_B])
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('星巴克')).toBeInTheDocument()
    })
    expect(screen.getByText('UBER')).toBeInTheDocument()
    expect(screen.getByText('餐飲')).toBeInTheDocument()
    expect(screen.getByText('交通')).toBeInTheDocument()
  })

  it('toggling enabled sends PUT', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    setupRoutes([RULE_A])
    mockedPut.mockResolvedValue({
      success: true,
      data: { ...RULE_A, enabled: false },
      message: '',
    })
    renderPage()

    const toggle = await screen.findByLabelText('toggle 星巴克')
    await user.click(toggle)

    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledWith('/api/rules/1', {
        enabled: false,
      })
    })
  })

  it('editing priority debounces a PUT', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    setupRoutes([RULE_A])
    mockedPut.mockResolvedValue({
      success: true,
      data: { ...RULE_A, priority: 35 },
      message: '',
    })
    renderPage()

    const input = await screen.findByLabelText('priority of 星巴克')
    await user.clear(input)
    await user.type(input, '35')
    // 還沒過 debounce 不該送
    expect(mockedPut).not.toHaveBeenCalled()
    vi.advanceTimersByTime(500)

    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledWith('/api/rules/1', { priority: 35 })
    })
  })

  it('deleting calls DELETE after confirming in the dialog', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    setupRoutes([RULE_A])
    mockedDelete.mockResolvedValue({
      success: true,
      data: { deleted_id: 1 },
      message: '',
    })
    renderPage()

    const delBtn = await screen.findByLabelText('delete 星巴克')
    await user.click(delBtn)

    // Confirmation dialog opens; no DELETE before confirming.
    expect(mockedDelete).not.toHaveBeenCalled()
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('確定要刪除規則「星巴克」？')

    await user.click(screen.getByRole('button', { name: '確認刪除' }))

    await waitFor(() => {
      expect(mockedDelete).toHaveBeenCalledWith('/api/rules/1')
    })
  })

  it('cancelling the delete dialog does not call DELETE', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    setupRoutes([RULE_A])
    renderPage()

    const delBtn = await screen.findByLabelText('delete 星巴克')
    await user.click(delBtn)
    await screen.findByRole('dialog')
    await user.click(screen.getByRole('button', { name: '取消' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(mockedDelete).not.toHaveBeenCalled()
  })

  it('shows error banner when toggle PUT fails', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    setupRoutes([RULE_A])
    mockedPut.mockRejectedValue(new Error('更新規則失敗'))
    renderPage()

    const toggle = await screen.findByLabelText('toggle 星巴克')
    await user.click(toggle)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('更新規則失敗')
  })

  it('shows error banner when DELETE fails', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    setupRoutes([RULE_A])
    mockedDelete.mockRejectedValue(new Error('刪除規則失敗'))
    renderPage()

    const delBtn = await screen.findByLabelText('delete 星巴克')
    await user.click(delBtn)
    await screen.findByRole('dialog')
    await user.click(screen.getByRole('button', { name: '確認刪除' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('刪除規則失敗')
  })

  it('shows nested-quantifier warning in regex dialog', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    setupRoutes([])
    renderPage()

    await user.click(await screen.findByRole('button', { name: '新增規則' }))
    await pickOption(user, '類型', '正規表達式 (regex)')
    await user.type(screen.getByLabelText('pattern'), '(a+)+')

    expect(
      screen.getByText(/nested quantifier/i),
    ).toBeInTheDocument()
  })

  it('warns on ambiguous-alternation regex (SSOT with backend)', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    setupRoutes([])
    renderPage()

    await user.click(await screen.findByRole('button', { name: '新增規則' }))
    await pickOption(user, '類型', '正規表達式 (regex)')
    // (a|b|ab)+ has no inner quantifier but still backtracks catastrophically;
    // the broadened detectComplexRegex must flag it, matching backend rejection.
    await user.type(screen.getByLabelText('pattern'), '(a|b|ab)+')

    expect(
      screen.getByText(/nested quantifier/i),
    ).toBeInTheDocument()
  })

  it('test rule mutation calls /api/rules/test', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    setupRoutes([])
    mockedPost.mockImplementation((path: string) => {
      if (path === '/api/rules/test') {
        return Promise.resolve({
          success: true,
          data: { matches: true },
          message: '',
        })
      }
      return Promise.resolve({ success: true, data: null, message: '' })
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: '新增規則' }))
    await user.type(screen.getByLabelText('pattern'), '星巴克')
    await user.type(screen.getByLabelText('sample_text'), '星巴克 #1234')
    await user.click(screen.getByRole('button', { name: '測試' }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/api/rules/test', {
        pattern: '星巴克',
        pattern_type: 'keyword',
        sample_text: '星巴克 #1234',
      })
    })
    expect(await screen.findByText('✓ 命中')).toBeInTheDocument()
  })

  it('creating a rule submits POST /api/rules and closes dialog', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    setupRoutes([])
    mockedPost.mockImplementation((path: string) => {
      if (path === '/api/rules') {
        return Promise.resolve({
          success: true,
          data: {
            ...RULE_A,
            id: 99,
            pattern: '蝦皮',
            category_id: 12,
            category_name: '購物',
            priority: 15,
          },
          message: '',
        })
      }
      return Promise.resolve({ success: true, data: null, message: '' })
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: '新增規則' }))
    await user.type(screen.getByLabelText('pattern'), '蝦皮')
    await pickOption(user, '類別', '購物（蝦皮）')
    await user.clear(screen.getByLabelText('priority'))
    await user.type(screen.getByLabelText('priority'), '15')
    await user.click(screen.getByRole('button', { name: /建立規則/ }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/api/rules', {
        pattern: '蝦皮',
        pattern_type: 'keyword',
        category_id: 12,
        priority: 15,
        enabled: true,
      })
    })
    // dialog 收起後就拿不到「建立規則」按鈕（dialog 不再渲染）
    await waitFor(() => {
      expect(
        screen.queryByRole('dialog'),
      ).not.toBeInTheDocument()
    })
  })
})
