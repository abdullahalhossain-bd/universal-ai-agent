import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, Check, Copy, Database, Globe, KeyRound, Loader2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { Alert, Badge, Button, Card, Input, Spinner } from '../components/ui'

const STEPS = [
  { id: 'website', label: 'Website', icon: Globe },
  { id: 'database', label: 'Database', icon: Database },
  { id: 'api', label: 'API key', icon: KeyRound },
]

export default function Onboarding() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [websiteState, setWebsiteState] = useState(null)
  const [datasource, setDatasource] = useState(null)
  const [keys, setKeys] = useState([])
  const [issuedKey, setIssuedKey] = useState(null)
  const [copied, setCopied] = useState(false)
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')

  const [db, setDb] = useState({
    name: 'Main database',
    connector_type: 'postgresql',
    connection_url: '',
    table_name: '',
  })

  useEffect(() => {
    let active = true
    Promise.allSettled([
      api.get('/v1/knowledge/websites'),
      api.get('/v1/datasources'),
      api.get('/v1/stores/me/api-keys'),
    ]).then(([web, data, keyData]) => {
      if (!active) return
      if (web.status === 'fulfilled') {
        setWebsiteState(web.value)
        const first = web.value.websites?.[0]
        if (first) setWebsiteUrl(`https://${first.domain}`)
      }
      if (data.status === 'fulfilled') setDatasource(data.value.items?.[0] || null)
      if (keyData.status === 'fulfilled') setKeys(keyData.value.api_keys || [])
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [])

  const hasWebsite = Boolean(websiteState?.count)
  const hasDatabase = Boolean(datasource)
  const activeKey = useMemo(() => keys.find((key) => key.active), [keys])

  const setField = (field) => (event) => setDb((current) => ({ ...current, [field]: event.target.value }))

  const connectWebsite = async () => {
    setWorking(true)
    setError('')
    try {
      const result = await api.post('/v1/knowledge/ingest', { website_url: websiteUrl })
      setWebsiteState((current) => ({ ...(current || {}), count: Math.max(1, current?.count || 0), websites: current?.websites || [] }))
      setWebsiteState((current) => ({ ...current, lastResult: result }))
      setStep(1)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'We could not crawl that website.')
    } finally {
      setWorking(false)
    }
  }

  const connectDatabase = async () => {
    setWorking(true)
    setError('')
    try {
      const test = await api.post('/v1/datasources/test', {
        connector_type: db.connector_type,
        connection_url: db.connection_url,
      })
      if (!test.connected) throw new Error('Database connection failed.')
      const created = await api.post('/v1/datasources', {
        name: db.name,
        connector_type: db.connector_type,
        connection_url: db.connection_url,
        table_name: db.table_name || undefined,
        active: true,
        full_sync: true,
      })
      setDatasource(created)
      setStep(2)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : err.message || 'We could not connect to that database.')
    } finally {
      setWorking(false)
    }
  }

  const createKey = async () => {
    setWorking(true)
    setError('')
    try {
      const created = await api.post('/v1/stores/me/api-keys', { name: 'Production widget' })
      setIssuedKey(created.api_key)
      setKeys((current) => [...current, created])
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create API key.')
    } finally {
      setWorking(false)
    }
  }

  const finish = () => navigate('/')

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-accent"><Spinner className="h-6 w-6" /></div>
  }

  return (
    <div className="min-h-screen bg-paper px-4 py-10 text-text">
      <div className="mx-auto max-w-3xl">
        <div className="mb-8 text-center">
          <Badge tone="accent">Quick setup</Badge>
          <h1 className="mt-3 font-display text-3xl font-semibold">Get your AI agent live</h1>
          <p className="mx-auto mt-2 max-w-xl text-sm text-muted">
            Connect your storefront and product database, then use your API key to install the chat widget.
          </p>
        </div>

        <div className="mb-6 grid grid-cols-3 gap-2">
          {STEPS.map((item, index) => {
            const Icon = item.icon
            const complete = index < step || (index === 0 && hasWebsite) || (index === 1 && hasDatabase)
            return (
              <button key={item.id} type="button" onClick={() => index <= step && setStep(index)} className={`rounded-lg border px-3 py-3 text-left ${index === step ? 'border-accent bg-accent-soft' : 'border-line bg-card'}`}>
                <div className="flex items-center gap-2 text-sm font-medium">
                  {complete ? <Check size={16} /> : <Icon size={16} />}
                  {index + 1}. {item.label}
                </div>
              </button>
            )
          })}
        </div>

        {error && <div className="mb-5"><Alert>{error}</Alert></div>}

        <Card className="p-6">
          {step === 0 && (
            <>
              <h2 className="font-display text-xl font-semibold">Connect your website</h2>
              <p className="mt-1 text-sm text-muted">We will crawl your storefront so the assistant can answer questions about products, policies, and shipping.</p>
              <div className="mt-6">
                <Input label="Website URL" type="url" required value={websiteUrl} onChange={(e) => setWebsiteUrl(e.target.value)} placeholder="https://yourstore.com" />
              </div>
              {hasWebsite && <p className="mt-3 text-sm text-success">✓ A website is already connected. You can re-crawl it or continue.</p>}
              <div className="mt-6 flex justify-end gap-2">
                <Button variant="secondary" onClick={() => setStep(1)}>Skip for now</Button>
                <Button onClick={connectWebsite} disabled={working || !websiteUrl}>
                  {working && <Spinner />}{working ? 'Crawling…' : hasWebsite ? 'Re-crawl & continue' : 'Connect & continue'} <ArrowRight size={16} />
                </Button>
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <h2 className="font-display text-xl font-semibold">Connect your product database</h2>
              <p className="mt-1 text-sm text-muted">Validate the connection first, then save it for catalog syncing.</p>
              {hasDatabase ? (
                <div className="mt-6 rounded-lg border border-line bg-paper p-4">
                  <div className="font-medium">{datasource.name}</div>
                  <div className="mt-1 text-sm text-muted">{datasource.connector_type} · {datasource.table_name || 'No table selected'}</div>
                  <div className="mt-2 text-sm text-success">✓ Database connected</div>
                </div>
              ) : (
                <div className="mt-6 space-y-4">
                  <div className="grid gap-4 md:grid-cols-2">
                    <Input label="Connection name" value={db.name} onChange={setField('name')} />
                    <label className="block"><span className="mb-1.5 block text-sm font-medium">Database</span><select value={db.connector_type} onChange={setField('connector_type')} className="w-full rounded-lg border border-line bg-white px-3.5 py-2.5 text-sm"><option value="postgresql">PostgreSQL</option><option value="mysql">MySQL</option></select></label>
                  </div>
                  <Input label="Connection URL" type="password" value={db.connection_url} onChange={setField('connection_url')} placeholder="postgresql://user:password@host:5432/dbname" />
                  <Input label="Product table (optional)" value={db.table_name} onChange={setField('table_name')} placeholder="products" />
                </div>
              )}
              <div className="mt-6 flex justify-between gap-2">
                <Button variant="secondary" onClick={() => setStep(0)}>Back</Button>
                {hasDatabase ? <Button onClick={() => setStep(2)}>Continue <ArrowRight size={16} /></Button> : <Button onClick={connectDatabase} disabled={working || !db.connection_url}>{working && <Spinner />}{working ? 'Connecting…' : 'Test & connect'} <ArrowRight size={16} /></Button>}
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <h2 className="font-display text-xl font-semibold">Your API key</h2>
              <p className="mt-1 text-sm text-muted">Use an active key to authenticate the chat widget on your storefront.</p>
              {issuedKey ? (
                <div className="mt-6 rounded-lg border border-accent/30 bg-accent-soft/40 p-4">
                  <div className="text-xs font-medium uppercase tracking-wide text-muted">Copy now — shown once</div>
                  <div className="mt-2 flex items-center gap-2 rounded-lg border border-line bg-white p-3">
                    <code className="min-w-0 flex-1 truncate text-sm">{issuedKey}</code>
                    <Button size="sm" variant="secondary" onClick={() => { navigator.clipboard.writeText(issuedKey); setCopied(true); setTimeout(() => setCopied(false), 1500) }}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? 'Copied' : 'Copy'}</Button>
                  </div>
                </div>
              ) : activeKey ? (
                <div className="mt-6 rounded-lg border border-line bg-paper p-4">
                  <div className="flex items-center gap-2 text-sm font-medium"><Check size={16} /> API key already active</div>
                  <p className="mt-1 text-xs text-muted">For security, the full existing key cannot be displayed again.</p>
                </div>
              ) : (
                <div className="mt-6 rounded-lg border border-line bg-paper p-4"><p className="text-sm text-muted">Create a production widget key to finish setup.</p><Button className="mt-4" onClick={createKey} disabled={working}>{working && <Spinner />}{working ? 'Creating…' : 'Create API key'}</Button></div>
              )}
              <div className="mt-6 flex justify-between gap-2"><Button variant="secondary" onClick={() => setStep(1)}>Back</Button><Button onClick={finish}>Go to dashboard <ArrowRight size={16} /></Button></div>
            </>
          )}
        </Card>

        <div className="mt-5 flex items-center justify-center gap-2 text-xs text-muted"><Loader2 size={13} /> You can change these settings later from the dashboard.</div>
      </div>
    </div>
  )
}
