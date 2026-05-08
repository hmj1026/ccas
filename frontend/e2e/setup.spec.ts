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

test.describe('Setup center', () => {
  test('Gmail Web flow uploads credentials, redirects through callback, and revokes', async ({
    page,
  }) => {
    let connected = false
    let authorizeHit = false

    await mockAuthenticatedSession(page)
    await page.route('**/api/setup/gmail/**', async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith('/status')) {
        await route.fulfill({
          json: ok({
            connected,
            email: connected ? 'user@example.com' : null,
            granted_scopes: connected
              ? ['https://www.googleapis.com/auth/gmail.readonly']
              : [],
          }),
        })
        return
      }
      if (url.pathname.endsWith('/credentials')) {
        await route.fulfill({
          json: ok({
            saved_path: '/data/credentials.json',
            client_id_last8: 'client42',
          }),
        })
        return
      }
      if (url.pathname.endsWith('/authorize')) {
        authorizeHit = true
        connected = true
        const appOrigin = new URL(page.url()).origin
        await route.fulfill({
          json: ok({
            authorize_url: `${appOrigin}/setup/gmail?status=connected`,
            state: 'fake-state',
          }),
        })
        return
      }
      if (url.pathname.endsWith('/revoke')) {
        connected = false
        await route.fulfill({
          json: ok({
            connected: false,
            email: null,
            granted_scopes: [],
          }),
        })
        return
      }
      await route.fulfill({ status: 404, json: { detail: 'Not Found' } })
    })

    await page.goto('/setup/gmail')
    await expect(page.getByText('上傳 credentials.json')).toBeVisible()

    await page
      .getByLabel('上傳 credentials.json')
      .setInputFiles({
        name: 'credentials.json',
        mimeType: 'application/json',
        buffer: Buffer.from(
          JSON.stringify({
            web: { client_id: 'client42', client_secret: 'secret42' },
          }),
        ),
      })
    await expect(page.getByText(/client_id 末 8 字/)).toBeVisible()

    await page.getByRole('button', { name: '授權 Google' }).click()
    await expect(page).toHaveURL(/\/setup\/gmail(?:\?|$)/)
    expect(authorizeHit).toBe(true)
    await expect(page.getByText('Gmail 已連線')).toBeVisible()
    await expect(page.getByText('user@example.com')).toBeVisible()

    await page.getByRole('button', { name: '解除 Gmail 連線' }).click()
    await page.getByRole('button', { name: '確認解除連線' }).click()
    await expect(page.getByText('上傳 credentials.json')).toBeVisible()
  })

  test('Gmail callback forwards code and state to backend callback', async ({
    page,
  }) => {
    let callbackHit = false

    await mockAuthenticatedSession(page)
    await page.route('**/api/setup/gmail/callback?**', async (route) => {
      const url = new URL(route.request().url())
      callbackHit =
        url.searchParams.get('code') === 'fake-code' &&
        url.searchParams.get('state') === 'fake-state'
      await route.fulfill({
        status: 303,
        headers: { location: '/setup/gmail?status=connected' },
      })
    })
    await page.route('**/api/setup/gmail/status', async (route) => {
      await route.fulfill({
        json: ok({
          connected: true,
          email: 'user@example.com',
          granted_scopes: ['https://www.googleapis.com/auth/gmail.readonly'],
        }),
      })
    })

    await page.goto('/setup/gmail/callback?code=fake-code&state=fake-state')
    await expect(page).toHaveURL(/\/setup\/gmail(?:\?|$)/)
    expect(callbackHit).toBe(true)
    await expect(page.getByText('Gmail 已連線')).toBeVisible()
  })

  test('bank toggle persists after reload', async ({ page }) => {
    const banks = [
      {
        code: 'CTBC',
        display_name: '中國信託',
        enabled: true,
        has_settings_row: true,
        metadata_missing: false,
        total_pdfs: 3,
        last_ingest_at: '2026-05-01T12:00:00Z',
      },
    ]

    await mockAuthenticatedSession(page)
    await page.route('**/api/setup/banks', async (route) => {
      await route.fulfill({ json: ok(banks) })
    })
    await page.route('**/api/setup/banks/CTBC', async (route) => {
      const body = (await route.request().postDataJSON()) as {
        enabled: boolean
      }
      banks[0] = { ...banks[0], enabled: body.enabled }
      await route.fulfill({ json: ok(banks[0]) })
    })
    await page.goto('/setup/banks')

    await expect(page.getByText('中國信託')).toBeVisible()
    await page.getByRole('button', { name: '停用 CTBC' }).click()
    await expect(page.getByRole('button', { name: '啟用 CTBC' })).toBeVisible()

    await page.goto('/setup/banks')
    await expect(page.getByRole('button', { name: '啟用 CTBC' })).toBeVisible()
  })

  test('PDF secret source changes from DB to env fallback after delete', async ({
    page,
  }) => {
    const secrets = [
      {
        bank_code: 'CTBC',
        has_db_secret: false,
        has_env_secret: true,
        effective_source: 'env',
      },
    ]

    await mockAuthenticatedSession(page)
    await page.route('**/api/setup/secrets', async (route) => {
      await route.fulfill({ json: ok(secrets) })
    })
    await page.route('**/api/setup/secrets/CTBC', async (route) => {
      if (route.request().method() === 'PUT') {
        secrets[0] = {
          ...secrets[0],
          has_db_secret: true,
          effective_source: 'db',
        }
        await route.fulfill({ json: ok({ bank_code: 'CTBC' }) })
        return
      }
      secrets[0] = {
        ...secrets[0],
        has_db_secret: false,
        effective_source: 'env',
      }
      await route.fulfill({ json: ok({ bank_code: 'CTBC' }) })
    })

    await page.goto('/setup/secrets')
    await expect(page.getByLabel('目前來源：env')).toBeVisible()

    await page.getByRole('button', { name: '設定 CTBC 密碼' }).click()
    await page.getByLabel('CTBC 新密碼').fill('db-password')
    await page.getByRole('button', { name: '儲存 CTBC 密碼' }).click()
    await expect(page.getByLabel('目前來源：DB')).toBeVisible()

    await page.reload()
    await expect(page.getByLabel('目前來源：DB')).toBeVisible()

    await page.getByRole('button', { name: '刪除 CTBC DB 密碼' }).click()
    await page.getByRole('button', { name: '確認刪除 CTBC' }).click()
    await expect(page.getByLabel('目前來源：env')).toBeVisible()
  })

  test('token rotate invalidates old login token and accepts new token', async ({
    page,
  }) => {
    let currentToken = 'old-token'
    let sessionAuthenticated = true

    await page.route('**/api/auth/session', async (route) => {
      const request = route.request()
      if (request.method() === 'GET') {
        await route.fulfill({
          json: ok({ authenticated: sessionAuthenticated }),
        })
        return
      }
      if (request.method() === 'DELETE') {
        sessionAuthenticated = false
        await route.fulfill({ status: 204 })
        return
      }
      const body = (await request.postDataJSON()) as { token: string }
      if (body.token === currentToken) {
        sessionAuthenticated = true
        await route.fulfill({ json: ok(null) })
        return
      }
      await route.fulfill({
        status: 401,
        json: { detail: 'Invalid token' },
      })
    })
    await page.route('**/api/setup/admin/token-info', async (route) => {
      await route.fulfill({
        json: ok({
          last4: currentToken.slice(-4),
          created_at: '2026-05-04T12:00:00Z',
          version: currentToken === 'old-token' ? 1 : 2,
        }),
      })
    })
    await page.route('**/api/setup/admin/token-rotate', async (route) => {
      currentToken = 'new-token-64-hex'
      await route.fulfill({
        json: ok({
          token: currentToken,
          version: 2,
          last4: currentToken.slice(-4),
        }),
      })
    })

    await page.goto('/setup/admin')
    await expect(page.getByText('API Token 管理')).toBeVisible()
    await page.getByRole('button', { name: '產生新 token' }).click()
    await page.getByRole('button', { name: '確認產生新 token' }).click()
    await expect(page.getByLabel('新 token 明文')).toContainText(currentToken)

    sessionAuthenticated = false
    await page.getByRole('button', { name: '登出 session 並回登入頁' }).click()
    await expect(page).toHaveURL(/\/login/)

    await page.getByLabel('API Token').fill('old-token')
    await page.getByRole('button', { name: '登入' }).click()
    await expect(page.getByText(/Invalid token/)).toBeVisible()

    await page.getByLabel('API Token').fill(currentToken)
    await page.getByRole('button', { name: '登入' }).click()
    await expect(page).toHaveURL(/\/overview/)
  })
})
