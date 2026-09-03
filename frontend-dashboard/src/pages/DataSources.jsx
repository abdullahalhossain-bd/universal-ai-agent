import { useEffect, useMemo, useState } from 'react'
import { Database, RefreshCw, Plus, Search, CheckCircle2, AlertTriangle, ArrowRight, Trash2 } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Badge, Button, Card, EmptyState, Input, PageHeader, Spinner } from '../components/ui'

export default function DataSources() {
  const [datasources, setDatasources] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [schema, setSchema] = useState(null)
  const [form, setForm] = useState({
    name: 'Main database',
    connector_type: 'postgresql',
    connection_url: '',
    table_name: '',
  })
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [discovering, setDiscovering] = useState(false)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.get('/v1/datasources')
      setDatasources(data)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load data sources.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleChange = (field) => (e) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  const testConnection = async () => {
    setTesting(true)
    setError('')
    try {
      const result = await api.post('/v1/datasources/test', {
        connector_type: form.connector_type,
        connection_url: form.connection_url,
      })
      setSchema(null)
      setError(result.connected ? 'Connection validated successfully.' : 'Connection test failed.')
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Connection test failed.')
    } finally {
      setTesting(false)
    }
  }

  const discoverSchema = async () => {
    setDiscovering(true)
    setError('')
    try {
      const result = await api.post('/v1/datasources/discover', {
        connector_type: form.connector_type,
        connection_url: form.connection_url,
      })
      setSchema(result)
      setError('')
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Schema discovery failed.')
      setSchema(null)
    } finally {
      setDiscovering(false)
    }
  }

  const createDatasource = async () => {
    setSaving(true)
    setError('')
    try {
      await api.post('/v1/datasources', {
        name: form.name,
        connector_type: form.connector_type,
        connection_url: form.connection_url,
        table_name: form.table_name || undefined,
        active: true,
        full_sync: true,
      })
      setShowForm(false)
      setForm({
        name: 'Main database',
        connector_type: 'postgresql',
        connection_url: '',
        table_name: '',
      })
      await load()
      setSchema(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Unable to save connection.')
    } finally {
      setSaving(false)
    }
  }

  const deleteDatasource = async (id) => {
    try {
      await api.del(`/v1/datasources/${id}`)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to delete datasource.')
    }
  }

  const summaries = useMemo(() => {
    if (!datasources) return []
    return datasources.items || []
  }, [datasources])

  const hasSchema = Boolean(schema && (schema.tables || schema.columns || schema.schemas))

  return (
    <div>
      <PageHeader
        title="Data sources"
        description="Connect a database, validate the URL, and review discovered schema before syncing product data."
        action={
          !showForm && (
            <Button onClick={() => setShowForm(true)}>
              <Plus size={16} /> Add datasource
            </Button>
          )
        }
      />

      {error && (
        <div className="mb-5">
          <Alert tone={error.includes('successfully') || error.includes('validated') ? 'success' : 'warn'}>{error}</Alert>
        </div>
      )}

      {showForm && (
        <Card className="mb-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-display text-lg font-semibold text-text">Database connection setup</h3>
            <Badge tone="accent">Live validation</Badge>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Input label="Datasource name" value={form.name} onChange={handleChange('name')} />
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-text">Connector type</span>
              <select
                value={form.connector_type}
                onChange={handleChange('connector_type')}
                className="w-full rounded-lg border border-line bg-white px-3.5 py-2.5 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent/30"
              >
                <option value="postgresql">PostgreSQL</option>
                <option value="mysql">MySQL</option>
              </select>
            </label>
          </div>

          <Input
            label="Connection URL"
            value={form.connection_url}
            onChange={handleChange('connection_url')}
            placeholder="postgresql://user:pass@host:5432/dbname"
          />

          <Input
            label="Target table (optional)"
            value={form.table_name}
            onChange={handleChange('table_name')}
            placeholder="products"
          />

          <div className="flex flex-wrap gap-3">
            <Button onClick={testConnection} disabled={testing || !form.connection_url}>
              {testing && <Spinner />}
              {testing ? 'Testing…' : 'Test connection'}
            </Button>
            <Button variant="secondary" onClick={discoverSchema} disabled={discovering || !form.connection_url}>
              {discovering && <Spinner />}
              {discovering ? 'Discovering…' : 'Discover schema'}
            </Button>
            <Button variant="secondary" onClick={() => setShowForm(false)}>Cancel</Button>
            <Button variant="primary" onClick={createDatasource} disabled={saving || !form.connection_url}>
              {saving && <Spinner />}
              {saving ? 'Saving…' : 'Save datasource'}
            </Button>
          </div>

          {hasSchema && (
            <div className="rounded-lg border border-line bg-paper p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-text">
                <Search size={15} /> Schema discovery result
              </div>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap text-xs text-muted">
                {JSON.stringify(schema, null, 2)}
              </pre>
            </div>
          )}
        </Card>
      )}

      {loading ? (
        <div className="flex justify-center py-16 text-muted">
          <Spinner className="h-6 w-6" />
        </div>
      ) : summaries.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No data sources connected"
          description="Add a database connection to validate it, discover schema, and sync product data into the knowledge/search pipeline."
          action={
            <Button onClick={() => setShowForm(true)}>
              <Plus size={16} /> Connect your first database
            </Button>
          }
        />
      ) : (
        <div className="space-y-4">
          {summaries.map((ds) => (
            <Card key={ds.id} className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-lg bg-accent-soft text-accent">
                  <Database size={18} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-display text-base font-semibold text-text">{ds.name}</span>
                    <Badge tone={ds.active ? 'success' : 'muted'}>{ds.active ? 'Active' : 'Inactive'}</Badge>
                  </div>
                  <div className="mt-1 text-sm text-muted">
                    {ds.connector_type} · {ds.table_name || 'No table selected'}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted">
                    <span className="inline-flex items-center gap-1">
                      {ds.last_sync_status === 'success' ? <CheckCircle2 size={12} className="text-success" /> : <AlertTriangle size={12} className="text-warn" />}
                      {ds.last_sync_status || 'No sync yet'}
                    </span>
                    {ds.last_sync_at && <span>{new Date(ds.last_sync_at).toLocaleString()}</span>}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Button variant="secondary" size="sm" onClick={() => {
                  setForm({
                    name: ds.name,
                    connector_type: ds.connector_type,
                    connection_url: ds.connection_url || '',
                    table_name: ds.table_name || '',
                  })
                  setShowForm(true)
                }}>
                  <RefreshCw size={14} /> Edit
                </Button>
                <Button variant="danger" size="sm" onClick={() => deleteDatasource(ds.id)}>
                  <Trash2 size={14} /> Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
