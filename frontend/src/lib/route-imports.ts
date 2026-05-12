/**
 * 路由 dynamic import 工廠集中地。
 *
 * `App.tsx` 用這些函式建立 `lazy()` 元件，`PrefetchLink` 在 hover/focus 時
 * 呼叫同一個函式預先載入 chunk。透過共用同一個 specifier，rolldown 會把兩處
 * 視為同一個 chunk，預載結果可被點擊後的 lazy 直接取用，免再下載。
 */

export const importOverview = () => import('@/pages/overview')
export const importTransactions = () => import('@/pages/transactions')
export const importTransactionDetail = () => import('@/pages/transaction-detail')
export const importInsights = () => import('@/pages/insights')
export const importBills = () => import('@/pages/bills')
export const importOperations = () => import('@/pages/operations')
export const importSettings = () => import('@/pages/settings')
export const importSettingsReminders = () => import('@/pages/settings-reminders')
export const importSettingsBudgets = () => import('@/pages/settings-budgets')
export const importSettingsRules = () => import('@/pages/settings-rules')
export const importSetupLayout = () => import('@/pages/setup/layout')
export const importSetupGmail = () => import('@/pages/setup/gmail')
export const importSetupGmailCallback = () => import('@/pages/setup/gmail-callback')
export const importSetupBanks = () => import('@/pages/setup/banks')
export const importSetupSecrets = () => import('@/pages/setup/secrets')
export const importSetupAdmin = () => import('@/pages/setup/admin')
