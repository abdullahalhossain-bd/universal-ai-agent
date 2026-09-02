import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Check, CreditCard, ExternalLink } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Badge, Button, Card, PageHeader, Spinner } from '../components/ui'

export default function Billing() {
  const [params] = useSearchParams()
  const [summary, setSummary] = useState(null)
  const [plans, setPlans] = useState(null)
  const [error, setError] = useState('')
  const [busyPlan, setBusyPlan] = useState(null)
  const [portalLoading, setPortalLoading] = useState(false)

  const load = () => {
    Promise.all([api.get('/v1/billing/summary'), api.get('/v1/billing/plans')])
      .then(([s, p]) => {
        setSummary(s)
        setPlans(p.plans)
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : 'Failed to load billing.'))
  }

  useEffect(load, [])

  const checkoutStatus = params.get('checkout')

  const upgrade = async (planName) => {
    setError('')
    setBusyPlan(planName)
    try {
      const { checkout_url } = await api.post('/v1/billing/checkout-session', { plan: planName })
      window.location.href = checkout_url
    } catch (err) {
      setError(
        err instanceof ApiError
          ? planFriendlyError(err)
          : 'Failed to start checkout. Please try again.'
      )
      setBusyPlan(null)
    }
  }

  const openPortal = async () => {
    setError('')
    setPortalLoading(true)
    try {
      const { portal_url } = await api.post('/v1/billing/portal-session')
      window.location.href = portal_url
    } catch (err) {
      setError(
        err instanceof ApiError
          ? planFriendlyError(err)
          : 'Failed to open billing portal.'
      )
      setPortalLoading(false)
    }
  }

  return (
    <div>
      <PageHeader title="Billing" description="Manage your plan, usage budget, and payment details." />

      {checkoutStatus === 'success' && (
        <div className="mb-5">
          <Alert tone="success">Payment confirmed — your plan will update shortly.</Alert>
        </div>
      )}
      {checkoutStatus === 'cancelled' && (
        <div className="mb-5">
          <Alert tone="warn">Checkout was cancelled — no changes were made.</Alert>
        </div>
      )}
      {error && (
        <div className="mb-5">
          <Alert>{error}</Alert>
        </div>
      )}

      {summary === null ? (
        <div className="flex justify-center py-16 text-muted">
          <Spinner className="h-6 w-6" />
        </div>
      ) : (
        <>
          <Card className="mb-8">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-display text-base font-semibold text-text">
                    {capitalize(summary.plan)} plan
                  </h3>
                  {summary.subscription_status && (
                    <Badge tone={summary.subscription_status === 'active' ? 'success' : 'warn'}>
                      {summary.subscription_status}
                    </Badge>
                  )}
                </div>
                <p className="mt-1 text-sm text-muted">
                  ${Number(summary.spent_this_month).toFixed(2)} spent of $
                  {Number(summary.monthly_budget).toFixed(2)} this month
                </p>
              </div>
              {summary.has_payment_method && (
                <Button variant="secondary" onClick={openPortal} disabled={portalLoading}>
                  {portalLoading ? <Spinner /> : <CreditCard size={16} />}
                  Manage billing
                  <ExternalLink size={13} />
                </Button>
              )}
            </div>
            <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-paper">
              <div
                className="h-full rounded-full bg-accent"
                style={{
                  width: `${Math.min(
                    100,
                    Math.max(
                      4,
                      (summary.spent_this_month / Math.max(summary.monthly_budget, 0.01)) * 100
                    )
                  )}%`,
                }}
              />
            </div>
          </Card>

          <div className="grid gap-5 sm:grid-cols-3">
            {plans.map((plan) => {
              const isCurrent = plan.name === summary.plan
              return (
                <Card key={plan.name} className={isCurrent ? 'border-accent ring-1 ring-accent' : ''}>
                  <div className="flex items-center justify-between">
                    <h3 className="font-display text-base font-semibold text-text">{plan.label}</h3>
                    {isCurrent && <Badge tone="accent">Current</Badge>}
                  </div>
                  <div className="mt-3 font-display text-2xl font-semibold text-text">
                    ${plan.monthly_budget.toFixed(0)}
                    <span className="text-sm font-normal text-muted"> / mo budget</span>
                  </div>
                  <ul className="mt-4 space-y-2 text-sm text-muted">
                    <li className="flex items-center gap-2">
                      <Check size={14} className="text-success" /> AI chat assistant
                    </li>
                    <li className="flex items-center gap-2">
                      <Check size={14} className="text-success" /> Website + product knowledge
                    </li>
                    <li className="flex items-center gap-2">
                      <Check size={14} className="text-success" /> ${plan.monthly_budget.toFixed(2)}{' '}
                      monthly AI usage budget
                    </li>
                  </ul>
                  <Button
                    className="mt-5 w-full"
                    variant={isCurrent ? 'secondary' : 'primary'}
                    disabled={isCurrent || !plan.billable || busyPlan === plan.name}
                    onClick={() => upgrade(plan.name)}
                  >
                    {busyPlan === plan.name && <Spinner />}
                    {isCurrent
                      ? 'Current plan'
                      : plan.billable
                        ? `Upgrade to ${plan.label}`
                        : 'Included free'}
                  </Button>
                </Card>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function capitalize(s) {
  return s ? s[0].toUpperCase() + s.slice(1) : s
}

function planFriendlyError(err) {
  if (err.status === 503) {
    return 'Billing is not fully configured yet — the store owner needs to add Stripe keys.'
  }
  return typeof err.detail === 'string' ? err.detail : 'Something went wrong.'
}
