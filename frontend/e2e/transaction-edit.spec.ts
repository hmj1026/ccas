/**
 * E2E（bills-management-and-insights §9.10）：
 * 列表 → 編輯 → 改 category → 重整保留 → 重跑 pipeline 不被覆寫。
 *
 * 全程透過 ``page.route`` mock backend，不依賴真實後端啟動。
 */
import { test, expect, type Page } from '@playwright/test'

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

const BASE_DETAIL = {
  id: 42,
  bill_id: 7,
  trans_date: '2026-03-15',
  posting_date: null,
  merchant: 'Starbucks',
  amount: 150,
  currency: 'TWD',
  original_amount: null,
  card_last4: '1234',
  category: '餐飲',
  bank_code: 'CTBC',
  billing_month: '2026-03',
  note: null,
  manual_category_override: false,
  tags: [] as readonly string[],
  merchant_alias: '',
  updated_at: '2026-03-16T10:00:00',
}

const CATEGORIES = [
  { id: 1, keyword: '星巴克', category: '餐飲' },
  { id: 2, keyword: '購物-key', category: '購物' },
]

async function setupRoutes(page: Page, state: { detail: typeof BASE_DETAIL }) {
  await mockAuthenticatedSession(page)

  await page.route('**/api/settings/categories', async (route) => {
    await route.fulfill({ json: ok(CATEGORIES) })
  })
  await page.route('**/api/transactions?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: [
          {
            id: state.detail.id,
            bill_id: state.detail.bill_id,
            trans_date: state.detail.trans_date,
            posting_date: state.detail.posting_date,
            merchant: state.detail.merchant,
            amount: state.detail.amount,
            currency: state.detail.currency,
            original_amount: state.detail.original_amount,
            card_last4: state.detail.card_last4,
            category: state.detail.category,
            bank_code: state.detail.bank_code,
            billing_month: state.detail.billing_month,
          },
        ],
        message: 'ok',
        pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
      }),
    })
  })

  // detail GET / PUT / DELETE manual-override
  await page.route('**/api/transactions/42', async (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({ json: ok(state.detail) })
      return
    }
    if (method === 'PUT') {
      const body = JSON.parse(route.request().postData() ?? '{}') as Record<
        string,
        unknown
      >
      const updated: typeof BASE_DETAIL = {
        ...state.detail,
        ...(body.note !== undefined ? { note: body.note as string } : {}),
        ...(body.tags !== undefined
          ? { tags: body.tags as readonly string[] }
          : {}),
        ...(body.merchant_alias !== undefined
          ? { merchant_alias: body.merchant_alias as string }
          : {}),
      }
      if (typeof body.category_id === 'number') {
        const cat = CATEGORIES.find((c) => c.id === body.category_id)
        if (cat) {
          updated.category = cat.category
          updated.manual_category_override = true
        }
      }
      state.detail = updated
      await route.fulfill({ json: ok(updated) })
      return
    }
    await route.fulfill({ status: 405 })
  })
  await page.route(
    '**/api/transactions/42/manual-override',
    async (route) => {
      state.detail = {
        ...state.detail,
        manual_category_override: false,
        category: '餐飲',
      }
      await route.fulfill({ json: ok(state.detail) })
    },
  )
}

test.describe('Transaction edit', () => {
  test('list → detail → change category → reload preserves override', async ({
    page,
  }) => {
    const state = { detail: { ...BASE_DETAIL } }
    await setupRoutes(page, state)

    // 1. 列表頁進入
    await page.goto('/transactions')
    await expect(page.getByText('Starbucks')).toBeVisible()

    // 2. 點編輯 icon → /transactions/42
    await page.getByLabel('編輯交易 Starbucks').click()
    await expect(page).toHaveURL(/\/transactions\/42/)
    await expect(page.getByLabel('分類選擇')).toBeVisible()
    await expect(page.getByText('自動分類')).toBeVisible()

    // 3. 改 category 為 購物 → 出現 manual override 徽章
    await page.getByLabel('分類選擇').selectOption('2')
    await expect(page.getByText('手動覆寫')).toBeVisible()
    await expect(page.getByLabel('重置覆寫')).toBeVisible()

    // 4. 模擬「F5 重整」：重新載入頁面、state 從伺服器抓回
    await page.reload()
    await expect(page.getByText('手動覆寫')).toBeVisible()

    // 5. 模擬「重跑 pipeline」：detail GET 仍回 manual_override=true
    //    （pipeline 不會主動覆寫已 override 的 row，state 不變）
    await page.reload()
    await expect(page.getByText('手動覆寫')).toBeVisible()
  })

  test('reset manual override clears badge', async ({ page }) => {
    const state = {
      detail: {
        ...BASE_DETAIL,
        manual_category_override: true,
        category: '購物',
      },
    }
    await setupRoutes(page, state)

    await page.goto('/transactions/42')
    await expect(page.getByText('手動覆寫')).toBeVisible()

    await page.getByLabel('重置覆寫').click()
    await expect(page.getByText('自動分類')).toBeVisible()
  })

  test('add tag updates UI', async ({ page }) => {
    const state = { detail: { ...BASE_DETAIL } }
    await setupRoutes(page, state)

    await page.goto('/transactions/42')
    await page.getByLabel('新增標籤').fill('業務')
    await page.getByRole('button', { name: '新增' }).click()
    await expect(page.getByText('業務')).toBeVisible()
  })

  test('PUT 失敗時顯示錯誤提示且頁面不被破壞 (R08/R23)', async ({ page }) => {
    const state = { detail: { ...BASE_DETAIL } }
    await setupRoutes(page, state)
    // 覆寫 detail 路由：GET 正常、PUT 回 422，驗證失敗會宣讀錯誤而非靜默。
    await page.route('**/api/transactions/42', async (route) => {
      const method = route.request().method()
      if (method === 'GET') {
        await route.fulfill({ json: ok(state.detail) })
        return
      }
      if (method === 'PUT') {
        await route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({ success: false, data: null, message: '分類無效' }),
        })
        return
      }
      await route.fulfill({ status: 405 })
    })

    await page.goto('/transactions/42')
    await page.getByLabel('分類選擇').selectOption('2')

    // 錯誤 alert（role="alert"）出現，且頁面其餘內容仍可用
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByText('Starbucks')).toBeVisible()
  })
})
