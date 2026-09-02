import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Globe, KeyRound, TrendingUp } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { Badge, Card, PageHeader, Spinner } from '../components/ui'

export default function Overview() {
  const { store } = useAuth()
  const [billing, setBilling] = useState(null)
  const [websites, setWebsites] = useState(null)
  const [keys, setKeys] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.allSettled([
      api.get('/v1/billing/summary'),
      api.get('/v1/knowledge/websites'),
      api.get('/v1/stores/me/api-keys'),
    ]).then(([b, w, k]) => {
      if (b.status === 'fulfilled') setBilling(b.value)
      else setError('Some data failed to load.')
      if (w.status === 'fulfilled') setWebsites(w.value)
      if (k.status === 'fulfilled') setKeys(k.value)
    })
  }, [])

  const loading = billing === null

  return (
    <div>
      <PageHeader
        title={`Welcome back${store?.name ? `, ${store.name}` : ''}`}
        description="Here's how your storefront assistant is doing this month."
      />

      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

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
            progress={
              billing.monthly_budget > 0
                ? Math.min(1, billing.spent_this_month / billing.monthly_budget)
                : 0
            }
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
            value={
              keys ? keys.api_keys.filter((k) => k.active).length : '—'
            }
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
          <Link
            to="/billing"
            className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent-hover"
          >
            View billing <ArrowUpRight size={14} />
          </Link>
        </Card>

        <Card>
          <h3 className="font-display text-base font-semibold text-text">Get the widget live</h3>
          <p className="mt-2 text-sm text-muted">
            Connect a website so the assistant knows your products and policies, then embed the
            chat widget on your storefront.
          </p>
          <Link
            to="/websites"
            className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent-hover"
          >
            Connect a website <ArrowUpRight size={14} />
          </Link>
        </Card>
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, sub, progress, link }) {
  return (
    <Card>
      <div className="flex items-center gap-2 text-muted">
        <Icon size={16} strokeWidth={1.9} />
        <span className="text-sm">{label}</span>
      </div>
      <div className="mt-3 font-display text-2xl font-semibold text-text">{value}</div>
      <div className="mt-1 text-xs text-muted">{sub}</div>
      {typeof progress === 'number' && (
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-paper">
          <div
            className={`h-full rounded-full ${progress > 0.9 ? 'bg-danger' : 'bg-accent'}`}
            style={{ width: `${Math.max(4, progress * 100)}%` }}
          />
        </div>
      )}
      {link && (
        <Link
          to={link.to}
          className="mt-3 inline-block text-xs font-medium text-accent hover:text-accent-hover"
        >
          {link.text} →
        </Link>
      )}
    </Card>
  )
}

function capitalize(s) {
  return s ? s[0].toUpperCase() + s.slice(1) : s
}
