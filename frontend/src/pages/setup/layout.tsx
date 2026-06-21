/**
 * 設定中心 layout（oauth-onboarding-ui §7）。
 *
 * 左側固定 sub-nav 含 4 子頁（Gmail / 銀行 / PDF 密碼 / API Token），
 * 右側 outlet 載入子頁內容。Layout 本身不需驗證（外層 AuthGuard 已套）。
 */
import { Mail, Building2, KeyRound, Lock, ShieldCheck } from 'lucide-react'
import { NavLink, Outlet } from 'react-router'

const SETUP_NAV_ITEMS = [
  { to: '/setup/gmail', label: 'Gmail 連線', icon: Mail },
  { to: '/setup/banks', label: '銀行啟用', icon: Building2 },
  { to: '/setup/secrets', label: 'PDF 密碼', icon: KeyRound },
  { to: '/setup/login-credentials', label: '登入憑證', icon: Lock },
  { to: '/setup/admin', label: 'API Token', icon: ShieldCheck },
] as const

function SetupLayout() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">設定中心</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          首次部屬完成後，依序完成下列設定即可啟用 CCAS 全部功能。
        </p>
      </div>

      <div className="flex flex-col gap-6 lg:flex-row">
        <nav
          className="flex shrink-0 flex-row gap-1 overflow-x-auto rounded-lg border border-border bg-card p-2 lg:w-56 lg:flex-col"
          aria-label="設定中心子頁"
        >
          {SETUP_NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors ${
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

        <section className="flex-1 min-w-0">
          <Outlet />
        </section>
      </div>
    </div>
  )
}

export default SetupLayout
