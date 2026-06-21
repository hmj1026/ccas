/**
 * E2E for settings/rules (bills-management-and-insights §10.6)。
 *
 * 全程透過 ``page.route`` mock backend，不依賴真實後端。
 *
 * 涵蓋情境：
 * 1. 列表渲染 + NAV 進入
 * 2. 開啟「新增規則」dialog → 即時 test → 建立 → 列表重新整理
 * 3. toggle enabled
 * 4. regex nested quantifier 警示
 */
import { test, expect, type Page, type Route } from '@playwright/test'

/** Choose a SelectField (base-ui) option: open the listbox then click an item. */
async function pickOption(page: Page, label: string, optionName: string) {
  await page.getByLabel(label).click()
  await page.getByRole('option', { name: optionName }).click()
}

type ApiEnvelope<T> = {
  success: true
  data: T
  message: string
}

function ok<T>(data: T): ApiEnvelope<T> {
  return { success: true, data, message: 'ok' }
}

async function mockAuthenticatedSession(page: Page) {
  await page.route('**/api/auth/session', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ json: ok({ authenticated: true }) })
      return
    }
    await route.fulfill({ json: ok(null) })
  })
}

const RULE = {
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

const CATEGORIES = [
  { id: 10, keyword: '星巴克', category: '餐飲' },
  { id: 11, keyword: 'UBER', category: '交通' },
  { id: 12, keyword: '蝦皮', category: '購物' },
]

async function setupRoutes(
  page: Page,
  state: { rules: typeof RULE[] },
) {
  await mockAuthenticatedSession(page)

  await page.route('**/api/settings/categories', async (route) => {
    await route.fulfill({ json: ok(CATEGORIES) })
  })

  await page.route('**/api/rules**', async (route: Route) => {
    const url = new URL(route.request().url())
    const method = route.request().method()

    // /api/rules/test
    if (url.pathname.endsWith('/api/rules/test') && method === 'POST') {
      const body = JSON.parse(route.request().postData() ?? '{}') as {
        pattern: string
        sample_text: string
      }
      const matches = body.sample_text.includes(body.pattern)
      await route.fulfill({ json: ok({ matches }) })
      return
    }

    // /api/rules/<id>
    const idMatch = url.pathname.match(/\/api\/rules\/(\d+)$/)
    if (idMatch) {
      const id = Number(idMatch[1])
      if (method === 'PUT') {
        const body = JSON.parse(
          route.request().postData() ?? '{}',
        ) as Record<string, unknown>
        const idx = state.rules.findIndex((r) => r.id === id)
        if (idx >= 0) {
          state.rules[idx] = { ...state.rules[idx], ...body }
        }
        await route.fulfill({ json: ok(state.rules[idx]) })
        return
      }
      if (method === 'DELETE') {
        state.rules = state.rules.filter((r) => r.id !== id)
        await route.fulfill({ json: ok({ deleted_id: id }) })
        return
      }
    }

    // /api/rules（list / create）
    if (url.pathname.endsWith('/api/rules')) {
      if (method === 'GET') {
        await route.fulfill({ json: ok(state.rules) })
        return
      }
      if (method === 'POST') {
        const body = JSON.parse(
          route.request().postData() ?? '{}',
        ) as Record<string, unknown>
        const created = {
          ...RULE,
          id: state.rules.length + 1,
          ...body,
          category_name:
            CATEGORIES.find((c) => c.id === body.category_id)?.category ??
            '未知',
        }
        state.rules = [...state.rules, created]
        await route.fulfill({ json: ok(created) })
        return
      }
    }

    await route.fulfill({ status: 404 })
  })
}

test.describe('Classification rules settings page', () => {
  test('lists rules from NAV and toggles enabled', async ({ page }) => {
    const state = { rules: [{ ...RULE }] }
    await setupRoutes(page, state)
    await page.goto('/overview')

    await page.getByRole('link', { name: '分類規則' }).first().click()
    await expect(page).toHaveURL(/\/settings\/rules/)

    await expect(page.getByText('星巴克')).toBeVisible()
    await expect(page.getByText('餐飲')).toBeVisible()

    // toggle off
    await page.getByLabel('toggle 星巴克').click()
    await expect.poll(() => state.rules[0].enabled).toBe(false)
  })

  test('create new rule via dialog with live test', async ({ page }) => {
    const state = { rules: [] as typeof RULE[] }
    await setupRoutes(page, state)
    await page.goto('/settings/rules')

    await expect(page.getByText(/尚未建立規則/)).toBeVisible()
    await page.getByRole('button', { name: '新增規則' }).click()

    await expect(page.getByRole('dialog')).toBeVisible()
    // 用 textbox role 精準鎖定 pattern 輸入框，避開同樣 aria-label 前綴的 pattern 欄位。
    await page.getByRole('textbox', { name: 'pattern' }).fill('蝦皮')
    await pickOption(page, '類別', '購物（蝦皮）')

    // 即時測試
    await page.getByLabel('sample_text').fill('蝦皮商城 #001')
    await page.getByRole('button', { name: '測試' }).click()
    await expect(page.getByText('✓ 命中')).toBeVisible()

    await page.getByRole('button', { name: /建立規則/ }).click()
    // dialog 收起 + 列表重新整理顯示新規則
    await expect(page.getByRole('dialog')).toBeHidden()
    await expect(page.getByText('蝦皮')).toBeVisible()
  })

  test('regex nested quantifier shows warning banner', async ({ page }) => {
    const state = { rules: [] as typeof RULE[] }
    await setupRoutes(page, state)
    await page.goto('/settings/rules')

    await page.getByRole('button', { name: '新增規則' }).click()
    await pickOption(page, '類型', '正規表達式 (regex)')
    await page.getByRole('textbox', { name: 'pattern' }).fill('(a+)+')

    await expect(page.getByText(/nested quantifier/i)).toBeVisible()
  })
})
