/**
 * Export dialog component (§13.6)。
 *
 * 收集 format / start / end / bank / category / include_user_fields，
 * 觸發 GET /api/transactions/export 並讓瀏覽器下載 blob。
 */
import { Download, X } from 'lucide-react'
import { useState } from 'react'
import { apiFetchBlob } from '@/lib/api-client'
import type { ExportFormat } from '@/lib/types'
import { Button } from '@/components/ui/button'

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

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-3 rounded-lg border border-border bg-background p-4"
      >
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold">匯出交易</h3>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label="close"
          >
            <X className="size-4" />
          </Button>
        </div>

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
              onChange={(e) => setEnd(e.target.value)}
            />
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col text-sm">
            <span className="text-muted-foreground">銀行代碼</span>
            <input
              type="text"
              className="rounded border border-input bg-background px-2 py-1"
              value={bank}
              onChange={(e) => setBank(e.target.value)}
              placeholder="例：CTBC"
            />
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
    </div>
  )
}
