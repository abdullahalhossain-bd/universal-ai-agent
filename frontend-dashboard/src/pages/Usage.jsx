import { useEffect, useState } from 'react'
import { BarChart3, Coins, Gauge, Wallet } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Card, PageHeader, Spinner } from '../components/ui'

export default function Usage() {
  const [summary, setSummary] = useState(null)
  const [usage, setUsage] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.allSettled([
      api.get('/v1/billing/summary'),
      api.get('/v1/admin/usage?limit=10'),
    ]).then(([billing, usageResult]) => {
      if (billing.status === 'fulfilled') setSummary(billing.value)
      if (usageResult.status === 'fulfilled') setUsage(usageResult.value)
      if (billing.status === 'rejected' || usageResult.status === 'rejected') {
        setError('Usage data could not be loaded. Please try again.')
      }
    }).catch((err) => {
      setError(err instanceof ApiError ? err.detail : 'Usage load failed.')
    })
  }, [])

  const spent = Number(summary?.spent_this_month || 0)
  const budget = Number(summary?.monthly_budget || 0)
  const remaining = Math.max(0, budget - spent)

  if (!summary) {
    return (
      <div>
        <PageHeader title="Usage & quota" description="Track token consumption, remaining budget, and recent AI activity." />
        <div className="flex justify-center py-12 text-muted">
          <Spinner className="h-6 w-6" />
        </div>
      </div>
    )
  }

  return (
    <div>
      <PageHeader title="Usage & quota" description="Track token consumption, remaining budget, and recent AI activity." />

      {error && <div className="mb-5"><Alert>{error}</Alert></div>}

      <div className="grid gap-5 md:grid-cols-4">
        <Card>
          <div className="flex items-center gap-2 text-muted"><Gauge size={16} /> Usage</div>
          <div className="mt-4 text-2xl font-display font-semibold text-text">${spent.toFixed(2)}</div>
          <div className="mt-1 text-xs text-muted">This month</div>
        </Card>
        <Card>
          <div className="flex items-center gap-2 text-muted"><Wallet size={16} /> Remaining</div>
          <div className="mt-4 text-2xl font-display font-semibold text-text">${remaining.toFixed(2)}</div>
          <div className="mt-1 text-xs text-muted">Available budget</div>
        </Card>
        <Card>
          <div className="flex items-center gap-2 text-muted"><Coins size={16} /> Plan</div>
          <div className="mt-4 text-2xl font-display font-semibold text-text">{summary.plan}</div>
          <div className="mt-1 text-xs text-muted">Current subscription</div>
        </Card>
        <Card>
          <div className="flex items-center gap-2 text-muted"><BarChart3 size={16} /> Weekly quota</div>
          <div className="mt-4 text-2xl font-display font-semibold text-text">{budget > 0 ? `${Math.max(0, ((remaining / budget) * 100)).toFixed(0)}%` : '0%'}</div>
          <div className="mt-1 text-xs text-muted">Of your monthly budget left</div>
        </Card>
      </div>

      <Card className="mt-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-display text-base font-semibold text-text">Recent usage activity</h3>
          <span className="text-xs text-muted">Latest 10 records</span>
        </div>

        {usage?.usage?.length ? (
          <div className="space-y-3">
            {usage.usage.map((item) => (
              <div key={item.id} className="flex flex-col justify-between gap-2 rounded-lg border border-line bg-paper px-3 py-2 md:flex-row md:items-center">
                <div>
                  <div className="font-medium text-text">{item.route}</div>
                  <div className="text-xs text-muted">{item.model || 'Unknown model'} · {new Date(item.created_at).toLocaleString()}</div>
                </div>
                <div className="text-sm font-medium text-text">${Number(item.estimated_cost || 0).toFixed(4)}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-muted">No usage history yet.</div>
        )}
      </Card>
    </div>
  )
}
