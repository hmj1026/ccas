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

const OverviewPage = lazy(() => import('@/pages/overview'))
const TransactionsPage = lazy(() => import('@/pages/transactions'))
const AnalyticsPage = lazy(() => import('@/pages/analytics'))
const BillsPage = lazy(() => import('@/pages/bills'))
const SettingsPage = lazy(() => import('@/pages/settings'))

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
            <Route path="analytics" element={<Suspense fallback={<LoadingState />}><AnalyticsPage /></Suspense>} />
            <Route path="bills" element={<Suspense fallback={<LoadingState />}><BillsPage /></Suspense>} />
            <Route path="settings" element={<Suspense fallback={<LoadingState />}><SettingsPage /></Suspense>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
