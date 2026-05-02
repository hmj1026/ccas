/**
 * 設定中心子頁 placeholder（PR-C3 / PR-C4 將替換）。
 *
 * 顯示「即將推出」訊息與目前可用的 fallback 操作。
 */
import { Wrench } from 'lucide-react'

interface PlaceholderInfo {
  readonly title: string
  readonly upcomingPr: string
  readonly fallback: readonly string[]
}

const SECTION_INFO: Record<'banks' | 'secrets' | 'admin', PlaceholderInfo> = {
  banks: {
    title: '銀行啟用清單 UI',
    upcomingPr: 'PR-C3（oauth-onboarding-ui §4 / §9）',
    fallback: [
      '目前仍以 config/banks.yaml 控制銀行啟用狀態。',
      '在伺服器端編輯該檔後重啟 backend / worker 即可生效。',
    ],
  },
  secrets: {
    title: 'PDF 密碼 UI',
    upcomingPr: 'PR-C3（oauth-onboarding-ui §5 / §10）',
    fallback: [
      '目前仍以 .env 的 PDF_PASSWORD_<BANK_CODE> 變數提供密碼。',
      '修改 .env 後重啟 backend / worker 即可生效。',
    ],
  },
  admin: {
    title: 'API Token rotate UI',
    upcomingPr: 'PR-C4（oauth-onboarding-ui §6 / §11）',
    fallback: [
      '目前仍以 ${CCAS_DATA_LOCATION}/secrets/api-token 檔案儲存 token。',
      '若需 rotate，請手動刪除該檔後重啟 backend，entrypoint 會自動重新產生。',
    ],
  },
}

function SetupPlaceholder({
  section,
}: {
  readonly section: 'banks' | 'secrets' | 'admin'
}) {
  const info = SECTION_INFO[section]
  return (
    <div className="space-y-4 rounded-lg border border-dashed border-border bg-card p-6">
      <div className="flex items-start gap-3">
        <Wrench className="mt-0.5 size-5 text-muted-foreground" />
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">{info.title}</h2>
          <p className="text-sm text-muted-foreground">
            此功能尚未實作，將於 {info.upcomingPr} 落地。
          </p>
        </div>
      </div>

      <div className="rounded-md border border-border bg-muted/40 p-4 text-sm">
        <p className="mb-2 font-medium">目前可用的 fallback 操作</p>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          {info.fallback.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

export default SetupPlaceholder
