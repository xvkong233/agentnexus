import { Layout, Menu, Dropdown, Space, Tag, Typography } from 'antd'
import {
  DashboardOutlined,
  TeamOutlined,
  DollarOutlined,
  KeyOutlined,
  BarChartOutlined,
  MessageOutlined,
  AppstoreOutlined,
  FileTextOutlined,
  UserOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../stores/auth'
import { BrandMark } from '../components/BrandMark'

const { Sider, Header, Content } = Layout

const ITEMS = [
  { key: '/admin/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/admin/tenants', icon: <TeamOutlined />, label: '租户管理' },
  { key: '/admin/pricing', icon: <DollarOutlined />, label: '定价配置' },
  { key: '/admin/platform-keys', icon: <KeyOutlined />, label: '平台密钥' },
  { key: '/admin/usage', icon: <BarChartOutlined />, label: '用量流水' },
  { key: '/admin/sessions', icon: <MessageOutlined />, label: '全局会话' },
  { key: '/admin/agents', icon: <AppstoreOutlined />, label: 'Agent 管理' },
  { key: '/admin/audit', icon: <FileTextOutlined />, label: '审计日志' },
]

export default function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { name, logout } = useAuth()

  const selected = '/' + location.pathname.split('/').slice(1, 3).join('/')

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="dark">
        <div style={{ padding: '20px 20px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <BrandMark size={32} dark />
          <div>
            <div style={{ color: '#fff', fontSize: 15, fontWeight: 600, lineHeight: 1.3 }}>AgentNexus</div>
            <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12 }}>灵枢 · 管理控制台</div>
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
          <Typography.Text type="secondary">AgentNexus · 智谱 Managed Agents 多租户托管与计费枢纽</Typography.Text>
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
                {name || '管理员'}
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
