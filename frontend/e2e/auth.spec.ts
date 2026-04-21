import { test, expect } from '@playwright/test'

const API_TOKEN = process.env.API_TOKEN ?? '123456'

test.describe('Authentication', () => {
  test('root redirects to login', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/)
  })

  test('login page renders token input', async ({ page }) => {
    await page.goto('/login')
    await expect(page.locator('[aria-label="API Token"]')).toBeVisible()
    await expect(page.locator('[aria-label="登入"]')).toBeVisible()
  })

  test('login with correct token navigates to overview', async ({ page }) => {
    await page.goto('/login')
    await page.locator('[aria-label="API Token"]').fill(API_TOKEN)
    await page.locator('[aria-label="登入"]').click()
    await expect(page).toHaveURL(/\/overview/, { timeout: 8000 })
  })

  test('wrong token shows error message', async ({ page }) => {
    await page.goto('/login')
    await page.locator('[aria-label="API Token"]').fill('wrong-token')
    await page.locator('[aria-label="登入"]').click()
    await expect(
      page.getByText(/錯誤|失敗|Invalid|error/i),
    ).toBeVisible({ timeout: 5000 })
  })

  test('auth guard redirects unauthenticated user to login', async ({
    browser,
  }) => {
    const context = await browser.newContext()
    const page = await context.newPage()
    await page.goto('/overview')
    await expect(page).toHaveURL(/\/login/, { timeout: 8000 })
    await context.close()
  })

  test('logout returns to login', async ({ page }) => {
    await page.goto('/login')
    await page.locator('[aria-label="API Token"]').fill(API_TOKEN)
    await page.locator('[aria-label="登入"]').click()
    await expect(page).toHaveURL(/\/overview/, { timeout: 8000 })

    await page.getByRole('button', { name: '登出' }).click()
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
  })
})
