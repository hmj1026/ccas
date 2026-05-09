/**
 * AuthGuard -- 路由層級驗證守衛。
 * 載入時查詢 session 狀態；未驗證則重導至登入頁並記錄來源路徑。
 */
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { apiGet } from '@/lib/api-client'
import type { ApiResponse, SessionStatus } from '@/lib/types'
import { LoadingState } from '@/components/shared/states'

/**
 * 驗證目前 session 是否有效；未登入時重導至 `/login`。
 * 驗證期間顯示載入畫面，避免頁面閃爍。
 *
 * @param children - 驗證通過後渲染的子元件
 */
function AuthGuard({ children }: { readonly children: ReactNode }) {
  const location = useLocation()
  const sessionQuery = useQuery({
    queryKey: ['auth', 'session'],
    queryFn: async () => {
      try {
        const response = await apiGet<ApiResponse<SessionStatus>>('/api/auth/session')
        return response.data.authenticated
      } catch {
        return false
      }
    },
    retry: false,
  })

  if (sessionQuery.isLoading) {
    return <LoadingState message="驗證登入狀態..." />
  }

  if (!sessionQuery.data) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <>{children}</>
}

export default AuthGuard
