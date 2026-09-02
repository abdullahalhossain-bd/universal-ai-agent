import { useEffect, useState } from 'react'
import { Globe, Plus, RefreshCw, FileText } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Button, Card, EmptyState, Input, PageHeader, Spinner } from '../components/ui'

export default function Websites() {
  const [websites, setWebsites] = useState(null)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [url, setUrl] = useState('')
  const [ingesting, setIngesting] = useState(false)
  const [lastResult, setLastResult] = useState(null)

  const load = () => {
    api
      .get('/v1/knowledge/websites')
      .then(setWebsites)
      .catch((err) => setError(err instanceof ApiError ? err.detail : 'Failed to load websites.'))
  }

  useEffect(load, [])

  const onSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLastResult(null)
    setIngesting(true)
    try {
      const result = await api.post('/v1/knowledge/ingest', { website_url: url })
      setLastResult(result)
      setUrl('')
      setShowForm(false)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to crawl that website.')
    } finally {
      setIngesting(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="Websites"
        description="Connect your storefront so the assistant can answer questions about your products, shipping, and policies."
        action={
          !showForm && (
            <Button onClick={() => setShowForm(true)}>
              <Plus size={16} /> Add website
            </Button>
          )
        }
      />

      {error && (
        <div className="mb-5">
          <Alert>{error}</Alert>
        </div>
      )}

      {lastResult && (
        <div className="mb-5">
          <Alert tone="success">
            Crawled successfully — {lastResult.created_pages ?? 0} page(s) added,{' '}
            {lastResult.created_chunks ?? 0} chunk(s) indexed.
          </Alert>
        </div>
      )}

      {showForm && (
        <Card className="mb-6">
          <h3 className="font-display text-base font-semibold text-text">Add a website</h3>
          <p className="mt-1 text-sm text-muted">
            We&apos;ll crawl up to 50 pages and index their content for the chat assistant.
          </p>
          <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Input
                id="website_url"
                label="Website URL"
                type="url"
                required
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://yourstore.com"
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={ingesting}>
                {ingesting && <Spinner />}
                {ingesting ? 'Crawling…' : 'Crawl website'}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      {websites === null ? (
        <div className="flex justify-center py-16 text-muted">
          <Spinner className="h-6 w-6" />
        </div>
      ) : websites.count === 0 ? (
        <EmptyState
          icon={Globe}
          title="No websites connected yet"
          description="Add your storefront URL and we'll crawl it so the assistant can answer product and policy questions accurately."
          action={
            !showForm && (
              <Button onClick={() => setShowForm(true)}>
                <Plus size={16} /> Add your first website
              </Button>
            )
          }
        />
      ) : (
        <div className="space-y-3">
          {websites.websites.map((site) => (
            <Card key={site.domain} className="flex items-center justify-between p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-soft text-accent">
                  <Globe size={18} strokeWidth={1.9} />
                </div>
                <div>
                  <div className="text-sm font-medium text-text">{site.domain}</div>
                  <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
                    <FileText size={12} />
                    {site.page_count} page{site.page_count === 1 ? '' : 's'} indexed
                    {site.last_crawled_at &&
                      ` · last crawled ${new Date(site.last_crawled_at).toLocaleDateString()}`}
                  </div>
                </div>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setUrl(`https://${site.domain}`)
                  setShowForm(true)
                }}
              >
                <RefreshCw size={14} /> Re-crawl
              </Button>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
