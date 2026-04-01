/**
 * 應用程式根元件。
 *
 * 設定 React Query 與 React Router，先驗證 session，再載入 dashboard 路由。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import AuthGuard from '@/components/auth-guard'
import Layout from '@/components/layout'
import LoginPage from '@/pages/login'
import OverviewPage from '@/pages/overview'
import TransactionsPage from '@/pages/transactions'
import AnalyticsPage from '@/pages/analytics'
import BillsPage from '@/pages/bills'
import SettingsPage from '@/pages/settings'

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
            <Route path="overview" element={<OverviewPage />} />
            <Route path="transactions" element={<TransactionsPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="bills" element={<BillsPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
