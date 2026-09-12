import { useEffect, useRef, useState } from 'react'
import { Globe, Plus, RefreshCw, FileText } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Button, Card, EmptyState, Input, PageHeader, Spinner } from '../components/ui'

function normalizeWebsiteUrl(value) {
  const raw = String(value || '').trim()
  if (!raw) throw new Error('Please enter a website URL.')
  const candidate = /^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`
  let parsed
  try { parsed = new URL(candidate) } catch { throw new Error('Please enter a valid website URL, such as https://example.com.') }
  if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname) {
    throw new Error('Website URL must use http or https.')
  }
  if (parsed.username || parsed.password) throw new Error('Website URL must not contain a username or password.')
  return parsed.toString()
}

function errorMessage(err, fallback = 'Something went wrong. Please try again.') {
  if (err instanceof ApiError) {
    if (typeof err.detail === 'object' && err.detail?.message) return err.detail.message
    return typeof err.detail === 'string' ? err.detail : err.message
  }
  return err?.message || fallback
}

export default function Websites() {
  const [websites, setWebsites] = useState(null)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [url, setUrl] = useState('')
  const [ingesting, setIngesting] = useState(false)
  const [crawl, setCrawl] = useState(null)
  const pollRef = useRef(null)

  const load = () => {
    api.get('/v1/knowledge/websites')
      .then(setWebsites)
      .catch((err) => setError(errorMessage(err, 'Failed to load websites.')))
  }

  useEffect(() => {
    load()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const pollStatus = (datasourceId) => {
    if (pollRef.current) clearInterval(pollRef.current)
    const poll = async () => {
      try {
        const status = await api.get(`/v1/websites/${encodeURIComponent(datasourceId)}/status`, { timeoutMs: 10000 })
        const progress = status.crawl_progress || {}
        const lastRun = status.last_run
        setCrawl({ progress, lastRun })
        if (lastRun?.status === 'success' || lastRun?.status === 'partial' || lastRun?.status === 'error') {
          clearInterval(pollRef.current)
          pollRef.current = null
          setIngesting(false)
          load()
        }
      } catch (err) {
        setError(errorMessage(err, 'Unable to read crawl progress.'))
      }
    }
    poll()
    pollRef.current = setInterval(poll, 2000)
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    if (ingesting) return
    setError('')
    setCrawl(null)
    try {
      const normalized = normalizeWebsiteUrl(url)
      setIngesting(true)
      const result = await api.post('/v1/knowledge/ingest', { website_url: normalized }, { timeoutMs: 15000 })
      setUrl('')
      setShowForm(false)
      setCrawl({ progress: { status: 'queued' }, lastRun: null })
      if (result?.datasource_id) pollStatus(result.datasource_id)
      else setIngesting(false)
      load()
    } catch (err) {
      setIngesting(false)
      setError(errorMessage(err, 'Failed to queue that website.'))
    }
  }

  const progress = crawl?.progress || {}
  const lastRun = crawl?.lastRun
  const pagesCrawled = Number(progress.pages_crawled || 0)
  const maxPages = Number(progress.max_pages || 0)
  const percent = maxPages ? Math.min(100, Math.round((pagesCrawled / maxPages) * 100)) : 0

  return (
    <div>
      <PageHeader
        title="Websites"
        description="Connect your storefront so the assistant can answer questions about your products, shipping, and policies."
        action={!showForm && <Button onClick={() => { setError(''); setShowForm(true) }}><Plus size={16} /> Add website</Button>}
      />

      {error && <div className="mb-5"><Alert>{error}</Alert></div>}

      {crawl && (
        <div className="mb-5">
          <Alert tone={lastRun?.status === 'error' ? 'danger' : lastRun?.status === 'partial' ? 'warning' : lastRun?.status === 'success' ? 'success' : undefined}>
            {lastRun?.status === 'success'
              ? `Crawl completed — ${lastRun.products_seen ?? 0} product(s) detected.`
              : lastRun?.status === 'partial'
                ? `Crawl completed with some data-quality issues — ${lastRun.products_seen ?? 0} product(s) detected.`
                : lastRun?.status === 'error'
                  ? `Crawl failed: ${lastRun.error || 'the worker reported an error.'}`
                  : progress.status === 'queued'
                    ? 'Website crawl queued. Starting shortly…'
                    : `Crawling website… ${pagesCrawled}${maxPages ? ` / ${maxPages} pages` : ' pages'}${maxPages ? ` (${percent}%)` : ''}`}
          </Alert>
        </div>
      )}

      {showForm && (
        <Card className="mb-6">
          <h3 className="font-display text-base font-semibold text-text">Add a website</h3>
          <p className="mt-1 text-sm text-muted">We&apos;ll crawl the pages allowed by your plan and index their content asynchronously.</p>
          <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Input id="website_url" label="Website URL" type="text" required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://yourstore.com" />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={ingesting || !url.trim()}>{ingesting && <Spinner />}{ingesting ? 'Starting…' : 'Crawl website'}</Button>
              <Button type="button" variant="secondary" disabled={ingesting} onClick={() => setShowForm(false)}>Cancel</Button>
            </div>
          </form>
        </Card>
      )}

      {websites === null ? (
        <div className="flex justify-center py-16 text-muted"><Spinner className="h-6 w-6" /></div>
      ) : websites.count === 0 ? (
        <EmptyState icon={Globe} title="No websites connected yet" description="Add your storefront URL and we&apos;ll crawl it so the assistant can answer product and policy questions accurately." action={!showForm && <Button onClick={() => setShowForm(true)}><Plus size={16} /> Add your first website</Button>} />
      ) : (
        <div className="space-y-3">
          {websites.websites.map((site) => (
            <Card key={site.domain} className="flex items-center justify-between p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-soft text-accent"><Globe size={18} strokeWidth={1.9} /></div>
                <div>
                  <div className="text-sm font-medium text-text">{site.domain}</div>
                  <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted"><FileText size={12} />{site.page_count} page{site.page_count === 1 ? '' : 's'} indexed{site.last_crawled_at && ` · last crawled ${new Date(site.last_crawled_at).toLocaleDateString()}`}</div>
                </div>
              </div>
              <Button variant="secondary" size="sm" disabled={ingesting} onClick={() => { setError(''); setUrl(`https://${site.domain}`); setShowForm(true) }}><RefreshCw size={14} /> Re-crawl</Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
