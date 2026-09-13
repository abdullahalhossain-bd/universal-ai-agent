import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertCircle, Check, CreditCard, Download, ExternalLink, RefreshCw } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Badge, Button, Card, PageHeader, Spinner } from '../components/ui'

export default function Billing() {
  const [params] = useSearchParams()
  const [summary, setSummary] = useState(null)
  const [plans, setPlans] = useState(null)
  const [invoices, setInvoices] = useState([])
  const [error, setError] = useState('')
  const [busyPlan, setBusyPlan] = useState(null)
  const [portalLoading, setPortalLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)

  const load = async () => {
    setError('')
    try {
      const [s, p, h] = await Promise.all([
        api.get('/v1/billing/summary'),
        api.get('/v1/billing/plans'),
        api.get('/v1/billing/invoices?limit=12'),
      ])
      setSummary(s)
      setPlans(p.plans)
      setInvoices(h.invoices || [])
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load billing.')
    }
  }

  const refreshHistory = async () => {
    setHistoryLoading(true)
    try {
      const h = await api.get('/v1/billing/invoices?limit=12')
      setInvoices(h.invoices || [])
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to refresh billing history.')
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const checkoutStatus = params.get('checkout')

  const upgrade = async (planName) => {
    setError('')
    setBusyPlan(planName)
    try {
      const { checkout_url } = await api.post('/v1/billing/checkout-session', { plan: planName })
      window.location.href = checkout_url
    } catch (err) {
      setError(err instanceof ApiError ? planFriendlyError(err) : 'Failed to start checkout. Please try again.')
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
      setError(err instanceof ApiError ? planFriendlyError(err) : 'Failed to open billing portal.')
      setPortalLoading(false)
    }
  }

  return (
    <div>
      <PageHeader title="Billing" description="Manage your plan, usage budget, payment details, and invoices." />

      {checkoutStatus === 'success' && <div className="mb-5"><Alert tone="success">Payment confirmed — your plan will update shortly.</Alert></div>}
      {checkoutStatus === 'cancelled' && <div className="mb-5"><Alert tone="warn">Checkout was cancelled — no changes were made.</Alert></div>}
      {error && <div className="mb-5"><Alert>{error}</Alert></div>}

      {summary === null ? (
        <div className="flex justify-center py-16 text-muted"><Spinner className="h-6 w-6" /></div>
      ) : (
        <>
          <Card className="mb-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-display text-base font-semibold text-text">{capitalize(summary.plan)} plan</h3>
                  {summary.subscription_status && <Badge tone={summary.subscription_status === 'active' ? 'success' : 'warn'}>{summary.subscription_status}</Badge>}
                </div>
                <p className="mt-1 text-sm text-muted">
                  ${Number(summary.spent_this_month).toFixed(2)} used of ${Number(summary.monthly_budget).toFixed(2)} monthly AI budget
                </p>
              </div>
              {summary.has_payment_method && <Button variant="secondary" onClick={openPortal} disabled={portalLoading}>
                {portalLoading ? <Spinner /> : <CreditCard size={16} />} Manage billing <ExternalLink size={13} />
              </Button>}
            </div>
            <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-paper">
              <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${summary.usage_percent}%` }} />
            </div>
            <div className="mt-2 flex justify-between text-xs text-muted">
              <span>{summary.usage_percent.toFixed(1)}% used</span>
              <span>${Number(summary.remaining_budget).toFixed(2)} remaining</span>
            </div>
          </Card>

          {summary.usage_warning && (
            <div className="mb-6">
              <Alert tone={summary.usage_warning === 'critical' ? 'danger' : 'warn'}>
                <div className="flex items-start gap-2">
                  <AlertCircle size={17} className="mt-0.5 shrink-0" />
                  <div>
                    <strong>{summary.usage_warning === 'critical' ? 'AI usage budget reached' : 'AI usage is getting high'}</strong>
                    <div className="mt-0.5 text-sm">
                      {summary.usage_warning === 'critical'
                        ? 'Your monthly AI budget has been reached. Upgrade your plan to continue with more usage.'
                        : `You have used ${summary.usage_percent.toFixed(0)}% of this month's AI budget. Consider upgrading before reaching the limit.`}
                    </div>
                  </div>
                </div>
              </Alert>
            </div>
          )}

          <div className="mb-8 grid gap-5 sm:grid-cols-3">
            {plans.map((plan) => {
              const isCurrent = plan.name === summary.plan
              return <Card key={plan.name} className={isCurrent ? 'border-accent ring-1 ring-accent' : ''}>
                <div className="flex items-center justify-between">
                  <h3 className="font-display text-base font-semibold text-text">{plan.label}</h3>
                  {isCurrent && <Badge tone="accent">Current</Badge>}
                </div>
                <div className="mt-3 font-display text-2xl font-semibold text-text">
                  {plan.billable
                    ? <>${plan.monthly_budget.toFixed(0)}<span className="text-sm font-normal text-muted"> / mo budget</span></>
                    : 'Free'}
                </div>
                <ul className="mt-4 space-y-2 text-sm text-muted">
                  <li className="flex items-center gap-2"><Check size={14} className="text-success" /> AI chat assistant</li>
                  <li className="flex items-center gap-2"><Check size={14} className="text-success" /> Website + product knowledge</li>
                  <li className="flex items-center gap-2"><Check size={14} className="text-success" /> ${plan.monthly_budget.toFixed(2)} monthly AI usage budget</li>
                </ul>
                <Button className="mt-5 w-full" variant={isCurrent ? 'secondary' : 'primary'} disabled={isCurrent || !plan.billable || busyPlan === plan.name} onClick={() => upgrade(plan.name)}>
                  {busyPlan === plan.name && <Spinner />}
                  {isCurrent ? 'Current plan' : plan.billable ? `Upgrade to ${plan.label}` : 'Included free'}
                </Button>
              </Card>
            })}
          </div>

          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="font-display text-base font-semibold text-text">Billing history</h3>
                <p className="mt-1 text-sm text-muted">Invoices and payment status from Stripe.</p>
              </div>
              <Button variant="secondary" onClick={refreshHistory} disabled={historyLoading}>
                {historyLoading ? <Spinner /> : <RefreshCw size={15} />} Refresh
              </Button>
            </div>
            <div className="mt-5 overflow-x-auto">
              {invoices.length === 0 ? (
                <div className="rounded-lg border border-dashed border-line px-4 py-10 text-center text-sm text-muted">
                  No invoices yet. Your billing history will appear here after your first payment.
                </div>
              ) : (
                <table className="w-full min-w-[650px] text-left text-sm">
                  <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
                    <tr><th className="pb-3">Invoice</th><th className="pb-3">Date</th><th className="pb-3">Amount</th><th className="pb-3">Status</th><th className="pb-3 text-right">Receipt</th></tr>
                  </thead>
                  <tbody>
                    {invoices.map((invoice) => <tr key={invoice.id} className="border-b border-line last:border-0">
                      <td className="py-3 font-medium text-text">{invoice.number || invoice.id}</td>
                      <td className="py-3 text-muted">{formatUnixDate(invoice.created)}</td>
                      <td className="py-3 text-text">{formatMoney(invoice.amount_paid ?? invoice.total, invoice.currency)}</td>
                      <td className="py-3"><Badge tone={invoice.status === 'paid' ? 'success' : invoice.status === 'open' ? 'warn' : 'neutral'}>{invoice.status || 'unknown'}</Badge></td>
                      <td className="py-3 text-right">
                        {invoice.hosted_invoice_url && <a href={invoice.hosted_invoice_url} target="_blank" rel="noreferrer" className="mr-3 inline-flex items-center gap-1 text-accent hover:underline">View <ExternalLink size={13} /></a>}
                        {invoice.invoice_pdf && <a href={invoice.invoice_pdf} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-muted hover:text-text"><Download size={13} /> PDF</a>}
                      </td>
                    </tr>)}
                  </tbody>
                </table>
              )}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}

function capitalize(s) { return s ? s[0].toUpperCase() + s.slice(1) : s }
function formatUnixDate(value) { return value ? new Date(value * 1000).toLocaleDateString() : '—' }
function formatMoney(cents, currency = 'usd') { return new Intl.NumberFormat(undefined, { style: 'currency', currency: String(currency).toUpperCase() }).format(Number(cents || 0) / 100) }
function planFriendlyError(err) {
  if (err.status === 503) return 'Billing is not fully configured yet — the store owner needs to add Stripe keys.'
  return typeof err.detail === 'string' ? err.detail : 'Something went wrong.'
}
