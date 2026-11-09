import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Divider, Form, Input, Modal, Popconfirm, Radio, Select, Space, Table, Tag, message } from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import http, { fmtTime } from '../../api/client'

const TYPE_LABELS = { feishu: '飞书', wecom: '企业微信', dingtalk: '钉钉', wechat: '个人微信' }

const statusTag = (s) => {
  if (s === 'bound' || s === 'connected') return 'success'
  if (s === 'pending' || s === 'connecting') return 'warning'
  return 'error'
}

export default function Channels() {
  const [items, setItems] = useState([])
  const [agents, setAgents] = useState([])
  const [envs, setEnvs] = useState([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [form] = Form.useForm()
  const [qr, setQr] = useState(null) // { channelId, qrCode, sessionKey, status }
  const qrTimer = useRef(null)
  const channelType = Form.useWatch('channel_type', form)

  const load = async () => {
    setLoading(true)
    try {
      const r = await http.get('/api/portal/channels')
      for (const item of r.items) {
        try {
          const fresh = await http.get(`/api/portal/channels/${item.id}`)
          Object.assign(item, fresh)
        } catch {
          /* keep cached */
        }
      }
      setItems(r.items)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    http.get('/api/portal/agents').then((r) => setAgents(r.items))
    http.get('/api/portal/environments').then((r) => setEnvs(r.items))
    return () => clearInterval(qrTimer.current)
  }, [])

  const startQr = (channelId, qrData) => {
    setQr({ channelId, ...qrData, status: qrData.status || 'pending' })
    clearInterval(qrTimer.current)
    qrTimer.current = setInterval(async () => {
      try {
        const s = await http.get(`/api/portal/channels/${channelId}/qr-session/${qrData.session_key}`)
        setQr((prev) => (prev ? { ...prev, status: s.status } : prev))
        if (s.status === 'bound') {
          clearInterval(qrTimer.current)
          message.success('微信绑定成功')
          load()
        }
      } catch {
        clearInterval(qrTimer.current)
      }
    }, 3000)
  }

  const save = async () => {
    const v = await form.validateFields()
    const body = {
      channel_type: v.channel_type,
      name: v.name,
      agent_id: v.agent_id,
      environment_id: v.environment_id,
    }
    if (v.channel_type !== 'wechat') {
      body.credentials = Object.fromEntries(
        Object.entries({
          app_id: v.app_id,
          app_secret: v.app_secret,
          bot_id: v.bot_id,
          secret: v.secret,
          client_id: v.client_id,
          client_secret: v.client_secret,
        }).filter(([, val]) => val != null && val !== ''),
      )
    }
    const r = await http.post('/api/portal/channels', body)
    setCreateOpen(false)
    message.success('渠道已创建')
    load()
    if (v.channel_type === 'wechat' && r.qr) startQr(r.id, r.qr)
  }

  const columns = [
    {
      title: '渠道', dataIndex: 'channel_type', width: 110,
      render: (t) => <Tag variant="filled">{TYPE_LABELS[t] || t}</Tag>,
    },
    { title: '名称', dataIndex: 'name' },
    {
      title: '绑定', dataIndex: 'binding_status', width: 100,
      render: (s) => <Tag color={statusTag(s)}>{s || '-'}</Tag>,
    },
    {
      title: '连接', dataIndex: 'connection_status', width: 110,
      render: (s) => <Tag color={statusTag(s)}>{s || '-'}</Tag>,
    },
    { title: '最近错误', dataIndex: 'last_error', ellipsis: true },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: fmtTime },
    {
      title: '操作', width: 220,
      render: (_, r) => (
        <Space>
          {r.channel_type === 'wechat' && (
            <Button
              size="small"
              onClick={async () => {
                const qrData = await http.post(`/api/portal/channels/${r.id}/qr-session`)
                startQr(r.id, qrData)
              }}
            >
              扫码绑定
            </Button>
          )}
          <Popconfirm
            title="确认删除该渠道？"
            onConfirm={async () => {
              await http.delete(`/api/portal/channels/${r.id}`)
              load()
            }}
          >
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        title="支持全部官方渠道：飞书 / 企业微信 / 钉钉 / 个人微信。凭据由上游托管（平台不保存）；个人微信创建后需扫码绑定。渠道侧不支持自定义工具人工接续，请使用内置工具。"
      />
      <Space style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            form.resetFields()
            form.setFieldsValue({ channel_type: 'feishu' })
            setCreateOpen(true)
          }}
        >
          接入渠道
        </Button>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新状态</Button>
      </Space>
      <Table rowKey="id" columns={columns} dataSource={items} loading={loading} />

      <Modal
        title="接入聊天渠道"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={save}
        width={620}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="channel_type" label="渠道类型" initialValue="feishu">
            <Radio.Group
              optionType="button"
              options={[
                { value: 'feishu', label: '飞书' },
                { value: 'wecom', label: '企业微信' },
                { value: 'dingtalk', label: '钉钉' },
                { value: 'wechat', label: '个人微信' },
              ]}
            />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="agent_id" label="Agent" rules={[{ required: true }]}>
            <Select options={agents.map((a) => ({ value: a.id, label: `${a.name}（${a.model_id}）` }))} />
          </Form.Item>
          <Form.Item name="environment_id" label="运行环境" rules={[{ required: true }]}>
            <Select options={envs.map((e) => ({ value: e.id, label: e.name }))} />
          </Form.Item>

          {channelType === 'feishu' && (
            <>
              <Divider plain>飞书应用凭据</Divider>
              <Form.Item name="app_id" label="App ID" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="app_secret" label="App Secret" rules={[{ required: true }]}>
                <Input.Password />
              </Form.Item>
            </>
          )}
          {channelType === 'wecom' && (
            <>
              <Divider plain>企业微信智能机器人凭据</Divider>
              <Form.Item name="bot_id" label="Bot ID" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="secret" label="Secret" rules={[{ required: true }]}>
                <Input.Password />
              </Form.Item>
            </>
          )}
          {channelType === 'dingtalk' && (
            <>
              <Divider plain>钉钉应用凭据</Divider>
              <Form.Item name="client_id" label="Client ID" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="client_secret" label="Client Secret" rules={[{ required: true }]}>
                <Input.Password />
              </Form.Item>
            </>
          )}
          {channelType === 'wechat' && (
            <Alert
              type="warning"
              showIcon
              title="无需凭据：创建后将弹出二维码，使用微信扫码绑定（约 8 分钟有效）"
            />
          )}
        </Form>
      </Modal>

      <Modal
        title="微信扫码绑定"
        open={!!qr}
        onCancel={() => {
          clearInterval(qrTimer.current)
          setQr(null)
        }}
        footer={null}
        width={360}
        centered
      >
        <div style={{ textAlign: 'center' }}>
          {qr?.qr_code && <img src={qr.qr_code} alt="QR" style={{ width: 220, height: 220, border: '1px solid #f0f0f0' }} />}
          <div style={{ color: 'rgba(0,0,0,0.45)', fontSize: 13, margin: '8px 0' }}>请使用微信扫描二维码完成绑定</div>
          <Tag color={qr?.status === 'bound' ? 'success' : 'warning'}>{qr?.status === 'bound' ? '绑定成功' : '等待扫码…'}</Tag>
        </div>
      </Modal>
    </Card>
  )
}
