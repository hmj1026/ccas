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
    const request = route.request()
    if (request.method() === 'GET') {
      await route.fulfill({ json: ok({ authenticated: true }) })
      return
    }
    if (request.method() === 'DELETE') {
      await route.fulfill({ status: 204 })
      return
    }
    await route.fulfill({ json: ok(null) })
  })
}

test.describe('Operations center', () => {
  test('submits pipeline trigger and shows active run', async ({ page }) => {
    const run = {
      id: 'run-1',
      job_id: 'job-1',
      status: 'running',
      triggered_by: 'api',
      params: { force: true, bank_code: 'CTBC', year: 2026, month: 3 },
      current_stage: 'parse',
      current_stage_processed: 47,
      current_stage_total: 120,
      stage_summary: [{ stage: 'ingest', ok: 2, fail: 0, elapsed_ms: 1000 }],
      error_message: null,
      started_at: new Date(Date.now() - 3000).toISOString(),
      completed_at: null,
      created_at: '2026-05-01T12:00:00Z',
      updated_at: '2026-05-01T12:00:03Z',
    }
    let triggered = false

    await mockAuthenticatedSession(page)
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
    await page.route('**/api/pipeline/trigger', async (route) => {
      triggered = true
      await route.fulfill({ json: ok({ job_id: 'job-1', run_id: 'run-1' }) })
    })
    await page.route('**/api/pipeline/runs/run-1', async (route) => {
      await route.fulfill({ json: ok(run) })
    })
    await page.route('**/api/pipeline/runs', async (route) => {
      await route.fulfill({ json: ok(triggered ? [run] : []) })
    })

    await page.goto('/operations')
    await expect(page.getByRole('heading', { name: '操作中心' })).toBeVisible()

    await page.getByLabel('銀行').selectOption('CTBC')
    await page.getByLabel('年度').selectOption('2026')
    await page.getByLabel('月份').selectOption('3')
    await page.getByLabel('起始階段').selectOption('parse')
    await page.getByLabel('結束階段').selectOption('classify')
    await page.getByLabel('強制重跑').check()
    await page.getByRole('button', { name: '開始執行' }).click()

    await expect(page.getByText('parse 47 / 120 (39%)')).toBeVisible()
    await expect(page.getByText('running').first()).toBeVisible()
  })
})
