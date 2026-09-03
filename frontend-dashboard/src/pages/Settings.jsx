import { useEffect, useState } from 'react'
import { Settings as SettingsIcon, ShieldCheck, Lock, Mail } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Button, Card, Input, PageHeader, Spinner } from '../components/ui'

export default function Settings() {
  const [store, setStore] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    api.get('/v1/auth/me')
      .then((data) => setStore(data.store))
      .catch((err) => setError(err instanceof ApiError ? err.detail : 'Unable to load account settings.'))
      .finally(() => setLoading(false))
  }, [])

  const saveBasicSettings = async () => {
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const result = await api.post('/v1/stores', {
        name: store.name,
        website_url: store.website_url,
        plan: store.plan,
      })
      setSuccess(`Store updated successfully. Current plan: ${result.plan}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to update settings.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <PageHeader title="Account settings" description="Manage your account, plan, website information, and security preferences." />

      {error && <div className="mb-5"><Alert>{error}</Alert></div>}
      {success && <div className="mb-5"><Alert tone="success">{success}</Alert></div>}

      {loading ? (
        <div className="flex justify-center py-12 text-muted"><Spinner className="h-6 w-6" /></div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <div className="mb-4 flex items-center gap-2 text-sm font-medium text-text">
              <SettingsIcon size={16} /> General information
            </div>
            <div className="space-y-4">
              <Input label="Store name" value={store?.name || ''} onChange={(e) => setStore((prev) => ({ ...prev, name: e.target.value }))} />
              <Input label="Website URL" value={store?.website_url || ''} onChange={(e) => setStore((prev) => ({ ...prev, website_url: e.target.value }))} />
              <Input label="Plan" value={store?.plan || ''} onChange={(e) => setStore((prev) => ({ ...prev, plan: e.target.value }))} />
              <Button onClick={saveBasicSettings} disabled={saving}>
                {saving ? <Spinner /> : <ShieldCheck size={16} />}
                Save settings
              </Button>
            </div>
          </Card>

          <Card>
            <div className="mb-4 flex items-center gap-2 text-sm font-medium text-text">
              <Lock size={16} /> Security
            </div>
            <div className="space-y-4">
              <div className="rounded-lg border border-line bg-paper p-3 text-sm text-muted">
                <div className="flex items-center gap-2 text-text"><Mail size={14} /> Email-based admin access</div>
                <div className="mt-2">Use strong passwords and rotate API keys regularly if they are exposed.</div>
              </div>
              <Button variant="secondary">Review API keys</Button>
              <Button variant="secondary">Disable inactive keys</Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
