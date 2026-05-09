/**
 * Gmail OAuth 回呼中介頁（oauth-onboarding-ui §8.4）。
 *
 * Google 完成授權後 redirect 至 ${origin}/setup/gmail/callback?code=...&state=...
 * 此頁讀取 query params 後將整段 URL 轉發至後端
 * GET /api/setup/gmail/callback，由後端完成 token exchange、303 redirect 回
 * /setup/gmail?status=connected。
 *
 * 不直接在前端打 backend：保留 same-origin redirect chain，避免 CORS 與
 * cookie 問題；同時讓 backend 可寫 token.json。
 */
import { useEffect } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router'
import { ErrorState, LoadingState } from '@/components/shared/states'

function GmailCallbackPage() {
  const [searchParams] = useSearchParams()
  const code = searchParams.get('code')
  const state = searchParams.get('state')
  const errorParam = searchParams.get('error')

  useEffect(() => {
    if (!code || !state || errorParam) return
    const params = new URLSearchParams({ code, state })
    window.location.replace(`/api/setup/gmail/callback?${params.toString()}`)
  }, [code, state, errorParam])

  if (errorParam) {
    return (
      <div className="flex flex-col items-center gap-3 p-4">
        <ErrorState message={`Google 回報授權失敗：${errorParam}`} />
        <Link
          to="/setup/gmail"
          replace
          className="text-sm text-primary underline-offset-4 hover:underline"
        >
          回到 Gmail 設定頁
        </Link>
      </div>
    )
  }

  if (!code || !state) {
    return <Navigate to="/setup/gmail" replace />
  }

  return <LoadingState message="正在完成授權，請稍候..." />
}

export default GmailCallbackPage
