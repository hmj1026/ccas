import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { apiGet } from '@/lib/api-client'
import type { ApiResponse, SessionStatus } from '@/lib/types'
import { LoadingState } from '@/components/shared/states'

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
