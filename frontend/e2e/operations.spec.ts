import { test, expect, type Page } from '@playwright/test'

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

    await pickOption(page, '銀行', '中國信託')
    await pickOption(page, '年度', '2026')
    await pickOption(page, '月份', '3')
    await pickOption(page, '起始階段', '解析')
    await pickOption(page, '結束階段', '分類')
    await page.getByLabel('強制重跑').check()
    await page.getByRole('button', { name: '開始執行' }).click()

    await expect(page.getByText('parse 47 / 120 (39%)')).toBeVisible()
    await expect(page.getByText('running').first()).toBeVisible()
  })

  test('pipeline run 失敗時顯示錯誤訊息 (R08)', async ({ page }) => {
    const failedRun = {
      id: 'run-1',
      job_id: 'job-1',
      status: 'failed',
      triggered_by: 'api',
      params: { force: false, bank_code: 'CTBC', year: 2026, month: 3 },
      current_stage: 'parse',
      current_stage_processed: 10,
      current_stage_total: 120,
      stage_summary: [{ stage: 'parse', ok: 0, fail: 1, elapsed_ms: 500 }],
      error_message: '解析失敗：PDF 密碼錯誤',
      started_at: new Date(Date.now() - 5000).toISOString(),
      completed_at: new Date().toISOString(),
      created_at: '2026-05-01T12:00:00Z',
      updated_at: '2026-05-01T12:00:05Z',
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
      await route.fulfill({ json: ok(failedRun) })
    })
    await page.route('**/api/pipeline/runs', async (route) => {
      await route.fulfill({ json: ok(triggered ? [failedRun] : []) })
    })

    await page.goto('/operations')
    await pickOption(page, '銀行', '中國信託')
    await pickOption(page, '年度', '2026')
    await pickOption(page, '月份', '3')
    await page.getByRole('button', { name: '開始執行' }).click()

    // 1) 失敗狀態在執行紀錄中可見
    const failedRow = page.locator('tr', { hasText: 'failed' }).first()
    await expect(failedRow).toBeVisible()
    await expect(page.getByText('failed').first()).toBeVisible()

    // 2) 點開該列詳情 → 錯誤訊息呈現給使用者
    await failedRow.getByRole('button').first().click()
    await expect(page.getByText('解析失敗：PDF 密碼錯誤')).toBeVisible()
  })
})
