import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Check, Copy, ShieldAlert } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { Alert, Button, Input, Spinner } from '../components/ui'
import { ApiError } from '../api/client'
import { AuthShell } from './Login'

export default function Signup() {
  const { signup } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ storeName: '', email: '', password: '', websiteUrl: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [issuedKey, setIssuedKey] = useState(null)
  const [copied, setCopied] = useState(false)

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const onSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const data = await signup({
        store_name: form.storeName,
        email: form.email,
        password: form.password,
        website_url: form.websiteUrl || undefined,
        plan: 'starter',
      })
      setIssuedKey(data.api_key)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (issuedKey) {
    return (
      <AuthShell>
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-accent-soft text-accent">
          <ShieldAlert size={20} strokeWidth={1.9} />
        </div>
        <h1 className="font-display text-xl font-semibold text-text">Save your API key</h1>
        <p className="mt-1.5 text-sm text-muted">
          This is the widget key for your storefront chat. For security, it&apos;s shown only
          once — copy it now and store it somewhere safe.
        </p>

        <div className="mt-5 flex items-center justify-between gap-2 rounded-lg border border-line bg-paper px-3.5 py-3">
          <code className="truncate text-sm text-text">{issuedKey}</code>
          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(issuedKey)
              setCopied(true)
              setTimeout(() => setCopied(false), 1500)
            }}
            className="flex shrink-0 items-center gap-1.5 rounded-md border border-line bg-white px-2.5 py-1.5 text-xs font-medium text-text hover:bg-paper"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>

        <Button className="mt-6 w-full" onClick={() => navigate('/')}>
          I&apos;ve saved it — continue
        </Button>
      </AuthShell>
    )
  }

  return (
    <AuthShell>
      <h1 className="font-display text-xl font-semibold text-text">Create your account</h1>
      <p className="mt-1.5 text-sm text-muted">Start on the Starter plan, free — upgrade anytime.</p>

      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        {error && <Alert>{error}</Alert>}
        <Input
          id="storeName"
          label="Store name"
          required
          value={form.storeName}
          onChange={update('storeName')}
          placeholder="Acme Outfitters"
        />
        <Input
          id="websiteUrl"
          label="Website URL"
          hint="Optional — you can connect it later from Websites."
          value={form.websiteUrl}
          onChange={update('websiteUrl')}
          placeholder="https://acme-outfitters.com"
        />
        <Input
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={form.email}
          onChange={update('email')}
          placeholder="you@yourstore.com"
        />
        <Input
          id="password"
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={form.password}
          onChange={update('password')}
          placeholder="At least 8 characters"
        />
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting && <Spinner />}
          Create account
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        Already have an account?{' '}
        <Link to="/login" className="font-medium text-accent hover:text-accent-hover">
          Log in
        </Link>
      </p>
    </AuthShell>
  )
}
