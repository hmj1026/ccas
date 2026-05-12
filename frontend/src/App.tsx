/**
 * 應用程式根元件。
 *
 * 設定 React Query 與 React Router，先驗證 session，再載入 dashboard 路由。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import AuthGuard from '@/components/auth-guard'
import Layout from '@/components/layout'
import { LoadingState } from '@/components/shared/states'
import LoginPage from '@/pages/login'
import {
  importBills,
  importInsights,
  importOperations,
  importOverview,
  importSettings,
  importSettingsBudgets,
  importSettingsReminders,
  importSettingsRules,
  importSetupAdmin,
  importSetupBanks,
  importSetupGmail,
  importSetupGmailCallback,
  importSetupLayout,
  importSetupSecrets,
  importTransactionDetail,
  importTransactions,
} from '@/lib/route-imports'

const OverviewPage = lazy(importOverview)
const TransactionsPage = lazy(importTransactions)
const TransactionDetailPage = lazy(importTransactionDetail)
const InsightsPage = lazy(importInsights)
const BillsPage = lazy(importBills)
const OperationsPage = lazy(importOperations)
const SettingsPage = lazy(importSettings)
const SettingsRemindersPage = lazy(importSettingsReminders)
const SettingsBudgetsPage = lazy(importSettingsBudgets)
const SettingsRulesPage = lazy(importSettingsRules)
const SetupLayout = lazy(importSetupLayout)
const SetupGmailPage = lazy(importSetupGmail)
const SetupGmailCallbackPage = lazy(importSetupGmailCallback)
const SetupBanksPage = lazy(importSetupBanks)
const SetupSecretsPage = lazy(importSetupSecrets)
const SetupAdminPage = lazy(importSetupAdmin)

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
      },
    },
  })
}

function App() {
  const [queryClient] = useState(createQueryClient)

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="login" element={<LoginPage />} />
          <Route
            element={
              <AuthGuard>
                <Layout />
              </AuthGuard>
            }
          >
            <Route index element={<Navigate to="/overview" replace />} />
            <Route path="overview" element={<Suspense fallback={<LoadingState />}><OverviewPage /></Suspense>} />
            <Route path="transactions" element={<Suspense fallback={<LoadingState />}><TransactionsPage /></Suspense>} />
            <Route path="transactions/:id" element={<Suspense fallback={<LoadingState />}><TransactionDetailPage /></Suspense>} />
            <Route path="insights" element={<Suspense fallback={<LoadingState />}><InsightsPage /></Suspense>} />
            <Route path="analytics" element={<Navigate to="/insights" replace />} />
            <Route path="bills" element={<Suspense fallback={<LoadingState />}><BillsPage /></Suspense>} />
            <Route path="operations" element={<Suspense fallback={<LoadingState />}><OperationsPage /></Suspense>} />
            <Route path="settings" element={<Suspense fallback={<LoadingState />}><SettingsPage /></Suspense>} />
            <Route path="settings/reminders" element={<Suspense fallback={<LoadingState />}><SettingsRemindersPage /></Suspense>} />
            <Route path="settings/budgets" element={<Suspense fallback={<LoadingState />}><SettingsBudgetsPage /></Suspense>} />
            <Route path="settings/rules" element={<Suspense fallback={<LoadingState />}><SettingsRulesPage /></Suspense>} />
            <Route
              path="setup"
              element={<Suspense fallback={<LoadingState />}><SetupLayout /></Suspense>}
            >
              <Route index element={<Navigate to="/setup/gmail" replace />} />
              <Route
                path="gmail"
                element={<Suspense fallback={<LoadingState />}><SetupGmailPage /></Suspense>}
              />
              <Route
                path="gmail/callback"
                element={<Suspense fallback={<LoadingState />}><SetupGmailCallbackPage /></Suspense>}
              />
              <Route
                path="banks"
                element={<Suspense fallback={<LoadingState />}><SetupBanksPage /></Suspense>}
              />
              <Route
                path="secrets"
                element={<Suspense fallback={<LoadingState />}><SetupSecretsPage /></Suspense>}
              />
              <Route
                path="admin"
                element={<Suspense fallback={<LoadingState />}><SetupAdminPage /></Suspense>}
              />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
