import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  // 自動啟動前端 dev server，讓 mock-route 規格在乾淨環境（CI / 新 clone）即可
  // 獨立執行，不再隱性依賴外部已啟動的 server（R07）。需要真實後端的規格
  // （auth / pages）以 E2E_BACKEND 環境變數自我 skip，見各 spec 頂部守衛。
  webServer: {
    command: 'pnpm dev --port 5173 --strictPort',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
