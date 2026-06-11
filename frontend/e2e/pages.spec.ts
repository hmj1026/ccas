import { test, expect } from '@playwright/test'

const API_TOKEN = process.env.API_TOKEN ?? '123456'

test.describe('Authenticated pages', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.locator('[aria-label="API Token"]').fill(API_TOKEN)
    await page.locator('[aria-label="登入"]').click()
    await expect(page).toHaveURL(/\/overview/, { timeout: 8000 })
  })

  test('overview page shows summary cards', async ({ page }) => {
    await expect(page.getByText('總消費')).toBeVisible()
    await expect(page.getByText('已繳')).toBeVisible()
    await expect(page.getByText('未繳').first()).toBeVisible()
  })

  test('bills page loads', async ({ page }) => {
    await page.goto('/bills')
    await expect(page).toHaveURL(/\/bills/)
    await expect(page.getByText('帳單')).toBeVisible()
  })

  test('transactions page loads', async ({ page }) => {
    await page.goto('/transactions')
    await expect(page).toHaveURL(/\/transactions/)
    await expect(page.getByText('交易')).toBeVisible()
  })

  test('analytics page loads with charts', async ({ page }) => {
    // /analytics 為 legacy 路由，App.tsx 用 <Navigate replace> 轉向 /insights
    await page.goto('/analytics')
    await expect(page).toHaveURL(/\/insights/)
    await expect(page.getByRole('heading', { name: '消費分析' })).toBeVisible({ timeout: 8000 })
    await expect(page.getByText('月消費趨勢')).toBeVisible()
  })

  test('settings page shows all 7 banks', async ({ page }) => {
    await page.goto('/settings')
    await expect(page).toHaveURL(/\/settings/)

    const banks = [
      '中國信託',
      '永豐銀行',
      '玉山銀行',
      '台新銀行',
      '聯邦銀行',
      '國泰世華',
      '台北富邦',
    ]
    for (const bank of banks) {
      await expect(page.getByText(bank, { exact: true }).first()).toBeVisible()
    }
  })

  test('settings page shows category keywords', async ({ page }) => {
    await page.goto('/settings')

    const categories = ['餐飲', '交通', '購物', '訂閱服務']
    for (const category of categories) {
      await expect(page.getByText(category).first()).toBeVisible()
    }
  })
})
