import { useState } from 'react'
import { Button, Card, Form, Input, Tabs, Typography } from 'antd'
import { ArrowRightOutlined, DashboardOutlined, MobileOutlined, WalletOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import http from '../api/client'
import { useAuth } from '../stores/auth'
import { BrandMark } from '../components/BrandMark'

const { Text, Title } = Typography

const FEATURES = [
  { icon: <DashboardOutlined />, title: '云端 Agent 托管', desc: '基于智谱 Managed Agents，无需自建沙箱与运行时' },
  { icon: <WalletOutlined />, title: 'Token 实时计费', desc: '预付费钱包 + 官方价矩阵，逐请求计量扣费' },
  { icon: <MobileOutlined />, title: '全渠道触达', desc: '飞书 / 企业微信 / 钉钉 / 个人微信一键接入' },
]

export default function Login() {
  const navigate = useNavigate()
  const setSession = useAuth((s) => s.setSession)
  const [loading, setLoading] = useState(false)

  const onFinish = (role) => async (values) => {
    setLoading(true)
    try {
      const path = role === 'admin' ? '/api/admin/auth/login' : '/api/portal/auth/login'
      const r = await http.post(path, values)
      if (role === 'admin') setSession(r.token, 'admin', r.admin.username)
      else setSession(r.token, 'tenant', r.user.username)
      navigate(role === 'admin' ? '/admin/dashboard' : '/portal/dashboard')
    } finally {
      setLoading(false)
    }
  }

  const formPanel = (
    <div style={{ width: '100%', maxWidth: 380, padding: '32px 0' }}>
      <Title level={3} style={{ marginBottom: 4, fontWeight: 600 }}>
        登录
      </Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
        选择身份，进入对应的控制台
      </Text>
      <Tabs
        centered={false}
        items={[
          {
            key: 'admin',
            label: '管理员',
            children: (
              <Form layout="vertical" onFinish={onFinish('admin')} requiredMark={false}>
                <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                  <Input size="large" placeholder="用户名" autoComplete="username" />
                </Form.Item>
                <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                  <Input.Password size="large" placeholder="密码" autoComplete="current-password" />
                </Form.Item>
                <Button type="primary" size="large" htmlType="submit" block loading={loading}>
                  登录管理控制台 <ArrowRightOutlined />
                </Button>
              </Form>
            ),
          },
          {
            key: 'portal',
            label: '客户',
            children: (
              <Form layout="vertical" onFinish={onFinish('tenant')} requiredMark={false}>
                <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                  <Input size="large" placeholder="用户名" autoComplete="username" />
                </Form.Item>
                <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                  <Input.Password size="large" placeholder="密码" autoComplete="current-password" />
                </Form.Item>
                <Button type="primary" size="large" htmlType="submit" block loading={loading}>
                  登录客户工作台 <ArrowRightOutlined />
                </Button>
              </Form>
            ),
          },
        ]}
      />
      <Text type="secondary" style={{ fontSize: 12, display: 'block', textAlign: 'center', marginTop: 24 }}>
        智谱 Managed Agents · 多租户托管 · 按 Token 计费
      </Text>
    </div>
  )

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#F5F7FA' }}>
      {/* 左侧品牌叙事面板 */}
      <div
        style={{
          flex: '1 1 55%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: '40px 56px',
          color: '#fff',
          background: 'linear-gradient(148deg, #0E1A2E 0%, #102A5C 52%, #134CFF 130%)',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* 装饰网格 */}
        <div
          aria-hidden
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: 'radial-gradient(rgba(255,255,255,0.08) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
            maskImage: 'radial-gradient(ellipse at 30% 20%, black 30%, transparent 75%)',
            WebkitMaskImage: 'radial-gradient(ellipse at 30% 20%, black 30%, transparent 75%)',
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, position: 'relative' }}>
          <BrandMark size={40} dark />
          <div>
            <div style={{ fontSize: 18, fontWeight: 600, lineHeight: 1.2 }}>AgentNexus</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)' }}>灵枢 · Agent 托管与计费平台</div>
          </div>
        </div>

        <div style={{ position: 'relative', maxWidth: 460 }}>
          <Title level={2} style={{ color: '#fff', fontWeight: 600, lineHeight: 1.35 }}>
            连接客户、云端 Agent
            <br />
            与计量计费的智能枢纽
          </Title>
          <div style={{ marginTop: 28, display: 'flex', flexDirection: 'column', gap: 16 }}>
            {FEATURES.map((f) => (
              <div key={f.title} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                <span
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 8,
                    background: 'rgba(255,255,255,0.1)',
                    border: '1px solid rgba(255,255,255,0.16)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 16,
                    flexShrink: 0,
                  }}
                >
                  {f.icon}
                </span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{f.title}</div>
                  <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', marginTop: 2 }}>{f.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ position: 'relative', fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>
          Powered by Zhipu Managed Agents · Ant Design 6 · Ant Design X
        </div>
      </div>

      {/* 右侧表单面板 */}
      <div
        style={{
          flex: '1 1 45%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
        }}
      >
        <Card
          style={{
            width: '100%',
            maxWidth: 420,
            borderRadius: 12,
            boxShadow: '0 6px 16px 0 rgba(16,24,40,0.08), 0 3px 6px -4px rgba(16,24,40,0.12)',
          }}
          styles={{ body: { padding: '8px 28px 20px' } }}
        >
          {formPanel}
        </Card>
      </div>
    </div>
  )
}
