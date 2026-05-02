/**
 * Dashboard 主版面配置。
 *
 * 左側導覽列 + 右側內容區。支援 responsive。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  LayoutDashboard,
  Receipt,
  BarChart3,
  FileText,
  Settings,
  Settings2,
  Menu,
  X,
  LogOut,
} from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router'
import { apiDelete } from '@/lib/api-client'
import type { ApiResponse } from '@/lib/types'
import { Button } from '@/components/ui/button'

const NAV_ITEMS = [
  { to: '/overview', label: '總覽', icon: LayoutDashboard },
  { to: '/transactions', label: '交易', icon: Receipt },
  { to: '/analytics', label: '分析', icon: BarChart3 },
  { to: '/bills', label: '帳單', icon: FileText },
  { to: '/settings', label: '設定', icon: Settings },
  { to: '/setup/gmail', label: '設定中心', icon: Settings2 },
] as const

function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const logout = useMutation({
    mutationFn: () => apiDelete<ApiResponse<null>>('/api/auth/session'),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth', 'session'] })
      navigate('/login', { replace: true })
    },
  })

  return (
    <div className="flex min-h-screen bg-background">
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
        <nav className="flex-1 space-y-1 p-2">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
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
            </NavLink>
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
        <main className="flex-1 p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default Layout
