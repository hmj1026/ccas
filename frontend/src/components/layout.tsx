/**
 * Dashboard 主版面配置。
 *
 * 左側導覽列 + 右側內容區。支援 responsive。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  LayoutDashboard,
  Receipt,
  Sparkles,
  FileText,
  Workflow,
  Settings,
  Settings2,
  Bell,
  Wallet,
  Tags,
  Menu,
  X,
  LogOut,
} from 'lucide-react'
import { useState } from 'react'
import { Outlet, useNavigate } from 'react-router'
import { apiDelete } from '@/lib/api-client'
import type { ApiResponse } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { PrefetchLink } from '@/components/prefetch-link'
import {
  importBills,
  importInsights,
  importOperations,
  importOverview,
  importSettings,
  importSettingsBudgets,
  importSettingsReminders,
  importSettingsRules,
  importSetupGmail,
  importTransactions,
} from '@/lib/route-imports'

const NAV_GROUPS = [
  {
    group: '主要功能',
    items: [
      { to: '/overview', label: '總覽', icon: LayoutDashboard, prefetch: importOverview },
      { to: '/transactions', label: '交易', icon: Receipt, prefetch: importTransactions },
      { to: '/insights', label: '消費分析', icon: Sparkles, prefetch: importInsights },
      { to: '/bills', label: '帳單', icon: FileText, prefetch: importBills },
    ],
  },
  {
    group: '操作',
    items: [
      { to: '/operations', label: '操作中心', icon: Workflow, prefetch: importOperations },
    ],
  },
  {
    group: '設定',
    items: [
      { to: '/settings/reminders', label: '提醒', icon: Bell, prefetch: importSettingsReminders },
      { to: '/settings/budgets', label: '預算', icon: Wallet, prefetch: importSettingsBudgets },
      { to: '/settings/rules', label: '分類規則', icon: Tags, prefetch: importSettingsRules },
      { to: '/settings', label: '分類關鍵字', icon: Settings, prefetch: importSettings },
      { to: '/setup', label: '設定中心', icon: Settings2, prefetch: importSetupGmail },
    ],
  },
] as const

function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const logout = useMutation({
    mutationFn: () => apiDelete<ApiResponse<null>>('/api/auth/session'),
    // 登出語意上前端狀態必然清除：不論 API 成敗都清快取並導向 /login，
    // 避免 API 失敗時使用者卡在已登出畫面（R11）。
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth', 'session'] })
      navigate('/login', { replace: true })
    },
  })

  return (
    <div className="flex min-h-screen bg-background">
      {/* Skip link：鍵盤使用者可跳過側欄導覽直接到主內容（R24） */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded focus:bg-background focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow"
      >
        跳至主要內容
      </a>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setMobileOpen(false)
          }}
          role="button"
          tabIndex={0}
          aria-label="Close navigation"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-56 flex-col border-r border-border bg-sidebar transition-transform lg:static lg:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-14 items-center justify-between border-b border-border px-4">
          <span className="text-lg font-bold text-foreground">CCAS</span>
          <button
            className="lg:hidden"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <X className="size-5" />
          </button>
        </div>
        <nav className="flex-1 space-y-3 overflow-y-auto p-2">
          {NAV_GROUPS.map(({ group, items }, groupIndex) => (
            <div key={group}>
              {groupIndex > 0 && (
                <div
                  role="separator"
                  className="mb-3 border-t border-border"
                />
              )}
              <p className="px-3 pb-1 text-xs font-medium text-muted-foreground">
                {group}
              </p>
              <div className="space-y-1">
                {items.map(({ to, label, icon: Icon, prefetch }) => (
                  <PrefetchLink
                    key={to}
                    to={to}
                    onPrefetch={prefetch}
                    onClick={() => setMobileOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                        isActive
                          ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                          : 'text-sidebar-foreground hover:bg-sidebar-accent/50'
                      }`
                    }
                  >
                    <Icon className="size-4" />
                    {label}
                  </PrefetchLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="border-t border-border p-3">
          <Button
            variant="ghost"
            className="w-full justify-start"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
          >
            <LogOut className="size-4" data-icon="inline-start" />
            登出
          </Button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col">
        <header className="flex h-14 items-center border-b border-border px-4 lg:hidden">
          <button
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="size-5" />
          </button>
          <span className="ml-3 text-lg font-bold">CCAS</span>
        </header>
        <main id="main-content" tabIndex={-1} className="flex-1 p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default Layout
