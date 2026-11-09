import { useEffect, useState } from 'react'
import { Alert, Button, Card, Form, Input, Modal, Popconfirm, Radio, Space, Switch, Table, Tag, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import http from '../../api/client'

const splitList = (text) =>
  (text || '').split(/[,，]/).map((s) => s.trim()).filter(Boolean)

export default function Environments() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const r = await http.get('/api/portal/environments')
      setItems(r.items)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const openCreate = () => {
    setEditing(null)
    form.setFieldsValue({
      name: '', apt: '', pip: '', npm: '', networkType: 'unrestricted',
      allowedHosts: '', allowPkgManagers: false, allowMcp: false,
    })
    setOpen(true)
  }

  const openEdit = (row) => {
    setEditing(row)
    const pkgs = row.config?.packages || {}
    form.setFieldsValue({
      name: row.name,
      apt: (pkgs.apt || []).join(', '),
      pip: (pkgs.pip || []).join(', '),
      npm: (pkgs.npm || []).join(', '),
      networkType: row.config?.networking?.type || 'unrestricted',
      allowedHosts: (row.config?.networking?.allowed_hosts || []).join(', '),
      allowPkgManagers: !!row.config?.networking?.allow_package_managers,
      allowMcp: !!row.config?.networking?.allow_mcp_servers,
    })
    setOpen(true)
  }

  const save = async () => {
    const v = await form.validateFields()
    const body = {
      name: v.name,
      networking:
        v.networkType === 'limited'
          ? {
              type: 'limited',
              allowed_hosts: splitList(v.allowedHosts),
              allow_package_managers: v.allowPkgManagers,
              allow_mcp_servers: v.allowMcp,
            }
          : { type: 'unrestricted' },
    }
    if (v.apt) body.apt = splitList(v.apt)
    if (v.pip) body.pip = splitList(v.pip)
    if (v.npm) body.npm = splitList(v.npm)
    if (editing) {
      await http.post(`/api/portal/environments/${editing.id}`, body)
      message.success('已更新（只影响之后新建的会话）')
    } else {
      await http.post('/api/portal/environments', body)
      message.success('已创建')
    }
    setOpen(false)
    load()
  }

  const networkType = Form.useWatch('networkType', form)

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: '环境 ID', dataIndex: 'upstream_id', width: 200, ellipsis: true },
    {
      title: '预装包', width: 280,
      render: (_, r) => {
        const pkgs = r.config?.packages || {}
        const tags = Object.entries(pkgs)
          .filter(([, p]) => p && p.length)
          .map(([mgr, p]) => (
            <Tag key={mgr} variant="filled">
              {mgr}: {p.join(', ')}
            </Tag>
          ))
        return tags.length ? <Space size={4} wrap>{tags}</Space> : '—'
      },
    },
    {
      title: '网络策略', width: 200,
      render: (_, r) =>
        r.config?.networking?.type === 'limited'
          ? `受限（${(r.config.networking.allowed_hosts || []).length} 个主机）`
          : '开放（HTTP/HTTPS）',
    },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s) => <Tag color={s === 'active' ? 'success' : 'default'}>{s === 'active' ? '可用' : '已归档'}</Tag>,
    },
    {
      title: '操作', width: 160,
      render: (_, r) => (
        <Space>
          <Button size="small" onClick={() => openEdit(r)}>编辑</Button>
          {r.status === 'active' && (
            <Popconfirm
              title="确认归档该环境？引用它的会话将在后续交互中终止。"
              onConfirm={async () => {
                await http.post(`/api/portal/environments/${r.id}/archive`)
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
      <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 16 }} onClick={openCreate}>
        创建环境
      </Button>
      <Table rowKey="id" columns={columns} dataSource={items} loading={loading} />

      <Modal
        title={editing ? '编辑环境' : '创建环境'}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={save}
        width={640}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="apt" label="apt 包" extra="逗号分隔，如 poppler-utils, ffmpeg">
            <Input />
          </Form.Item>
          <Form.Item name="pip" label="pip 包" extra="逗号分隔，如 pandas, matplotlib">
            <Input />
          </Form.Item>
          <Form.Item name="npm" label="npm 包" extra="逗号分隔，如 typescript">
            <Input />
          </Form.Item>
          <Form.Item name="networkType" label="网络策略">
            <Radio.Group
              options={[
                { value: 'unrestricted', label: '开放（出站 HTTP/HTTPS）' },
                { value: 'limited', label: '受限白名单' },
              ]}
            />
          </Form.Item>
          {networkType === 'limited' && (
            <>
              <Form.Item name="allowedHosts" label="允许的主机" extra="逗号分隔，如 api.example.com, *.github.com">
                <Input />
              </Form.Item>
              <Form.Item name="allowPkgManagers" label="允许包管理器" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name="allowMcp" label="允许 MCP" valuePropName="checked">
                <Switch />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </Card>
  )
}
