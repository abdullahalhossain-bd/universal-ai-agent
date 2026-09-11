import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, BarChart3, HelpCircle, MessageCircleQuestion, RefreshCw, Search, Target } from 'lucide-react'
import { api } from '../api/client'
import { Badge, Button, Card, PageHeader, Spinner } from '../components/ui'

const PERIODS = [7, 30, 90]

export default function Analytics() {
  const [days, setDays] = useState(30)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true); setError('')
    try {
      const [overview, daily, questions, gaps, intents] = await Promise.all([
        api.get(`/v1/analytics/overview?days=${days}`),
        api.get(`/v1/analytics/daily?days=${days}`),
        api.get(`/v1/analytics/popular-questions?days=${days}&limit=12`),
        api.get(`/v1/analytics/knowledge-gaps?days=${days}&limit=12`),
        api.get(`/v1/analytics/intents?days=${days}`),
      ])
      setData({ overview, daily, questions, gaps, intents })
    } catch (e) { setError(e?.message || 'Analytics could not be loaded.') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [days])

  const maxDaily = useMemo(() => Math.max(1, ...(data?.daily?.series || []).map(x => x.questions)), [data])

  return <div>
    <PageHeader
      title="Conversation intelligence"
      description="Understand what customers ask, what the assistant handles, and where your catalog or knowledge needs improvement."
      actions={<div className="flex items-center gap-2"><select value={days} onChange={e => setDays(Number(e.target.value))} className="rounded-lg border border-line bg-card px-3 py-2 text-sm text-text">{PERIODS.map(p => <option key={p} value={p}>{p} days</option>)}</select><Button variant="secondary" onClick={load}><RefreshCw size={14} /> Refresh</Button></div>}
    />

    {error && <Card className="mb-5 border-danger/30"><div className="flex items-center gap-2 text-sm text-danger"><AlertTriangle size={16}/>{error}</div></Card>}
    {loading && !data ? <div className="flex justify-center py-20 text-muted"><Spinner className="h-6 w-6" /></div> : data && <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric icon={MessageCircleQuestion} label="Customer questions" value={data.overview.questions} sub={`${data.overview.conversations} conversations`} />
        <Metric icon={Target} label="Answer coverage" value={`${Math.round(data.overview.answer_coverage_rate * 100)}%`} sub={`${data.overview.unanswered_questions} no-result events`} tone={data.overview.answer_coverage_rate >= .85 ? 'good' : 'warn'} />
        <Metric icon={Search} label="Product searches" value={data.overview.product_searches} sub="Catalog-driven requests" />
        <Metric icon={HelpCircle} label="Likely gaps" value={data.gaps.gaps.length} sub="Grouped topics needing review" tone={data.gaps.gaps.length ? 'warn' : 'good'} />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1.4fr_.8fr]">
        <Card>
          <div className="flex items-center justify-between"><div><h2 className="font-display text-base font-semibold">Question volume</h2><p className="mt-1 text-xs text-muted">Daily questions vs. no-result events</p></div><BarChart3 size={17} className="text-muted" /></div>
          <div className="mt-6 flex h-44 items-end gap-1.5 overflow-hidden">
            {(data.daily.series || []).map(day => <div key={day.date} title={`${day.date}: ${day.questions} questions, ${day.unanswered} no-result`} className="group flex min-w-[5px] flex-1 flex-col justify-end gap-1">
              <div className="rounded-t bg-accent/70 transition-all group-hover:bg-accent" style={{height: `${Math.max(3, day.questions / maxDaily * 100)}%`}} />
              {day.unanswered > 0 && <div className="h-1 rounded-sm bg-danger/70" />}
            </div>)}
          </div>
          <div className="mt-3 flex justify-between text-[11px] text-muted"><span>{data.daily.series?.[0]?.date || ''}</span><span>{data.daily.series?.at(-1)?.date || ''}</span></div>
        </Card>

        <Card>
          <h2 className="font-display text-base font-semibold">Intent mix</h2>
          <div className="mt-4 space-y-3">{data.intents.intents.slice(0, 7).map(item => <div key={item.intent}><div className="flex justify-between text-xs"><span className="font-medium text-text">{prettyIntent(item.intent)}</span><span className="text-muted">{item.count} · {item.unanswered} no-result</span></div><div className="mt-1.5 h-1.5 rounded-full bg-paper"><div className="h-full rounded-full bg-accent" style={{width: `${Math.max(3, item.count / Math.max(1, data.overview.questions) * 100)}%`}} /></div></div>)}</div>
        </Card>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <Card>
          <div className="flex items-start justify-between"><div><h2 className="font-display text-base font-semibold">Most common questions</h2><p className="mt-1 text-xs text-muted">Grouped by lightweight wording fingerprint; examples show real customer phrasing.</p></div><Badge tone="accent">Top 12</Badge></div>
          <div className="mt-4 divide-y divide-line">{data.questions.questions.length ? data.questions.questions.map((q, i) => <div key={q.fingerprint} className="py-3"><div className="flex gap-3"><span className="nums w-5 text-xs text-muted">{i + 1}</span><div className="min-w-0 flex-1"><div className="text-sm font-medium text-text">{q.question}</div><div className="mt-1 text-[11px] text-muted">{q.count}× asked · {Math.round(q.answer_rate * 100)}% with catalog result · {Object.keys(q.intents).map(prettyIntent).join(', ')}</div>{q.examples?.length > 1 && <div className="mt-2 text-xs text-muted">Also: {q.examples.slice(1).join(' · ')}</div>}</div></div></div>) : <Empty text="No questions recorded for this period." />}</div>
        </Card>

        <Card>
          <div className="flex items-start justify-between"><div><h2 className="font-display text-base font-semibold">Likely knowledge & catalog gaps</h2><p className="mt-1 text-xs text-muted">Prioritized from no-result events. Review before adding content.</p></div><Badge tone="warning">Needs review</Badge></div>
          <div className="mt-4 divide-y divide-line">{data.gaps.gaps.length ? data.gaps.gaps.map((gap, i) => <div key={`${gap.kind}-${gap.question}-${i}`} className="py-3"><div className="flex gap-3"><div className="mt-0.5 rounded-md bg-danger/10 p-1.5 text-danger"><AlertTriangle size={14}/></div><div className="min-w-0 flex-1"><div className="text-sm font-medium text-text">{gap.question}</div><div className="mt-1 text-[11px] text-muted">{gap.count}× · {labelGap(gap.kind)}</div><p className="mt-1 text-xs text-muted">{gap.explanation}</p>{gap.examples?.length > 1 && <div className="mt-2 text-xs text-muted">Examples: {gap.examples.slice(0, 2).join(' · ')}</div>}</div></div></div>) : <Empty text="No likely gaps detected. Keep monitoring new questions." />}</div>
        </Card>
      </div>

      <Card className="mt-6 border-accent/20 bg-accent-soft/20"><div className="flex gap-3"><div className="mt-0.5 rounded-md bg-accent/10 p-1.5 text-accent"><HelpCircle size={15}/></div><div><h3 className="text-sm font-semibold">How to use this report</h3><p className="mt-1 text-xs leading-5 text-muted">A no-result event does not automatically mean the AI gave a wrong answer. Use the gap list to find repeated demand for missing products, attributes, policies, delivery information, or other merchant knowledge. Add the missing data/content, then watch whether the same topic's answer coverage improves.</p></div></div></Card>
    </>}
  </div>
}

function Metric({ icon: Icon, label, value, sub, tone }) { return <Card><div className="flex items-center gap-2 text-muted"><Icon size={16}/><span className="text-xs">{label}</span></div><div className={`nums mt-3 font-display text-[28px] font-medium ${tone === 'warn' ? 'text-warning' : tone === 'good' ? 'text-success' : 'text-text'}`}>{value}</div><div className="mt-1 text-xs text-muted">{sub}</div></Card> }
function Empty({ text }) { return <div className="py-8 text-center text-sm text-muted">{text}</div> }
function prettyIntent(value) { return String(value || 'unknown').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase()) }
function labelGap(value) { return value === 'catalog_gap' ? 'Catalog match gap' : value === 'human_handoff' ? 'Human handoff' : 'Knowledge gap candidate' }
