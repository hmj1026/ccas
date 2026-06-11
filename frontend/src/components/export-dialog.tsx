/**
 * Export dialog component (§13.6)。
 *
 * 收集 format / start / end / bank / category / include_user_fields，
 * 觸發 GET /api/transactions/export 並讓瀏覽器下載 blob。
 */
import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { useState } from 'react'
import { apiFetchBlob, apiGet } from '@/lib/api-client'
import type { ApiResponse, BankConfigItem, ExportFormat } from '@/lib/types'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function ExportDialog({
  isOpen,
  onClose,
}: {
  readonly isOpen: boolean
  readonly onClose: () => void
}) {
  const [format, setFormat] = useState<ExportFormat>('csv')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [bank, setBank] = useState('')
  const [category, setCategory] = useState('')
  const [includeUserFields, setIncludeUserFields] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Shares the React Query cache entry with FilterBar's bank dropdown.
  const banksQuery = useQuery({
    queryKey: ['settings', 'banks'],
    queryFn: () =>
      apiGet<ApiResponse<readonly BankConfigItem[]>>('/api/settings/banks'),
    staleTime: 5 * 60 * 1000,
  })
  const banks = banksQuery.data?.data ?? []

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (start && end && end < start) {
      setError('結束日期不能早於起始日期')
      return
    }
    setBusy(true)
    try {
      const params = {
        format,
        start: start || undefined,
        end: end || undefined,
        bank: bank || undefined,
        category: category || undefined,
        include_user_fields: includeUserFields,
      }
      const blob = await apiFetchBlob('/api/transactions/export', params)
      const ts = new Date().toISOString().slice(0, 10)
      const ext = format === 'xlsx' ? 'xlsx' : 'csv'
      downloadBlob(blob, `ccas-transactions-${ts}.${ext}`)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : '匯出失敗')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>匯出交易</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
        <label className="flex flex-col text-sm">
          <span className="text-muted-foreground">格式</span>
          <select
            className="rounded border border-input bg-background px-2 py-1"
            value={format}
            onChange={(e) => setFormat(e.target.value as ExportFormat)}
          >
            <option value="csv">CSV</option>
            <option value="xlsx">Excel (xlsx)</option>
          </select>
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col text-sm">
            <span className="text-muted-foreground">起始日期</span>
            <input
              type="date"
              className="rounded border border-input bg-background px-2 py-1"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </label>
          <label className="flex flex-col text-sm">
            <span className="text-muted-foreground">結束日期</span>
            <input
              type="date"
              className="rounded border border-input bg-background px-2 py-1"
              value={end}
              min={start || undefined}
              onChange={(e) => setEnd(e.target.value)}
            />
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col text-sm">
            <span className="text-muted-foreground">銀行</span>
            {banksQuery.isError ? (
              // Fallback: keep export usable with manual bank code input.
              <input
                type="text"
                className="rounded border border-input bg-background px-2 py-1"
                value={bank}
                onChange={(e) => setBank(e.target.value)}
                placeholder="例：CTBC"
                aria-label="銀行代碼（清單載入失敗，請手動輸入）"
              />
            ) : (
              <select
                className="rounded border border-input bg-background px-2 py-1"
                value={bank}
                onChange={(e) => setBank(e.target.value)}
              >
                <option value="">全部銀行</option>
                {banks.map((b) => (
                  <option key={b.bank_code} value={b.bank_code}>
                    {b.bank_name}（{b.bank_code}）
                  </option>
                ))}
              </select>
            )}
          </label>
          <label className="flex flex-col text-sm">
            <span className="text-muted-foreground">類別</span>
            <input
              type="text"
              className="rounded border border-input bg-background px-2 py-1"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="例：餐飲"
            />
          </label>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeUserFields}
            onChange={(e) => setIncludeUserFields(e.target.checked)}
          />
          包含使用者欄位（手動覆寫 / tags / merchant_alias / note）
        </label>

        {error && <p className="text-xs text-destructive">{error}</p>}

        <Button type="submit" disabled={busy} className="w-full">
          <Download className="size-4" data-icon="inline-start" />
          {busy ? '匯出中…' : '下載'}
        </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
