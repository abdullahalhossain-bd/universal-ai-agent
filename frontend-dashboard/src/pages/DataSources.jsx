import { useEffect, useMemo, useState } from 'react'
import { Database, Plus, Search, RefreshCw, Trash2, CheckCircle2, AlertTriangle } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Badge, Button, Card, EmptyState, Input, PageHeader, Spinner } from '../components/ui'

const EMPTY_FORM = {
  name: 'Main database',
  connector_type: 'postgresql',
  connection_url: '',
  table_name: '',
}

const PRODUCT_FIELDS = [
  'id',
  'name',
  'price',
  'stock',
  'image_url',
  'category',
  'description',
  'brand',
  'sku',
  'updated_at',
  'created_at',
]

const FIELD_LABELS = {
  id: 'Product ID',
  name: 'Product Name',
  price: 'Price',
  stock: 'Stock',
  image_url: 'Image URL',
  category: 'Category',
  description: 'Description',
  brand: 'Brand',
  sku: 'SKU',
  updated_at: 'Updated At',
  created_at: 'Created At',
}

const extractMappingEntries = (result) => {
  const entries = []
  const add = (field, data) => {
    if (!field) return
    if (typeof data === 'string') {
      entries.push({ field, suggested_column: data, confidence: 1, status: 'auto_accepted', reason: '' })
      return
    }
    if (data && typeof data === 'object') {
      entries.push({
        field,
        suggested_column: data.suggested_column || data.column || null,
        confidence: Number(data.confidence || 0),
        status: data.status || '',
        reason: data.reason || '',
        candidates: data.candidates || [],
      })
    }
  }

  Object.entries(result?.auto_accepted || {}).forEach(([field, column]) => add(field, column))
  ;(result?.needs_confirmation || []).forEach((item) => add(item?.field, item))
  ;(result?.manual_required || []).forEach((item) => add(item?.field, item))
  Object.entries(result?.ask || {}).forEach(([field, data]) => add(field, data))
  Object.entries(result?.manual || {}).forEach(([field, data]) => add(field, data))

  const byField = new Map()
  entries.forEach((entry) => {
    if (!byField.has(entry.field) || entry.confidence > byField.get(entry.field).confidence) {
      byField.set(entry.field, entry)
    }
  })
  return byField
}

export default function DataSources() {
  const [datasources, setDatasources] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [schema, setSchema] = useState(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [discovering, setDiscovering] = useState(false)

  const [reviewingId, setReviewingId] = useState(null)
  const [reviewSchema, setReviewSchema] = useState(null)
  const [reviewTable, setReviewTable] = useState('')
  const [mappingResult, setMappingResult] = useState(null)
  const [mappingChoices, setMappingChoices] = useState({})
  const [mappingLoading, setMappingLoading] = useState(false)
  const [mappingError, setMappingError] = useState('')
  const [savingMapping, setSavingMapping] = useState(false)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      setDatasources(await api.get('/v1/datasources'))
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load data sources.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const items = useMemo(() => datasources?.items || [], [datasources])

  const resetForm = () => {
    setForm(EMPTY_FORM)
    setEditingId(null)
    setSchema(null)
    setShowForm(false)
  }

  const handleChange = (field) => (e) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  const openCreate = () => {
    setError('')
    setForm(EMPTY_FORM)
    setEditingId(null)
    setSchema(null)
    setShowForm(true)
  }

  const openEdit = (ds) => {
    setError('')
    setEditingId(ds.id)
    setForm({
      name: ds.name || '',
      connector_type: ds.connector_type || 'postgresql',
      connection_url: '',
      table_name: ds.table_name || '',
    })
    setSchema(null)
    setShowForm(true)
  }

  const testConnection = async () => {
    if (!form.connection_url) return
    setTesting(true)
    setError('')
    try {
      const result = await api.post('/v1/datasources/test', {
        connector_type: form.connector_type,
        connection_url: form.connection_url,
      })
      if (!result.connected) throw new ApiError(400, result.error || 'Connection test failed.')
      setError('Connection validated successfully.')
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
      let result
      if (editingId && !form.connection_url) {
        result = await api.post(`/v1/datasources/${editingId}/discover`, {})
      } else {
        if (!form.connection_url) throw new ApiError(400, 'Enter a connection URL first.')
        result = await api.post('/v1/datasources/discover', {
          connector_type: form.connector_type,
          connection_url: form.connection_url,
        })
      }
      setSchema(result)
    } catch (err) {
      setSchema(null)
      setError(err instanceof ApiError ? err.detail : 'Schema discovery failed.')
    } finally {
      setDiscovering(false)
    }
  }

  const saveDatasource = async () => {
    setSaving(true)
    setError('')
    try {
      if (editingId) {
        const payload = { name: form.name, table_name: form.table_name || null }
        if (form.connection_url.trim()) payload.connection_url = form.connection_url.trim()
        await api.patch(`/v1/datasources/${editingId}`, payload)
      } else {
        if (!form.connection_url.trim()) throw new ApiError(400, 'Connection URL is required.')
        await api.post('/v1/datasources', {
          name: form.name,
          connector_type: form.connector_type,
          connection_url: form.connection_url.trim(),
          table_name: form.table_name || undefined,
          active: true,
          full_sync: true,
        })
      }
      resetForm()
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Unable to save datasource.')
    } finally {
      setSaving(false)
    }
  }

  const deleteDatasource = async (id) => {
    if (!window.confirm('Delete this datasource?')) return
    setError('')
    try {
      await api.del(`/v1/datasources/${id}`)
      if (editingId === id) resetForm()
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to delete datasource.')
    }
  }

  const closeMappingReview = () => {
    setReviewingId(null)
    setReviewSchema(null)
    setReviewTable('')
    setMappingResult(null)
    setMappingChoices({})
    setMappingError('')
  }

  const runMappingForTable = async (tableName, ds, schemaData) => {
    setReviewTable(tableName)
    setMappingError('')
    setMappingLoading(true)
    try {
      const table = (schemaData?.tables || []).find((item) => item.table === tableName)
      const columns = table?.columns || []
      const result = await api.post('/v1/mapping/suggest', {
        store_id: ds.store_id,
        table: tableName,
        columns,
      })
      setMappingResult(result)

      // Seed the editable mapping with the best server suggestion for every
      // field. The merchant can change any suggestion before saving.
      const suggestions = {}
      const entries = extractMappingEntries(result)
      entries.forEach((entry, field) => {
        if (entry.suggested_column) suggestions[field] = entry.suggested_column
      })
      setMappingChoices(suggestions)
    } catch (err) {
      setMappingError(err instanceof ApiError ? err.detail : 'Could not analyze that table.')
    } finally {
      setMappingLoading(false)
    }
  }

  const openMappingReview = async (ds) => {
    setReviewingId(ds.id)
    setMappingError('')
    setMappingResult(null)
    setMappingChoices({})
    setReviewTable(ds.table_name || '')
    setReviewSchema(null)
    setMappingLoading(true)
    try {
      const result = await api.post(`/v1/datasources/${ds.id}/discover`, {})
      setReviewSchema(result)
      if (ds.table_name) await runMappingForTable(ds.table_name, ds, result)
    } catch (err) {
      setMappingError(err instanceof ApiError ? err.detail : 'Could not read the database schema.')
    } finally {
      setMappingLoading(false)
    }
  }

  const saveMapping = async (ds) => {
    if (!mappingResult) return
    const finalMapping = { ...(mappingResult.auto_accepted || {}), ...mappingChoices }
    if (!finalMapping.id || !finalMapping.name) {
      setMappingError('Product ID এবং Product Name — এই দুইটা field এর column অবশ্যই বেছে দিতে হবে।')
      return
    }

    setSavingMapping(true)
    setMappingError('')
    try {
      await api.post('/v1/mapping/apply', {
        store_id: ds.store_id,
        datasource_id: ds.id,
        table: reviewTable,
        mapping: finalMapping,
      })
      await api.post(`/v1/datasources/${ds.id}/sync`, {})
      closeMappingReview()
      await load()
    } catch (err) {
      setMappingError(err instanceof ApiError ? err.detail : 'Mapping save করা যায়নি।')
    } finally {
      setSavingMapping(false)
    }
  }

  const reviewTables = reviewSchema?.tables || []
  const selectedColumns = reviewTables.find((item) => item.table === reviewTable)?.columns || []
  const mappingEntries = useMemo(() => extractMappingEntries(mappingResult), [mappingResult])
  const mappingFields = useMemo(() => {
    const dynamic = Array.from(mappingEntries.keys())
    return Array.from(new Set([...PRODUCT_FIELDS, ...dynamic]))
  }, [mappingEntries])

  return (
    <div>
      <PageHeader
        title="Data sources"
        description="Connect a database, discover its schema, map product fields, and sync product data."
        action={!showForm && <Button onClick={openCreate}><Plus size={16} /> Add datasource</Button>}
      />

      {error && (
        <div className="mb-5">
          <Alert tone={error.includes('successfully') || error.includes('validated') ? 'success' : 'warn'}>{error}</Alert>
        </div>
      )}

      {showForm && (
        <Card className="mb-6 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="font-display text-lg font-semibold text-text">
                {editingId ? 'Edit database connection' : 'Database connection setup'}
              </h3>
              {editingId && <p className="mt-1 text-xs text-muted">Stored credentials are protected. Leave the URL empty to keep the existing connection.</p>}
            </div>
            <Badge tone="accent">Secure connection</Badge>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Input label="Datasource name" value={form.name} onChange={handleChange('name')} />
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-text">Connector type</span>
              <select
                value={form.connector_type}
                disabled={Boolean(editingId)}
                onChange={handleChange('connector_type')}
                className="w-full rounded-lg border border-line bg-white px-3.5 py-2.5 text-sm text-text disabled:cursor-not-allowed disabled:bg-paper"
              >
                <option value="postgresql">PostgreSQL</option>
                <option value="mysql">MySQL</option>
              </select>
            </label>
          </div>

          <Input
            label={editingId ? 'New connection URL (optional)' : 'Connection URL'}
            value={form.connection_url}
            onChange={handleChange('connection_url')}
            placeholder={form.connector_type === 'mysql' ? 'mysql+pymysql://user:pass@host:3306/dbname' : 'postgresql://user:pass@host:5432/dbname'}
          />

          <Input label="Target table (optional)" value={form.table_name} onChange={handleChange('table_name')} placeholder="products" />

          <div className="flex flex-wrap gap-3">
            <Button onClick={testConnection} disabled={testing || !form.connection_url}>
              {testing && <Spinner />}{testing ? 'Testing…' : 'Test connection'}
            </Button>
            <Button variant="secondary" onClick={discoverSchema} disabled={discovering || (!form.connection_url && !editingId)}>
              {discovering && <Spinner />}{discovering ? 'Discovering…' : 'Discover schema'}
            </Button>
            <Button variant="secondary" onClick={resetForm}>Cancel</Button>
            <Button variant="primary" onClick={saveDatasource} disabled={saving || (!editingId && !form.connection_url)}>
              {saving && <Spinner />}{saving ? 'Saving…' : editingId ? 'Save changes' : 'Save datasource'}
            </Button>
          </div>

          {schema && (
            <div className="rounded-lg border border-line bg-paper p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-text"><Search size={15} /> Schema discovery result</div>
              <pre className="max-h-72 overflow-auto whitespace-pre-wrap text-xs text-muted">{JSON.stringify(schema, null, 2)}</pre>
            </div>
          )}
        </Card>
      )}

      {loading ? (
        <div className="flex justify-center py-16 text-muted"><Spinner className="h-6 w-6" /></div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No data sources connected"
          description="Connect a PostgreSQL or MySQL database to discover and sync product data."
          action={<Button onClick={openCreate}><Plus size={16} /> Connect your first database</Button>}
        />
      ) : (
        <div className="space-y-4">
          {items.map((ds) => (
            <Card key={ds.id} className="p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-lg bg-accent-soft text-accent"><Database size={18} /></div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-display text-base font-semibold text-text">{ds.name}</span>
                      <Badge tone={ds.active ? 'success' : 'muted'}>{ds.active ? 'Active' : 'Inactive'}</Badge>
                    </div>
                    <div className="mt-1 text-sm text-muted">{ds.connector_type} · {ds.table_name || 'No table selected'}</div>
                    <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted">
                      <span className="inline-flex items-center gap-1">
                        {ds.last_sync_status === 'success' ? <CheckCircle2 size={12} className="text-success" /> : <AlertTriangle size={12} className="text-warn" />}
                        {ds.last_sync_status || 'No sync yet'}
                      </span>
                      {ds.last_sync_at && <span>{new Date(ds.last_sync_at).toLocaleString()}</span>}
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="secondary" size="sm" onClick={() => openEdit(ds)}><RefreshCw size={14} /> Edit</Button>
                  <Button variant="primary" size="sm" onClick={() => reviewingId === ds.id ? closeMappingReview() : openMappingReview(ds)}>
                    <Search size={14} /> {reviewingId === ds.id ? 'Close' : 'Fix mapping'}
                  </Button>
                  <Button variant="danger" size="sm" onClick={() => deleteDatasource(ds.id)}><Trash2 size={14} /> Delete</Button>
                </div>
              </div>

              {reviewingId === ds.id && (
                <div className="mt-5 rounded-lg border border-line bg-paper p-4">
                  <h4 className="font-display text-sm font-semibold text-text">Column ↔ Product field mapping</h4>
                  <p className="mt-1 mb-4 text-xs text-muted">ডাটাবেজের column কোন product field হিসেবে ব্যবহার হবে, তা এখানে ঠিক করুন। Product ID ও Product Name অবশ্যই থাকবে; বাকি field যতটা সম্ভব automatically suggest করা হবে, এবং আপনি চাইলে সব পরিবর্তন করতে পারবেন।</p>

                  {mappingError && <div className="mb-3"><Alert tone="warn">{mappingError}</Alert></div>}

                  {mappingLoading && <div className="flex items-center gap-2 py-4 text-sm text-muted"><Spinner /> Analyzing schema…</div>}

                  {!mappingLoading && reviewTables.length > 0 && (
                    <div className="space-y-4">
                      <label className="block max-w-xl">
                        <span className="mb-1.5 block text-sm font-medium text-text">Product table</span>
                        <select
                          value={reviewTable}
                          onChange={(e) => runMappingForTable(e.target.value, ds, reviewSchema)}
                          className="w-full rounded-lg border border-line bg-white px-3.5 py-2.5 text-sm text-text"
                        >
                          <option value="">Select a table</option>
                          {reviewTables.map((table) => <option key={table.table} value={table.table}>{table.table}</option>)}
                        </select>
                      </label>

                      {reviewTable && selectedColumns.length > 0 && mappingResult && (
                        <div className="space-y-3">
                          {mappingFields.map((field) => {
                            const auto = mappingResult.auto_accepted || {}
                            const entry = mappingEntries.get(field)
                            const current = mappingChoices[field] ?? auto[field] ?? entry?.suggested_column ?? ''
                            const required = field === 'id' || field === 'name'
                            const confidence = entry?.confidence
                            const confidenceText = confidence ? ` · ${Math.round(confidence * 100)}%` : ''
                            return (
                              <div key={field} className="grid gap-2 md:grid-cols-[180px_1fr] md:items-center">
                                <span className="text-sm font-medium text-text">
                                  {FIELD_LABELS[field] || field}
                                  {required && <span className="ml-1 text-warn">*</span>}
                                </span>
                                <div>
                                  <select
                                    value={current}
                                    onChange={(e) => setMappingChoices((prev) => ({ ...prev, [field]: e.target.value }))}
                                    className={`w-full rounded-lg border bg-white px-3 py-2 text-sm text-text ${required && !current ? 'border-warn' : 'border-line'}`}
                                  >
                                    <option value="">Select column{required ? ' (required)' : ''}</option>
                                    {selectedColumns.map((column) => {
                                      const name = typeof column === 'string' ? column : column.name
                                      return <option key={name} value={name}>{name}</option>
                                    })}
                                  </select>
                                  {entry?.reason && <div className="mt-1 text-xs text-muted">{entry.reason}{confidenceText}</div>}
                                </div>
                              </div>
                            )
                          })}

                          <div className="pt-2">
                            <Button onClick={() => saveMapping(ds)} disabled={savingMapping || !reviewTable}>
                              {savingMapping && <Spinner />}{savingMapping ? 'Saving & syncing…' : 'Save mapping & sync products'}
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
