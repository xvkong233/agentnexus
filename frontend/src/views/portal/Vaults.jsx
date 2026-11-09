import { useEffect, useState } from 'react'
import { Alert, Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import http, { fmtTime } from '../../api/client'

const AUTH_TYPES = [
  { value: 'static_bearer', label: 'static_bearer（MCP Bearer Token）' },
  { value: 'bearer', label: 'bearer（普通站点鉴权）' },
  { value: 'mcp_oauth', label: 'mcp_oauth（MCP OAuth，支持自动刷新）' },
  { value: 'oauth', label: 'oauth' },
  { value: 'environment_variable', label: 'environment_variable（沙箱环境变量）' },
]

export default function Vaults() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [credVault, setCredVault] = useState(null) // 本地 vault 行
  const [creds, setCreds] = useState([])
  const [addOpen, setAddOpen] = useState(false)
  const [credForm] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const r = await http.get('/api/portal/vaults')
      setItems(r.items)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const showCreds = async (row) => {
    setCredVault(row)
    const r = await http.get(`/api/portal/vaults/${row.id}/credentials`)
    setCreds(r.data || [])
  }

  const doAddCred = async () => {
    const v = await credForm.validateFields()
    let auth
    try {
      auth = JSON.parse(v.authJson)
      auth.type = v.type
    } catch {
      return message.error('凭据 JSON 格式错误')
    }
    await http.post(`/api/portal/vaults/${credVault.id}/credentials`, { name: v.name, auth })
    message.success('凭据已保存（不可再查看原文）')
    setAddOpen(false)
    credForm.resetFields()
    showCreds(credVault)
  }

  const columns = [
    { title: '名称', dataIndex: 'display_name' },
    { title: 'ID', dataIndex: 'upstream_id', width: 200, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s) => <Tag color={s === 'active' ? 'success' : 'default'}>{s === 'active' ? '可用' : '已归档'}</Tag>,
    },
    {
      title: '操作', width: 160,
      render: (_, r) => (
        <Space>
          <Button size="small" onClick={() => showCreds(r)}>凭据</Button>
          {r.status === 'active' && (
            <Popconfirm
              title="确认归档该保管库？"
              onConfirm={async () => {
                await http.post(`/api/portal/vaults/${r.id}/archive`)
                load()
              }}
            >
              <Button size="small" danger>归档</Button>
            </Popconfirm>
          )}
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
        title="凭据保管库用于 MCP 服务器鉴权与环境变量密钥。凭据只写不读（任何 API 不回显密钥原文），Agent 与沙箱均无法读取。"
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
        创建保管库
      </Button>
      <Table rowKey="id" columns={columns} dataSource={items} loading={loading} />

      <Modal
        title="创建保管库"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={async () => {
          if (!newName.trim()) return message.error('请输入名称')
          await http.post('/api/portal/vaults', { display_name: newName })
          message.success('已创建')
          setCreateOpen(false)
          load()
        }}
      >
        <Input placeholder="保管库名称" value={newName} onChange={(e) => setNewName(e.target.value)} />
      </Modal>

      <Modal
        title={`凭据 - ${credVault?.display_name || ''}`}
        open={!!credVault}
        onCancel={() => setCredVault(null)}
        footer={null}
        width={760}
      >
        <Button type="primary" size="small" style={{ marginBottom: 8 }} onClick={() => setAddOpen(true)}>
          添加凭据
        </Button>
        <Table
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={creds}
          columns={[
            { title: '名称', dataIndex: 'name' },
            { title: '类型', dataIndex: 'auth', width: 180, render: (a) => a?.type },
            {
              title: '操作', width: 80,
              render: (_, r) => (
                <Popconfirm
                  title="确认删除该凭据？"
                  onConfirm={async () => {
                    await http.delete(`/api/portal/vaults/${credVault.id}/credentials/${r.id}`)
                    showCreds(credVault)
                  }}
                >
                  <Button size="small" danger>删除</Button>
                </Popconfirm>
              ),
            },
          ]}
        />

        <Modal
          title="添加凭据"
          open={addOpen}
          onCancel={() => setAddOpen(false)}
          onOk={doAddCred}
          width={520}
          destroyOnHidden
        >
          <Form form={credForm} layout="vertical">
            <Form.Item name="name" label="名称" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="type" label="类型" initialValue="static_bearer" rules={[{ required: true }]}>
              <Select options={AUTH_TYPES} />
            </Form.Item>
            <Form.Item
              name="authJson"
              label="凭据 JSON"
              rules={[{ required: true }]}
              extra='如 {"token":"sk-...","mcp_server_url":"https://..."} 或 {"name":"MY_KEY","value":"..."}'
            >
              <Input.TextArea rows={5} />
            </Form.Item>
          </Form>
        </Modal>
      </Modal>
    </Card>
  )
}
