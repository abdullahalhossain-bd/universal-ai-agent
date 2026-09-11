import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { adminApi, api, getAdminToken, getToken, setAdminToken, setToken } from '../api/client'

const AuthContext = createContext(null)

async function establishInboxSession(email, password) {
  // Dashboard auth and Inbox auth are intentionally separate credentials/tokens.
  // This call only establishes the HttpOnly Inbox cookie; the JWT is never stored in JS.
  try {
    await api.post('/v1/auth/inbox/login', { email, password }, { auth: false })
  } catch {
    // Do not break the main dashboard login if the optional Inbox session cannot be established.
  }
}

const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [store, setStore] = useState(null)
  const [loading, setLoading] = useState(true)

  const [adminUser, setAdminUser] = useState(null)
  const [adminLoading, setAdminLoading] = useState(true)

  const loadMe = useCallback(async () => {
    if (!getToken()) {
      setLoading(false)
      return
    }
    try {
      const data = await api.get('/v1/auth/me')
      setUser(data.user)
      setStore(data.store)
    } catch {
      setToken(null)
      setUser(null)
      setStore(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadAdminMe = useCallback(async () => {
    if (!getAdminToken()) {
      setAdminLoading(false)
      return
    }
    try {
      const data = await adminApi.get('/v1/admin/me')
      setAdminUser(data)
    } catch {
      setAdminToken(null)
      setAdminUser(null)
    } finally {
      setAdminLoading(false)
    }
  }, [])

  useEffect(() => {
    loadMe()
    loadAdminMe()
  }, [loadMe, loadAdminMe])

  const applyAuthResponse = (data) => {
    setToken(data.access_token)
    setUser(data.user)
    setStore(data.store)
  }

  const login = async (email, password) => {
    const data = await api.post('/v1/auth/login', { email, password }, { auth: false })
    applyAuthResponse(data)
    await establishInboxSession(email, password)
    return data
  }

  const signup = async (payload) => {
    const data = await api.post('/v1/auth/signup', payload, { auth: false })
    applyAuthResponse(data)
    await establishInboxSession(payload.email, payload.password)
    return data
  }

  const logout = async () => {
    // Revoke the dashboard session server-side. The Inbox cookie is session-version
    // bound, so it becomes unusable as soon as this succeeds.
    try {
      if (getToken()) await api.post('/v1/auth/logout')
    } catch {
      // Always clear local state even if the server is temporarily unavailable.
    }
    setToken(null)
    setUser(null)
    setStore(null)
  }

  const refreshStore = async () => {
    const data = await api.get('/v1/auth/me')
    setUser(data.user)
    setStore(data.store)
  }

  const adminLogin = async (email, password) => {
    const data = await api.post('/v1/admin/login', { email, password }, { auth: false, token: null })
    setAdminToken(data.access_token)
    setAdminUser(data.admin)
    return data
  }

  const adminLogout = () => {
    setAdminToken(null)
    setAdminUser(null)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        store,
        loading,
        login,
        signup,
        logout,
        refreshStore,
        adminUser,
        adminLoading,
        adminLogin,
        adminLogout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export { AuthProvider }

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
