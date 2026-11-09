import { useEffect, useState } from 'react'
import { Alert, Button, Card, Input, Modal, Popconfirm, Space, Table, Tag, Typography, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import http, { fmtTime } from '../../api/client'

export default function ApiKeys() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [created, setCreated] = useState(null) // 完整密钥（仅显示一次）
  const [newName, setNewName] = useState('')

  const origin = window.location.origin

  const load = async () => {
    setLoading(true)
    try {
      const r = await http.get('/api/portal/api-keys')
      setItems(r.items)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: '密钥前缀', dataIndex: 'prefix', width: 160 },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s) => <Tag color={s === 'active' ? 'success' : 'default'}>{s === 'active' ? '启用' : '已吊销'}</Tag>,
    },
    { title: '最近使用', dataIndex: 'last_used_at', width: 160, render: fmtTime },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: fmtTime },
    {
      title: '操作', width: 100,
      render: (_, r) =>
        r.status === 'active' ? (
          <Popconfirm
            title="确认吊销？使用该密钥的接入将立即失效。"
            onConfirm={async () => {
              await http.post(`/api/portal/api-keys/${r.id}/revoke`)
              load()
            }}
          >
            <Button size="small" danger>吊销</Button>
          </Popconfirm>
        ) : null,
    },
  ]

  return (
    <Card>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        title="开放平台 API Key 用于客户系统程序化接入（基址 /api/open/v1，认证头 X-API-Key）。完整密钥仅在创建时显示一次。"
      />
      <Button
        type="primary"
        icon={<PlusOutlined />}
        style={{ marginBottom: 16 }}
        onClick={() => {
          setNewName('')
          setCreateOpen(true)
        }}
      >
        创建 API Key
      </Button>
      <Table rowKey="id" columns={columns} dataSource={items} loading={loading} />

      <Modal
        title="创建 API Key"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={async () => {
          const r = await http.post('/api/portal/api-keys', { name: newName || 'default' })
          setCreated(r.api_key)
          setCreateOpen(false)
          load()
        }}
      >
        <Input placeholder="名称，如 生产环境" value={newName} onChange={(e) => setNewName(e.target.value)} />
      </Modal>

      <Modal
        title="密钥已创建（仅显示一次）"
        open={!!created}
        onCancel={() => setCreated(null)}
        footer={null}
        width={620}
      >
        <Alert type="warning" showIcon title="请立即复制保存，关闭后无法再次查看完整密钥" />
        <Space.Compact style={{ width: '100%', marginTop: 12 }}>
          <Input value={created || ''} readOnly />
          <Button
            type="primary"
            onClick={() => {
              navigator.clipboard.writeText(created)
              message.success('已复制')
            }}
          >
            复制
          </Button>
        </Space.Compact>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>
          <b>快速接入示例：</b>
        </Typography.Paragraph>
        <pre style={{ background: '#FAFAFA', padding: 12, borderRadius: 8, fontSize: 12, overflow: 'auto' }}>
{`# 创建会话
curl -X POST ${origin}/api/open/v1/sessions \\
  -H "X-API-Key: ${created || ''}" -H "Content-Type: application/json" \\
  -d '{"agent_id":"<Agent ID>","environment_id":"<环境 ID>","initial_message":"你好"}'

# 发送消息
curl -X POST ${origin}/api/open/v1/sessions/<会话ID>/messages \\
  -H "X-API-Key: ${created || ''}" -H "Content-Type: application/json" \\
  -d '{"text":"你的问题"}'

# 查询用量
curl ${origin}/api/open/v1/usage/summary -H "X-API-Key: ${created || ''}"`}
        </pre>
      </Modal>
    </Card>
  )
}
