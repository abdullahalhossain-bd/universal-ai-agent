import { useEffect, useState } from 'react'
import { Check, Copy, KeyRound, Plus, ShieldOff } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Badge, Button, Card, EmptyState, Input, PageHeader, Spinner } from '../components/ui'

export default function ApiKeys() {
  const [keys, setKeys] = useState(null)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [issuedKey, setIssuedKey] = useState(null)
  const [revokingId, setRevokingId] = useState(null)
  const [copied, setCopied] = useState(false)

  const load = () => {
    api
      .get('/v1/stores/me/api-keys')
      .then((data) => setKeys(data.api_keys))
      .catch((err) => setError(err instanceof ApiError ? err.detail : 'Failed to load API keys.'))
  }

  useEffect(load, [])

  const onCreate = async (e) => {
    e.preventDefault()
    setError('')
    setCreating(true)
    try {
      const created = await api.post('/v1/stores/me/api-keys', { name: name || 'New Key' })
      setIssuedKey(created)
      setName('')
      setShowForm(false)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create API key.')
    } finally {
      setCreating(false)
    }
  }

  const onRevoke = async (id) => {
    setRevokingId(id)
    setError('')
    try {
      await api.post(`/v1/stores/me/api-keys/${id}/revoke`)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to revoke API key.')
    } finally {
      setRevokingId(null)
    }
  }

  return (
    <div>
      <PageHeader
        title="API Keys"
        description="Widget authentication keys for your storefront chat. Revoke a key immediately if it's ever exposed."
        action={
          !showForm && (
            <Button onClick={() => setShowForm(true)}>
              <Plus size={16} /> New key
            </Button>
          )
        }
      />

      {error && (
        <div className="mb-5">
          <Alert>{error}</Alert>
        </div>
      )}

      {issuedKey && (
        <Card className="mb-6 border-accent/30 bg-accent-soft/40">
          <h3 className="font-display text-sm font-semibold text-text">
            New key created — copy it now
          </h3>
          <p className="mt-1 text-xs text-muted">
            For security, the full key is only shown this once.
          </p>
          <div className="mt-3 flex items-center justify-between gap-2 rounded-lg border border-line bg-white px-3.5 py-3">
            <code className="truncate text-sm text-text">{issuedKey.api_key}</code>
            <button
              type="button"
              onClick={() => {
                navigator.clipboard.writeText(issuedKey.api_key)
                setCopied(true)
                setTimeout(() => setCopied(false), 1500)
              }}
              className="flex shrink-0 items-center gap-1.5 rounded-md border border-line bg-white px-2.5 py-1.5 text-xs font-medium text-text hover:bg-paper"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <Button variant="ghost" size="sm" className="mt-3" onClick={() => setIssuedKey(null)}>
            Done
          </Button>
        </Card>
      )}

      {showForm && (
        <Card className="mb-6">
          <form onSubmit={onCreate} className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Input
                id="key_name"
                label="Key name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Production widget"
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={creating}>
                {creating && <Spinner />}
                Create key
              </Button>
              <Button type="button" variant="secondary" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}

      {keys === null ? (
        <div className="flex justify-center py-16 text-muted">
          <Spinner className="h-6 w-6" />
        </div>
      ) : keys.length === 0 ? (
        <EmptyState
          icon={KeyRound}
          title="No API keys yet"
          description="Create a key to authenticate the storefront chat widget."
          action={
            <Button onClick={() => setShowForm(true)}>
              <Plus size={16} /> Create your first key
            </Button>
          }
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-line bg-card">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-paper text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-5 py-3 font-medium">Name</th>
                <th className="px-5 py-3 font-medium">Key</th>
                <th className="px-5 py-3 font-medium">Created</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key.id} className="border-b border-line last:border-0">
                  <td className="px-5 py-3.5 font-medium text-text">{key.name}</td>
                  <td className="px-5 py-3.5 font-mono text-xs text-muted">
                    {key.key_prefix}••••••••
                  </td>
                  <td className="px-5 py-3.5 text-muted">
                    {new Date(key.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-5 py-3.5">
                    {key.active ? (
                      <Badge tone="success">Active</Badge>
                    ) : (
                      <Badge tone="muted">Revoked</Badge>
                    )}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    {key.active && (
                      <Button
                        variant="danger"
                        size="sm"
                        disabled={revokingId === key.id}
                        onClick={() => onRevoke(key.id)}
                      >
                        {revokingId === key.id ? <Spinner /> : <ShieldOff size={14} />}
                        Revoke
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
