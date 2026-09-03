import { useEffect, useMemo, useState } from 'react'
import { ArrowUpRight, Check, Database, Globe, KeyRound, Settings2, TrendingUp } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { Badge, Button, Card, PageHeader, Spinner } from '../components/ui'

const SETUP_STEPS = [
  { id: 'website', label: 'Connect website', icon: Globe },
  { id: 'database', label: 'Connect product database', icon: Database },
  { id: 'api', label: 'Create API key', icon: KeyRound },
]

export default function Overview() {
  const { store } = useAuth()
  const [billing, setBilling] = useState(null)
  const [websites, setWebsites] = useState(null)
  const [datasources, setDatasources] = useState(null)
  const [keys, setKeys] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    Promise.allSettled([
      api.get('/v1/billing/summary'),
      api.get('/v1/knowledge/websites'),
      api.get('/v1/datasources'),
      api.get('/v1/stores/me/api-keys'),
    ]).then(([b, w, d, k]) => {
      if (!active) return
      if (b.status === 'fulfilled') setBilling(b.value)
      else setError('Some data failed to load.')
      if (w.status === 'fulfilled') setWebsites(w.value)
      if (d.status === 'fulfilled') setDatasources(d.value)
      if (k.status === 'fulfilled') setKeys(k.value)
    })
    return () => { active = false }
  }, [])

  const activeKeys = useMemo(
    () => keys?.api_keys?.filter((key) => key.active).length || 0,
    [keys],
  )
  const setup = useMemo(() => {
    const completed = [Boolean(websites?.count), Boolean(datasources?.count), activeKeys > 0]
    const done = completed.filter(Boolean).length
    return { completed, done, total: completed.length, complete: done === completed.length }
  }, [websites, datasources, activeKeys])

  const loading = billing === null

  return (
    <div>
      <PageHeader
        title={`Welcome back${store?.name ? `, ${store.name}` : ''}`}
        description="Here's how your storefront assistant is doing this month."
      />

      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      {!loading && !setup.complete && (
        <Card className="mb-6 border-accent/30 bg-accent-soft/30">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Settings2 size={17} className="text-accent" />
                <h2 className="font-display text-lg font-semibold">Finish your setup</h2>
                <Badge tone="accent">{setup.done}/{setup.total}</Badge>
              </div>
              <p className="mt-1 text-sm text-muted">Complete the remaining steps to get your AI shopping assistant ready for your storefront.</p>
              <div className="mt-4 grid gap-2 sm:grid-cols-3">
                {SETUP_STEPS.map((item, index) => {
                  const Icon = item.icon
                  const complete = setup.completed[index]
                  return (
                    <div key={item.id} className="flex items-center gap-2 rounded-lg border border-line bg-card px-3 py-2 text-xs">
                      {complete ? <Check size={14} className="text-success" /> : <Icon size={14} className="text-muted" />}
                      <span className={complete ? 'text-muted line-through' : 'font-medium text-text'}>{item.label}</span>
                    </div>
                  )
                })}
              </div>
            </div>
            <Link to="/onboarding" className="shrink-0">
              <Button>Continue setup <ArrowUpRight size={15} /></Button>
            </Link>
          </div>
        </Card>
      )}

      {!loading && setup.complete && (
        <Card className="mb-6 border-success/30 bg-success/5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold"><Check size={16} className="text-success" /> Setup complete</div>
              <p className="mt-1 text-xs text-muted">Your website, product database, and API authentication are configured.</p>
            </div>
            <Link to="/onboarding" className="text-sm font-medium text-accent hover:text-accent-hover">View setup →</Link>
          </div>
        </Card>
      )}

      {loading ? (
        <div className="flex justify-center py-16 text-muted">
          <Spinner className="h-6 w-6" />
        </div>
      ) : (
        <div className="grid gap-5 sm:grid-cols-3">
          <StatCard
            icon={TrendingUp}
            label="Usage this month"
            value={`$${Number(billing.spent_this_month).toFixed(2)}`}
            sub={`of $${Number(billing.monthly_budget).toFixed(2)} budget`}
            progress={billing.monthly_budget > 0 ? Math.min(1, billing.spent_this_month / billing.monthly_budget) : 0}
          />
          <StatCard
            icon={Globe}
            label="Connected websites"
            value={websites ? websites.count : '—'}
            sub={websites?.count ? `${websites.count} site(s) indexed` : 'None yet'}
            link={{ to: '/websites', text: 'Manage' }}
          />
          <StatCard
            icon={KeyRound}
            label="Active API keys"
            value={keys ? activeKeys : '—'}
            sub="Widget authentication"
            link={{ to: '/api-keys', text: 'Manage' }}
          />
        </div>
      )}

      <div className="mt-8 grid gap-5 sm:grid-cols-2">
        <Card>
          <div className="flex items-center justify-between">
            <h3 className="font-display text-base font-semibold text-text">Current plan</h3>
            <Badge tone="accent">{billing ? capitalize(billing.plan) : '—'}</Badge>
          </div>
          <p className="mt-2 text-sm text-muted">
            {billing?.subscription_status
              ? `Subscription status: ${billing.subscription_status}`
              : 'No active Stripe subscription — you are on the free tier.'}
          </p>
          <Link to="/billing" className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent-hover">
            View billing <ArrowUpRight size={14} />
          </Link>
        </Card>

        <Card>
          <h3 className="font-display text-base font-semibold text-text">Get the widget live</h3>
          <p className="mt-2 text-sm text-muted">
            Connect your website and database, then use the installation step to add the chat widget to your storefront.
          </p>
          <Link to="/onboarding" className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent-hover">
            Open setup <ArrowUpRight size={14} />
          </Link>
        </Card>
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, sub, progress, link }) {
  return (
    <Card>
      <div className="flex items-center gap-2 text-muted"><Icon size={16} strokeWidth={1.9} /><span className="text-sm">{label}</span></div>
      <div className="mt-3 font-display text-2xl font-semibold text-text">{value}</div>
      <div className="mt-1 text-xs text-muted">{sub}</div>
      {typeof progress === 'number' && <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-paper"><div className={`h-full rounded-full ${progress > 0.9 ? 'bg-danger' : 'bg-accent'}`} style={{ width: `${Math.max(4, progress * 100)}%` }} /></div>}
      {link && <Link to={link.to} className="mt-3 inline-block text-xs font-medium text-accent hover:text-accent-hover">{link.text} →</Link>}
    </Card>
  )
}

function capitalize(s) { return s ? s[0].toUpperCase() + s.slice(1) : s }
