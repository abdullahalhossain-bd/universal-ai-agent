import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { Alert, Button, Input, Spinner } from '../components/ui'
import { ApiError } from '../api/client'

export default function AdminLogin() {
  const { adminLogin } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const onSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await adminLogin(email, password)
      navigate('/admin')
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to sign in to admin.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="w-full max-w-md rounded-2xl border border-line bg-card p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-white">
            <ShieldCheck size={18} strokeWidth={2} />
          </div>
          <div>
            <h1 className="font-display text-xl font-semibold text-text">Platform Admin</h1>
            <p className="text-sm text-muted">Operator access</p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          {error && <Alert>{error}</Alert>}
          <Input
            id="admin-email"
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="admin@company.com"
          />
          <Input
            id="admin-password"
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting && <Spinner />}
            Sign in
          </Button>
        </form>
      </div>
    </div>
  )
}
