import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { adminApi, api, getAdminToken, getToken, setAdminToken, setToken } from '../api/client'

const AuthContext = createContext(null)

async function establishInboxSession() {
  // The dashboard JWT is used only to bootstrap the separate HttpOnly Inbox cookie.
  // Passwords are never sent to a second login endpoint and never retained here.
  try { await api.post('/v1/auth/inbox/establish') } catch { /* Inbox can be retried on the next authenticated load. */ }
}

const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [store, setStore] = useState(null)
  const [loading, setLoading] = useState(true)
  const [adminUser, setAdminUser] = useState(null)
  const [adminLoading, setAdminLoading] = useState(true)

  const loadMe = useCallback(async () => {
    if (!getToken()) { setLoading(false); return }
    try {
      const data = await api.get('/v1/auth/me')
      setUser(data.user); setStore(data.store)
      await establishInboxSession()
    } catch {
      setToken(null); setUser(null); setStore(null)
    } finally { setLoading(false) }
  }, [])

  const loadAdminMe = useCallback(async () => {
    if (!getAdminToken()) { setAdminLoading(false); return }
    try { setAdminUser(await adminApi.get('/v1/admin/me')) }
    catch { setAdminToken(null); setAdminUser(null) }
    finally { setAdminLoading(false) }
  }, [])

  useEffect(() => { loadMe(); loadAdminMe() }, [loadMe, loadAdminMe])

  const applyAuthResponse = (data) => {
    setToken(data.access_token); setUser(data.user); setStore(data.store)
  }

  const login = async (email, password) => {
    const data = await api.post('/v1/auth/login', { email, password }, { auth: false })
    applyAuthResponse(data)
    await establishInboxSession()
    return data
  }

  const signup = async (payload) => {
    const data = await api.post('/v1/auth/signup', payload, { auth: false })
    applyAuthResponse(data)
    await establishInboxSession()
    return data
  }

  const logout = async () => {
    try { if (getToken()) await api.post('/v1/auth/logout') } catch { /* local logout still proceeds */ }
    setToken(null); setUser(null); setStore(null)
  }

  const refreshStore = async () => {
    const data = await api.get('/v1/auth/me')
    setUser(data.user); setStore(data.store)
    await establishInboxSession()
  }

  const adminLogin = async (email, password) => {
    const data = await api.post('/v1/admin/login', { email, password }, { auth: false, token: null })
    setAdminToken(data.access_token); setAdminUser(data.admin); return data
  }

  const adminLogout = () => { setAdminToken(null); setAdminUser(null) }

  return <AuthContext.Provider value={{ user, store, loading, login, signup, logout, refreshStore, adminUser, adminLoading, adminLogin, adminLogout }}>
    {children}
  </AuthContext.Provider>
}

export { AuthProvider }
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
