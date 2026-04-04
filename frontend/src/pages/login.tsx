import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { apiPost } from '@/lib/api-client'
import type { ApiResponse } from '@/lib/types'
import { Button } from '@/components/ui/button'

type LocationState = {
  readonly from?: {
    readonly pathname?: string
  }
}

function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const [token, setToken] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  const login = useMutation({
    mutationFn: (value: string) =>
      apiPost<ApiResponse<null>>('/api/auth/session', { token: value }),
    onSuccess: async () => {
      queryClient.setQueryData(['auth', 'session'], true)
      await queryClient.invalidateQueries({ queryKey: ['auth', 'session'] })
      const state = location.state as LocationState | null
      navigate(state?.from?.pathname ?? '/overview', { replace: true })
    },
    onError: (error: Error) => {
      setErrorMessage(error.message)
    },
  })

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!token.trim()) {
      setErrorMessage('請輸入 API Token')
      return
    }
    setErrorMessage('')
    login.mutate(token.trim())
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <form
        className="w-full max-w-md space-y-5 rounded-2xl border border-border bg-card p-6 shadow-sm"
        onSubmit={handleSubmit}
      >
        <div className="space-y-2">
          <h1 className="text-2xl font-bold">登入 CCAS</h1>
          <p className="text-sm text-muted-foreground">
            以 API Token 建立瀏覽器 session，Token 不會再嵌入前端 bundle。
          </p>
        </div>

        <label className="block space-y-2">
          <span className="text-sm font-medium">API Token</span>
          <input
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm"
            autoComplete="current-password"
            aria-label="API Token"
          />
        </label>

        {errorMessage ? (
          <p className="text-sm text-destructive">{errorMessage}</p>
        ) : null}

        <Button
          type="submit"
          className="w-full"
          disabled={login.isPending}
          aria-label="登入"
        >
          {login.isPending ? '登入中...' : '登入'}
        </Button>
      </form>
    </div>
  )
}

export default LoginPage
