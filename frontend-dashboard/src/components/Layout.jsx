import { NavLink, Outlet } from 'react-router-dom'
import {
  LayoutDashboard,
  Globe,
  KeyRound,
  CreditCard,
  LogOut,
  Sparkles,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/websites', label: 'Websites', icon: Globe },
  { to: '/api-keys', label: 'API Keys', icon: KeyRound },
  { to: '/billing', label: 'Billing', icon: CreditCard },
]

export default function Layout() {
  const { user, store, logout } = useAuth()

  return (
    <div className="flex min-h-screen bg-paper">
      <aside className="flex w-64 shrink-0 flex-col bg-ink text-white">
        <div className="flex items-center gap-2 px-6 py-6">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent">
            <Sparkles size={16} strokeWidth={2.25} />
          </div>
          <span className="font-display text-[15px] font-semibold tracking-tight">
            Merchant Console
          </span>
        </div>

        <nav className="flex-1 space-y-1 px-3">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-ink-soft text-white'
                    : 'text-ink-muted hover:bg-ink-soft hover:text-white'
                }`
              }
            >
              <Icon size={17} strokeWidth={1.9} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-ink-line px-3 py-4">
          <div className="mb-2 rounded-lg px-3 py-2">
            <div className="truncate text-sm font-medium text-white">
              {store?.name || 'Your store'}
            </div>
            <div className="truncate text-xs text-ink-muted">{user?.email}</div>
          </div>
          <button
            onClick={logout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-ink-muted transition-colors hover:bg-ink-soft hover:text-white"
          >
            <LogOut size={17} strokeWidth={1.9} />
            Log out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-8 py-10">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
