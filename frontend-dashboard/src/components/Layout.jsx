import { NavLink, Outlet } from 'react-router-dom'
import { LayoutDashboard, Globe, KeyRound, CreditCard, Database, MessageSquareText, MessagesSquare, BarChart3, Settings, LogOut, Sparkles } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/websites', label: 'Websites', icon: Globe },
  { to: '/datasources', label: 'Data sources', icon: Database },
  { to: '/api-keys', label: 'API Keys', icon: KeyRound },
  { to: '/chat', label: 'Chat', icon: MessageSquareText },
  { to: '/messages', label: 'Messages', icon: MessagesSquare },
  { to: '/usage', label: 'Usage', icon: BarChart3 },
  { to: '/billing', label: 'Billing', icon: CreditCard },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Layout() {
  const { user, store, logout } = useAuth()
  return <div className="flex min-h-screen bg-paper">
    <aside className="flex w-64 shrink-0 flex-col bg-ink text-white">
      <div className="flex items-center gap-2.5 px-6 py-7">
        <div className="flex h-7 w-7 items-center justify-center rounded-md border border-accent/40 text-accent"><Sparkles size={14} strokeWidth={2}/></div>
        <span className="font-display text-[17px] font-medium tracking-tight">Merchant Console</span>
      </div>
      <nav className="flex-1 space-y-0.5 px-3">{NAV.map(({to,label,icon:Icon,end}) => <NavLink key={to} to={to} end={end} className={({isActive}) => `flex items-center gap-3 border-l-2 px-3.5 py-2.5 text-[13.5px] font-medium transition-colors ${isActive ? 'border-accent bg-ink-soft text-white' : 'border-transparent text-ink-muted hover:border-ink-line hover:text-white'}`}><Icon size={16} strokeWidth={1.8}/>{label}</NavLink>)}</nav>
      <div className="border-t border-ink-line px-3 py-4">
        <div className="mb-1 px-3.5 py-2">
          <div className="truncate font-display text-[15px] font-medium text-white">{store?.name || 'Your store'}</div>
          <div className="truncate text-xs text-ink-muted">{user?.email}</div>
        </div>
        <button onClick={logout} className="flex w-full items-center gap-3 border-l-2 border-transparent px-3.5 py-2.5 text-[13.5px] font-medium text-ink-muted transition-colors hover:border-ink-line hover:text-white"><LogOut size={16} strokeWidth={1.8}/>Log out</button>
      </div>
    </aside>
    <main className="flex-1 overflow-y-auto"><div className="mx-auto max-w-5xl px-8 py-12"><Outlet /></div></main>
  </div>
}
