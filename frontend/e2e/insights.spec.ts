/**
 * E2E for Insights page (bills-management-and-insights §13.10 + §15.8)。
 *
 * 全程透過 ``page.route`` mock backend，不依賴真實後端啟動。
 *
 * 涵蓋情境：
 * 1. NAV 「Insights」進入 → 頁面載入主要區塊
 * 2. 切換 year_metric 重新發 fetch
 * 3. 設定 month → 顯示 compare 區塊
 * 4. 開啟匯出對話框 → 觸發 blob 下載 → 對話框收起
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

const TREND_DATA = [
  { month: '2026-04', total: 5000 },
  { month: '2026-05', total: 7500 },
]

const BANKS_DATA = [
  { bank_code: 'CTBC', bank_name: '中國信託', total: 12000 },
  { bank_code: 'ESUN', bank_name: '玉山', total: 8000 },
]

const YEARS_TOTAL = [
  { year: 2025, value: 100000 },
  { year: 2026, value: 50000 },
]

const YEARS_COUNT = [
  { year: 2025, value: 220 },
  { year: 2026, value: 110 },
]

const MERCHANTS = [
  { merchant: 'STARBUCKS', total: 5000, count: 12 },
  { merchant: 'UBER', total: 3000, count: 8 },
]

const CATEGORIES_COMPARE = [
  {
    category: '餐飲',
    total: 1500,
    previous_total: 1200,
    change_percent: 25.0,
  },
]

async function setupRoutes(
  page: Page,
  hooks: { onYearMetric?: (metric: string) => void } = {},
) {
  await mockAuthenticatedSession(page)

  // Banks list (used by FilterBar bank select)
  await page.route('**/api/settings/banks', async (route) => {
    await route.fulfill({
      json: ok([
        {
          id: 1,
          bank_code: 'CTBC',
          bank_name: '中國信託',
          gmail_filter: 'from:ctbc',
          active_parser_version: 'v1',
          is_active: true,
        },
      ]),
    })
  })

  await page.route('**/api/analytics/trend**', async (route) => {
    await route.fulfill({ json: ok(TREND_DATA) })
  })
  await page.route('**/api/analytics/compare/banks**', async (route) => {
    await route.fulfill({ json: ok(BANKS_DATA) })
  })
  await page.route(
    '**/api/analytics/compare/years**',
    async (route: Route) => {
      const url = new URL(route.request().url())
      const metric = url.searchParams.get('metric') ?? 'total'
      hooks.onYearMetric?.(metric)
      await route.fulfill({
        json: ok(metric === 'count' ? YEARS_COUNT : YEARS_TOTAL),
      })
    },
  )
  await page.route('**/api/analytics/top-merchants**', async (route) => {
    await route.fulfill({ json: ok(MERCHANTS) })
  })
  await page.route('**/api/analytics/categories**', async (route) => {
    await route.fulfill({ json: ok(CATEGORIES_COMPARE) })
  })
}

test.describe('Insights page', () => {
  test('renders main sections from NAV', async ({ page }) => {
    await setupRoutes(page)
    await page.goto('/overview')

    // NAV Insights link (labelled 消費分析)
    await page.getByRole('link', { name: '消費分析' }).first().click()
    await expect(page).toHaveURL(/\/insights/)

    await expect(
      page.getByRole('heading', { name: '消費分析' }),
    ).toBeVisible()
    await expect(
      page.getByRole('heading', { name: '月消費趨勢' }),
    ).toBeVisible()
    await expect(
      page.getByRole('heading', { name: '銀行對比' }),
    ).toBeVisible()
    await expect(
      page.getByRole('heading', { name: '年度對比' }),
    ).toBeVisible()
    await expect(
      page.getByRole('heading', { name: '商家排行' }),
    ).toBeVisible()
    // Compare 區塊恆顯示；未帶 month query 時顯示提示 EmptyState（P3-6）
    await expect(page.getByText('類別 vs 上月')).toBeVisible()
    await expect(
      page.getByText('請先於上方選擇月份以比較類別'),
    ).toBeVisible()
  })

  test('switching year metric refetches with metric=count', async ({
    page,
  }) => {
    const seen: string[] = []
    await setupRoutes(page, { onYearMetric: (m) => seen.push(m) })
    await page.goto('/insights')

    await expect(
      page.getByRole('heading', { name: '年度對比' }),
    ).toBeVisible()

    // 預設 metric=total
    await expect(seen).toContain('total')

    await pickOption(page, '年度對比指標', '筆數')
    await expect.poll(() => seen.includes('count')).toBe(true)
  })

  test('setting month query renders compare section', async ({ page }) => {
    await setupRoutes(page)
    await page.goto('/insights?month=2026-05')

    await expect(page.getByText('類別 vs 上月')).toBeVisible()
    await expect(page.getByText('餐飲')).toBeVisible()
    // ▲25.0% 由 change_percent=25 推算
    await expect(page.getByText(/▲25\.0%/)).toBeVisible()
  })

  test('export dialog triggers CSV blob download', async ({ page }) => {
    await setupRoutes(page)

    let exportCalled = false
    await page.route('**/api/transactions/export**', async (route) => {
      exportCalled = true
      await route.fulfill({
        status: 200,
        headers: {
          'content-type': 'text/csv; charset=utf-8',
          'content-disposition': 'attachment; filename=transactions.csv',
        },
        body: 'trans_date,merchant,amount\n2026-05-10,STARBUCKS,150\n',
      })
    })

    await page.goto('/insights')
    await page.getByRole('button', { name: /匯出$/ }).click()

    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(
      page.getByRole('heading', { name: '匯出交易' }),
    ).toBeVisible()

    // 點下載 → 等待對話框收起確認流程完成
    await page.getByRole('button', { name: /下載/ }).click()
    await expect(page.getByRole('dialog')).toBeHidden()
    expect(exportCalled).toBe(true)
  })
})
