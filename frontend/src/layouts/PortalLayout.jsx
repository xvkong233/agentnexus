import { useEffect, useState } from 'react'
import { Layout, Menu, Dropdown, Space, Tag, Typography } from 'antd'
import {
  DashboardOutlined,
  MessageOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  ClockCircleOutlined,
  MobileOutlined,
  SafetyCertificateOutlined,
  WalletOutlined,
  BarChartOutlined,
  KeyOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import http, { fmtMoney } from '../api/client'
import { useAuth } from '../stores/auth'
import { BrandMark } from '../components/BrandMark'

const { Sider, Header, Content } = Layout

const ITEMS = [
  { key: '/portal/dashboard', icon: <DashboardOutlined />, label: '工作台' },
  { key: '/portal/sessions', icon: <MessageOutlined />, label: '会话与聊天' },
  { key: '/portal/agents', icon: <AppstoreOutlined />, label: 'Agent 管理' },
  { key: '/portal/environments', icon: <CloudServerOutlined />, label: '运行环境' },
  { key: '/portal/deployments', icon: <ClockCircleOutlined />, label: '定时任务' },
  { key: '/portal/channels', icon: <MobileOutlined />, label: '聊天渠道' },
  { key: '/portal/vaults', icon: <SafetyCertificateOutlined />, label: '凭据保管库' },
  { key: '/portal/wallet', icon: <WalletOutlined />, label: '钱包与账单' },
  { key: '/portal/usage', icon: <BarChartOutlined />, label: '用量统计' },
  { key: '/portal/api-keys', icon: <KeyOutlined />, label: 'API 密钥' },
  { key: '/portal/settings', icon: <SettingOutlined />, label: '工具回调设置' },
]

export default function PortalLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { name, logout } = useAuth()
  const [wallet, setWallet] = useState({ balance: 0, blocked: false, blocked_reason: '' })
  const [tenantName, setTenantName] = useState('')

  useEffect(() => {
    http
      .get('/api/portal/me')
      .then((me) => {
        setTenantName(me.tenant?.name || '')
        setWallet(me.wallet || { balance: 0, blocked: false })
      })
      .catch(() => {})
  }, [location.pathname])

  const selected = '/' + location.pathname.split('/').slice(1, 3).join('/')

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="dark">
        <div style={{ padding: '20px 20px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <BrandMark size={32} dark />
          <div>
            <div style={{ color: '#fff', fontSize: 15, fontWeight: 600, lineHeight: 1.3 }}>AgentNexus</div>
            <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12 }}>{tenantName || '客户工作台'}</div>
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selected]}
          items={ITEMS}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            paddingInline: 24,
            borderBottom: '1px solid #f0f0f0',
            height: 56,
          }}
        >
          {wallet.blocked ? (
            <Tag color="error">服务已暂停：{wallet.blocked_reason || '余额不足'}</Tag>
          ) : (
            <Tag color="success" variant="filled">
              余额 ¥{fmtMoney(wallet.balance, 2)}
            </Tag>
          )}
          <Dropdown
            menu={{
              items: [{ key: 'logout', icon: <LogoutOutlined />, label: '退出登录' }],
              onClick: ({ key }) => {
                if (key === 'logout') {
                  logout()
                  navigate('/login')
                }
              },
            }}
          >
            <Space style={{ cursor: 'pointer' }}>
              <Tag icon={<UserOutlined />} variant="filled">
                {name || '客户'}
              </Tag>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 16 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
