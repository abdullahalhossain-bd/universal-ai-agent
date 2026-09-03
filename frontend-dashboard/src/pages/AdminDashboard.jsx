import { useEffect, useMemo, useState } from 'react'
import { BarChart3, Building2, ShieldCheck, Users, Activity, LogOut, RefreshCw, Search, ChevronLeft, ChevronRight, Server } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { adminApi, ApiError } from '../api/client'
import { Alert, Badge, Button, Card, Spinner } from '../components/ui'

export default function AdminDashboard() {
  const { adminUser, adminLogout } = useAuth()
  const [stats, setStats] = useState(null)
  const [stores, setStores] = useState([])
  const [health, setHealth] = useState(null)
  const [features, setFeatures] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [plan, setPlan] = useState('')
  const [offset, setOffset] = useState(0)
  const [selectedStore, setSelectedStore] = useState(null)
  const [detail, setDetail] = useState(null)
  const [saveBusy, setSaveBusy] = useState(false)

  const refresh = async () => {
    setLoading(true); setError('')
    try {
      const [statsData, storesData, healthData, featureData] = await Promise.all([
        adminApi.get('/v1/admin/stats'),
        adminApi.get(`/v1/admin/stores?limit=20&offset=${offset}${query ? `&q=${encodeURIComponent(query)}` : ''}${status ? `&status=${status}` : ''}${plan ? `&plan=${plan}` : ''}`),
        adminApi.get('/v1/admin/system-health'),
        adminApi.get('/v1/admin/features'),
      ])
      setStats(statsData); setStores(storesData.stores || []); setHealth(healthData); setFeatures(featureData.features || [])
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load admin dashboard.')
    } finally { setLoading(false) }
  }
  useEffect(() => { refresh() }, [offset, query, status, plan])

  const openStoreDetails = async (storeId) => {
    try { setDetail(await adminApi.get(`/v1/admin/stores/${storeId}`)); setSelectedStore(storeId) }
    catch (err) { setError(err instanceof ApiError ? err.detail : 'Unable to load store details.') }
  }

  const saveStore = async () => {
    if (!selectedStore) return
    setSaveBusy(true); setError('')
    try {
      await adminApi.patch(`/v1/admin/stores/${selectedStore}`, { status: detail.status, plan: detail.plan, enabled_features: detail.enabled_features || {} })
      await refresh(); await openStoreDetails(selectedStore)
    } catch (err) { setError(err instanceof ApiError ? err.detail : 'Save failed.') }
    finally { setSaveBusy(false) }
  }

  const toggleFeature = (key) => setDetail(prev => ({ ...prev, enabled_features: { ...(prev.enabled_features || {}), [key]: !(prev.enabled_features || {})[key] } }))

  const statCards = useMemo(() => !stats ? [] : [
    { label: 'Total merchants', value: stats.total_stores, icon: Building2 },
    { label: 'Active merchants', value: stats.active_stores, icon: Users },
    { label: 'Suspended', value: stats.suspended_stores, icon: ShieldCheck },
    { label: 'MTD spend', value: `$${Number(stats.month_to_date_spend || 0).toFixed(2)}`, icon: BarChart3 },
  ], [stats])

  return <div className="min-h-screen bg-paper p-6"><div className="mx-auto max-w-7xl">
    <div className="mb-6 flex flex-wrap items-center justify-between gap-4"><div><h1 className="font-display text-3xl font-semibold text-text">Platform admin</h1><p className="text-sm text-muted">Welcome, {adminUser?.email}</p></div><div className="flex items-center gap-3"><Button variant="secondary" onClick={refresh}><RefreshCw size={15}/> Refresh</Button><Button variant="secondary" onClick={adminLogout}><LogOut size={15}/> Log out</Button></div></div>
    {error && <div className="mb-5"><Alert>{error}</Alert></div>}
    {loading ? <div className="flex justify-center py-16 text-muted"><Spinner className="h-6 w-6"/></div> : <>
      <div className="mb-6 grid gap-4 md:grid-cols-4">{statCards.map(({label,value,icon:Icon}) => <Card key={label}><div className="flex items-center justify-between"><span className="text-sm text-muted">{label}</span><Icon size={16} className="text-accent"/></div><div className="mt-4 font-display text-3xl font-semibold text-text">{value}</div></Card>)}</div>

      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <Card><div className="mb-3 flex items-center gap-2 font-display text-base font-semibold text-text"><Server size={16}/> System health</div><div className="grid gap-2 sm:grid-cols-3">{Object.entries(health?.checks || {}).map(([key,value]) => <div key={key} className="rounded-lg border border-line bg-paper p-3"><div className="text-xs uppercase text-muted">{key}</div><div className="mt-1 flex items-center justify-between"><span className="text-sm text-text">{value}</span><Badge tone={value === 'ok' ? 'success' : 'warn'}>{value === 'ok' ? 'Healthy' : 'Check'}</Badge></div></div>)}</div></Card>
        <Card><div className="mb-3 font-display text-base font-semibold text-text">Feature catalog</div><div className="space-y-2">{features.map(f => <div key={f.key} className="flex items-center justify-between rounded-lg border border-line bg-paper px-3 py-2"><div><div className="text-sm font-medium text-text">{f.label || f.key}</div><div className="text-xs text-muted">{f.key}</div></div><Badge tone="muted">Platform control</Badge></div>)}</div></Card>
      </div>

      <Card><div className="mb-4 flex flex-wrap gap-3"><div className="relative min-w-[180px] flex-1"><Search size={15} className="absolute left-3 top-3 text-muted"/><input className="w-full rounded-lg border border-line bg-white py-2.5 pl-9 pr-3 text-sm text-text" placeholder="Search merchants..." value={query} onChange={e=>setQuery(e.target.value)}/></div><select value={status} onChange={e=>setStatus(e.target.value)} className="rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-text"><option value="">Any status</option><option value="setup">setup</option><option value="active">active</option><option value="suspended">suspended</option></select><select value={plan} onChange={e=>setPlan(e.target.value)} className="rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-text"><option value="">Any plan</option><option value="starter">starter</option><option value="growth">growth</option><option value="pro">pro</option></select></div>
        <div className="overflow-hidden rounded-xl border border-line"><table className="w-full text-left text-sm"><thead className="bg-paper text-xs uppercase tracking-wide text-muted"><tr><th className="px-4 py-3">Merchant</th><th className="px-4 py-3">Plan</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Users</th><th className="px-4 py-3">MTD spend</th></tr></thead><tbody>{stores.map(store=><tr key={store.id} className="cursor-pointer border-t border-line hover:bg-paper" onClick={()=>openStoreDetails(store.id)}><td className="px-4 py-3 font-medium text-text">{store.name}</td><td className="px-4 py-3">{store.plan}</td><td className="px-4 py-3"><Badge tone={store.status==='active'?'success':store.status==='suspended'?'danger':'warn'}>{store.status}</Badge></td><td className="px-4 py-3">{store.user_count}</td><td className="px-4 py-3">${Number(store.month_to_date_spend||0).toFixed(2)}</td></tr>)}</tbody></table></div>
        <div className="mt-4 flex items-center justify-between text-sm text-muted"><span>Page {Math.floor(offset/20)+1}</span><div className="flex gap-2"><Button variant="secondary" size="sm" onClick={()=>setOffset(p=>Math.max(0,p-20))} disabled={offset===0}><ChevronLeft size={14}/> Prev</Button><Button variant="secondary" size="sm" onClick={()=>setOffset(p=>p+20)}>Next <ChevronRight size={14}/></Button></div></div>
      </Card>

      {detail && <Card className="mt-6"><div className="mb-4 flex flex-wrap items-center justify-between gap-4"><div><h2 className="font-display text-xl font-semibold text-text">{detail.name}</h2><p className="text-sm text-muted">{detail.website_url || 'No website URL'}</p></div><div className="flex gap-2"><select value={detail.status} onChange={e=>setDetail(p=>({...p,status:e.target.value}))} className="rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-text"><option value="setup">setup</option><option value="active">active</option><option value="suspended">suspended</option></select><select value={detail.plan} onChange={e=>setDetail(p=>({...p,plan:e.target.value}))} className="rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-text"><option value="starter">starter</option><option value="growth">growth</option><option value="pro">pro</option></select><Button onClick={saveStore} disabled={saveBusy}>{saveBusy?<Spinner/>:'Save changes'}</Button></div></div>
        <div className="grid gap-5 md:grid-cols-2"><div className="rounded-lg border border-line bg-paper p-4"><div className="mb-2 flex items-center gap-2 text-sm font-medium text-text"><Activity size={15}/> Usage summary</div><div className="text-sm text-muted">Monthly spend: ${Number(detail.month_to_date_spend||0).toFixed(2)}</div><div className="text-sm text-muted">Monthly budget: ${Number(detail.monthly_budget||0).toFixed(2)}</div><div className="text-sm text-muted">Users: {detail.user_count}</div></div>
          <div className="rounded-lg border border-line bg-paper p-4"><div className="mb-2 flex items-center gap-2 text-sm font-medium text-text"><ShieldCheck size={15}/> Feature controls</div><div className="space-y-2">{features.map(f=>{const on=Boolean((detail.enabled_features||{})[f.key]);return <button type="button" key={f.key} onClick={()=>toggleFeature(f.key)} className="flex w-full items-center justify-between rounded-lg border border-line bg-white px-3 py-2 text-left"><span className="text-sm text-text">{f.label || f.key}</span><Badge tone={on?'success':'muted'}>{on?'On':'Off'}</Badge></button>})}</div></div></div>
        <div className="mt-6 grid gap-5 md:grid-cols-2"><div><h3 className="mb-2 font-display text-base font-semibold text-text">API keys</h3><div className="space-y-2">{(detail.api_keys||[]).map(key=><div key={key.id} className="rounded-lg border border-line bg-paper px-3 py-2 text-sm text-muted">{key.name} · {key.key_prefix}… · {key.revoked?'revoked':'active'}</div>)}{(detail.api_keys||[]).length===0&&<div className="text-sm text-muted">No API keys.</div>}</div></div><div><h3 className="mb-2 font-display text-base font-semibold text-text">Datasources</h3><div className="space-y-2">{(detail.datasources||[]).map(ds=><div key={ds.id} className="rounded-lg border border-line bg-paper px-3 py-2 text-sm text-muted">{ds.name} · {ds.connector_type} · {ds.last_sync_status||'not synced'}</div>)}{(detail.datasources||[]).length===0&&<div className="text-sm text-muted">No datasource.</div>}</div></div></div>
      </Card>}
    </>}
  </div></div>
}
