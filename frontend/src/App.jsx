import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Result, Button } from 'antd'
import { useAuth } from './stores/auth'
import AdminLayout from './layouts/AdminLayout'
import PortalLayout from './layouts/PortalLayout'

import Login from './views/Login'
import AdminDashboard from './views/admin/Dashboard'
import Tenants from './views/admin/Tenants'
import TenantDetail from './views/admin/TenantDetail'
import Pricing from './views/admin/Pricing'
import PlatformKeys from './views/admin/PlatformKeys'
import UsageRecords from './views/admin/UsageRecords'
import AdminSessions from './views/admin/Sessions'
import AgentsView from './views/admin/AgentsView'
import AuditLogs from './views/admin/AuditLogs'

import PortalDashboard from './views/portal/Dashboard'
import Agents from './views/portal/Agents'
import Environments from './views/portal/Environments'
import Sessions from './views/portal/Sessions'
import Chat from './views/portal/Chat'
import Deployments from './views/portal/Deployments'
import Channels from './views/portal/Channels'
import Vaults from './views/portal/Vaults'
import Wallet from './views/portal/Wallet'
import Usage from './views/portal/Usage'
import ApiKeys from './views/portal/ApiKeys'
import Settings from './views/portal/Settings'

function Guard({ role, children }) {
  const { token, role: currentRole } = useAuth()
  const location = useLocation()
  if (!token) return <Navigate to="/login" replace />
  if (role && currentRole !== role) {
    return (
      <Result
        status="403"
        title="无权访问"
        subTitle="当前账号无权访问该页面"
        extra={
          <Button
            type="primary"
            onClick={() => (currentRole === 'admin' ? (location.pathname = '/admin/dashboard') : (location.pathname = '/portal/dashboard'))}
          >
            返回首页
          </Button>
        }
      />
    )
  }
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/admin"
        element={
          <Guard role="admin">
            <AdminLayout />
          </Guard>
        }
      >
        <Route index element={<Navigate to="/admin/dashboard" replace />} />
        <Route path="dashboard" element={<AdminDashboard />} />
        <Route path="tenants" element={<Tenants />} />
        <Route path="tenants/:id" element={<TenantDetail />} />
        <Route path="pricing" element={<Pricing />} />
        <Route path="platform-keys" element={<PlatformKeys />} />
        <Route path="usage" element={<UsageRecords />} />
        <Route path="sessions" element={<AdminSessions />} />
        <Route path="agents" element={<AgentsView />} />
        <Route path="audit" element={<AuditLogs />} />
      </Route>
      <Route
        path="/portal"
        element={
          <Guard role="tenant">
            <PortalLayout />
          </Guard>
        }
      >
        <Route index element={<Navigate to="/portal/dashboard" replace />} />
        <Route path="dashboard" element={<PortalDashboard />} />
        <Route path="agents" element={<Agents />} />
        <Route path="environments" element={<Environments />} />
        <Route path="sessions" element={<Sessions />} />
        <Route path="chat/:id" element={<Chat />} />
        <Route path="deployments" element={<Deployments />} />
        <Route path="channels" element={<Channels />} />
        <Route path="vaults" element={<Vaults />} />
        <Route path="wallet" element={<Wallet />} />
        <Route path="usage" element={<Usage />} />
        <Route path="api-keys" element={<ApiKeys />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
