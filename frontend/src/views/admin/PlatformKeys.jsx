import { useEffect, useState } from 'react'
import { Alert, Button, Card, Form, Input, Modal, Select, Space, Switch, Table, Tag, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import http from '../../api/client'

export default function PlatformKeys() {
  const [items, setItems] = useState([])
  const [tenants, setTenants] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const r = await http.get('/api/admin/platform-keys')
      setItems(r.items)
      const t = await http.get('/api/admin/tenants', { params: { page: 1, page_size: 200 } })
      setTenants(t.items)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const tenantName = (id) => (!id ? '—' : tenants.find((t) => t.id === id)?.name || id)

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: '密钥', dataIndex: 'key_hint', width: 140 },
    {
      title: '默认', dataIndex: 'is_default', width: 80,
      render: (v) => (v ? <Tag color="success">默认</Tag> : null),
    },
    { title: '绑定租户', dataIndex: 'tenant_id', width: 150, render: tenantName },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s) => <Tag color={s === 'active' ? 'success' : 'default'}>{s === 'active' ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', width: 220,
      render: (_, r) => (
        <Space>
          {!r.is_default && (
            <Button
              size="small"
              onClick={async () => {
                await http.post(`/api/admin/platform-keys/${r.id}/set-default`)
                message.success('已设为默认')
                load()
              }}
            >
              设为默认
            </Button>
          )}
          <Button
            size="small"
            danger={r.status === 'active'}
            onClick={async () => {
              await http.post(`/api/admin/platform-keys/${r.id}/status?status=${r.status === 'active' ? 'disabled' : 'active'}`)
              load()
            }}
          >
            {r.status === 'active' ? '停用' : '启用'}
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        title="平台持有的智谱 BigModel API Key（Fernet 加密落库，仅显示尾号）。默认 Key 承接未绑定租户的调用；绑定租户的 Key 可让上游费用按客户归属。"
      />
      <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 16 }} onClick={() => setOpen(true)}>
        添加密钥
      </Button>
      <Table rowKey="id" columns={columns} dataSource={items} loading={loading} />
      <Modal
        title="添加平台密钥"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={async () => {
          const v = await form.validateFields()
          await http.post('/api/admin/platform-keys', v)
          message.success('已添加')
          setOpen(false)
          form.resetFields()
          load()
        }}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="如 生产密钥" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key" rules={[{ required: true, min: 8 }]}>
            <Input.Password placeholder="BigModel API Key" />
          </Form.Item>
          <Form.Item name="is_default" label="设为默认" valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
          <Form.Item name="tenant_id" label="绑定租户">
            <Select
              allowClear
              placeholder="不绑定"
              options={tenants.map((t) => ({ value: t.id, label: `${t.name}（${t.code}）` }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
