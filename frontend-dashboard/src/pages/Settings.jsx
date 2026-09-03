import { useEffect, useState } from 'react'
import { Settings as SettingsIcon, ShieldCheck, Lock, Mail, Bot } from 'lucide-react'
import { api, ApiError } from '../api/client'
import { Alert, Button, Card, Input, PageHeader, Spinner } from '../components/ui'

const defaults = {
  agent_name: 'Shop Assistant',
  welcome_message: 'Hi! How can I help you today?',
  language: 'auto',
  tone: 'friendly',
  system_instructions: '',
  product_behavior: 'accurate',
  fallback_message: "I couldn't find that information. Please contact the store for help.",
  enabled: true,
}

export default function Settings() {
  const [store, setStore] = useState(null)
  const [agent, setAgent] = useState(defaults)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    Promise.all([
      api.get('/v1/auth/me'),
      api.get('/v1/stores/me/agent-config'),
    ])
      .then(([account, config]) => {
        setStore(account.store)
        setAgent({ ...defaults, ...config })
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : 'Unable to load settings.'))
      .finally(() => setLoading(false))
  }, [])

  const saveAgent = async () => {
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      const result = await api.put('/v1/stores/me/agent-config', agent)
      setAgent({ ...defaults, ...result })
      setSuccess('AI agent settings saved successfully.')
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save AI agent settings.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <PageHeader title="Settings" description="Manage your store account, AI assistant behavior, and security preferences." />

      {error && <div className="mb-5"><Alert>{error}</Alert></div>}
      {success && <div className="mb-5"><Alert tone="success">{success}</Alert></div>}

      {loading ? (
        <div className="flex justify-center py-12 text-muted"><Spinner className="h-6 w-6" /></div>
      ) : (
        <div className="space-y-5">
          <Card>
            <div className="mb-4 flex items-center gap-2 text-sm font-medium text-text">
              <SettingsIcon size={16} /> Account information
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <Input label="Store name" value={store?.name || ''} readOnly />
              <Input label="Website URL" value={store?.website_url || ''} readOnly />
              <Input label="Plan" value={store?.plan || ''} readOnly />
            </div>
            <p className="mt-3 text-xs text-muted">Plan and account details are controlled by the account and billing system.</p>
          </Card>

          <Card>
            <div className="mb-1 flex items-center gap-2 text-sm font-medium text-text">
              <Bot size={16} /> AI assistant
            </div>
            <p className="mb-5 text-sm text-muted">Customize how your storefront assistant introduces itself and handles product questions.</p>
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="space-y-4">
                <Input label="Assistant name" value={agent.agent_name} onChange={(e) => setAgent((p) => ({ ...p, agent_name: e.target.value }))} />
                <Input label="Welcome message" value={agent.welcome_message} onChange={(e) => setAgent((p) => ({ ...p, welcome_message: e.target.value }))} />
                <label className="block text-sm font-medium text-text">Language<select className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-text" value={agent.language} onChange={(e) => setAgent((p) => ({ ...p, language: e.target.value }))}><option value="auto">Auto-detect</option><option value="en">English</option><option value="bn">Bangla</option></select></label>
                <label className="block text-sm font-medium text-text">Tone<select className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-text" value={agent.tone} onChange={(e) => setAgent((p) => ({ ...p, tone: e.target.value }))}><option value="friendly">Friendly</option><option value="professional">Professional</option><option value="concise">Concise</option><option value="warm">Warm</option></select></label>
              </div>
              <div className="space-y-4">
                <label className="block text-sm font-medium text-text">System instructions<textarea className="mt-1 min-h-32 w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-text" maxLength={5000} value={agent.system_instructions} onChange={(e) => setAgent((p) => ({ ...p, system_instructions: e.target.value }))} placeholder="Example: Be helpful, never invent product details, and keep answers short." /></label>
                <label className="block text-sm font-medium text-text">Product answer style<select className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-text" value={agent.product_behavior} onChange={(e) => setAgent((p) => ({ ...p, product_behavior: e.target.value }))}><option value="accurate">Accuracy first</option><option value="helpful">Helpful recommendations</option><option value="sales">Sales-focused</option></select></label>
                <Input label="Fallback message" value={agent.fallback_message} onChange={(e) => setAgent((p) => ({ ...p, fallback_message: e.target.value }))} />
                <label className="flex items-center gap-2 text-sm text-text"><input type="checkbox" checked={agent.enabled} onChange={(e) => setAgent((p) => ({ ...p, enabled: e.target.checked }))} /> Enable AI assistant</label>
              </div>
            </div>
            <div className="mt-5 flex justify-end">
              <Button onClick={saveAgent} disabled={saving}>
                {saving ? <Spinner /> : <ShieldCheck size={16} />}
                Save AI settings
              </Button>
            </div>
          </Card>

          <Card>
            <div className="mb-4 flex items-center gap-2 text-sm font-medium text-text">
              <Lock size={16} /> Security
            </div>
            <div className="rounded-lg border border-line bg-paper p-3 text-sm text-muted">
              <div className="flex items-center gap-2 text-text"><Mail size={14} /> Email-based dashboard access</div>
              <div className="mt-2">Use strong passwords and rotate API keys regularly if they are exposed.</div>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
