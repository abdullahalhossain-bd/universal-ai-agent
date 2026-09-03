import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Onboarding from './pages/Onboarding'
import Overview from './pages/Overview'
import Websites from './pages/Websites'
import ApiKeys from './pages/ApiKeys'
import Billing from './pages/Billing'
import DataSources from './pages/DataSources'
import ChatPreview from './pages/ChatPreview'
import Messages from './pages/Messages'
import Usage from './pages/Usage'
import Settings from './pages/Settings'
import AdminLogin from './pages/AdminLogin'
import AdminDashboard from './pages/AdminDashboard'
import { Spinner } from './components/ui'

function ProtectedRoute({ children }) { const { user, loading } = useAuth(); if (loading) return <div className="flex min-h-screen items-center justify-center text-accent"><Spinner className="h-6 w-6" /></div>; if (!user) return <Navigate to="/login" replace />; return children }
function PublicOnlyRoute({ children }) { const { user, loading } = useAuth(); if (loading) return null; if (user) return <Navigate to="/" replace />; return children }
function AdminProtectedRoute({ children }) { const { adminUser, adminLoading } = useAuth(); if (adminLoading) return <div className="flex min-h-screen items-center justify-center text-accent"><Spinner className="h-6 w-6" /></div>; if (!adminUser) return <Navigate to="/admin/login" replace />; return children }
function PublicAdminOnlyRoute({ children }) { const { adminUser, adminLoading } = useAuth(); if (adminLoading) return null; if (adminUser) return <Navigate to="/admin" replace />; return children }

function AppRoutes() {
  return <Routes>
    <Route path="/login" element={<PublicOnlyRoute><Login /></PublicOnlyRoute>} />
    <Route path="/signup" element={<PublicOnlyRoute><Signup /></PublicOnlyRoute>} />
    <Route path="/admin/login" element={<PublicAdminOnlyRoute><AdminLogin /></PublicAdminOnlyRoute>} />
    <Route path="/admin" element={<AdminProtectedRoute><AdminDashboard /></AdminProtectedRoute>} />
    <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
      <Route path="/" element={<Overview />} />
      <Route path="/onboarding" element={<Onboarding />} />
      <Route path="/websites" element={<Websites />} />
      <Route path="/api-keys" element={<ApiKeys />} />
      <Route path="/datasources" element={<DataSources />} />
      <Route path="/chat" element={<ChatPreview />} />
      <Route path="/messages" element={<Messages />} />
      <Route path="/usage" element={<Usage />} />
      <Route path="/billing" element={<Billing />} />
      <Route path="/settings" element={<Settings />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>
}
export default function App() { return <AuthProvider><AppRoutes /></AuthProvider> }
