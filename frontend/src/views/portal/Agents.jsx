import { useEffect, useState } from 'react'
import {
  Button, Card, Form, Input, Modal, Select, Space, Switch, Table, Tag, message,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import http from '../../api/client'

const MODELS = [
  { value: 'glm-5.3', label: 'glm-5.3（推理最强）' },
  { value: 'glm-5.3-flash', label: 'glm-5.3-flash（首响快/读图）' },
  { value: 'glm-5.3-flashx', label: 'glm-5.3-flashx（极速/读图）' },
  { value: 'glm-5.3-flashx-legal', label: 'glm-5.3-flashx-legal（法律场景专用）' },
]

function parseJson(text, fallback) {
  if (!text || !text.trim()) return fallback
  try {
    return JSON.parse(text)
  } catch {
    throw new Error('JSON 格式错误，请检查自定义工具 / MCP 配置')
  }
}

export default function Agents() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()
  const [versions, setVersions] = useState(null) // { agent, data }

  const load = async () => {
    setLoading(true)
    try {
      const r = await http.get('/api/portal/agents', { params: { include_archived: includeArchived } })
      setItems(r.items)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [includeArchived])

  const openCreate = () => {
    setEditing(null)
    form.setFieldsValue({
      name: '', modelId: 'glm-5.3-flash', effort: 'high', system: '',
      toolset: true, customTools: '', mcpServers: '', description: '',
    })
    setOpen(true)
  }

  const openEdit = (row) => {
    setEditing(row)
    const model = row.model && typeof row.model === 'object' ? row.model : { id: row.model_id, effort: 'high' }
    const effort = typeof model.effort === 'object' ? model.effort?.type || 'high' : model.effort || 'high'
    const customs = (row.tools || []).filter((t) => t.type === 'custom')
    form.setFieldsValue({
      name: row.name,
      modelId: model.id,
      effort,
      system: row.system || '',
      toolset: (row.tools || []).some((t) => t.type === 'agent_toolset_20260601'),
      customTools: customs.length ? JSON.stringify(customs) : '',
      mcpServers: (row.mcp_servers || []).length ? JSON.stringify(row.mcp_servers) : '',
      description: row.description || '',
    })
    setOpen(true)
  }

  const save = async () => {
    const v = await form.validateFields()
    let payload
    try {
      const tools = []
      if (v.toolset) tools.push({ type: 'agent_toolset_20260601' })
      tools.push(...parseJson(v.customTools, []))
      payload = {
        name: v.name,
        model: { id: v.modelId, effort: v.effort },
        system: v.system || null,
        description: v.description || null,
        tools,
        mcp_servers: parseJson(v.mcpServers, []),
      }
    } catch (err) {
      return message.error(err.message)
    }
    if (editing) {
      await http.post(`/api/portal/agents/${editing.id}`, payload)
      message.success('已更新（生成新版本）')
    } else {
      await http.post('/api/portal/agents', payload)
      message.success('已创建')
    }
    setOpen(false)
    load()
  }

  const showVersions = async (row) => {
    const r = await http.get(`/api/portal/agents/${row.id}/versions`)
    setVersions({ agent: row, data: (r.data || []).slice().reverse() })
  }

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: '模型', dataIndex: 'model_id', width: 140 },
    { title: '版本', dataIndex: 'version', width: 70, render: (v) => `v${v}` },
    {
      title: '工具', width: 180,
      render: (_, r) => (
        <Space size={4} wrap>
          {(r.tools || []).map((t, i) => (
            <Tag key={i} variant="filled">
              {t.type === 'custom' ? `custom:${t.name}` : String(t.type).replace('_20260601', '')}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s) => <Tag color={s === 'active' ? 'success' : 'default'}>{s === 'active' ? '可用' : '已归档'}</Tag>,
    },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    {
      title: '操作', width: 220,
      render: (_, r) => (
        <Space>
          <Button size="small" onClick={() => openEdit(r)}>编辑</Button>
          <Button size="small" onClick={() => showVersions(r)}>版本</Button>
          {r.status === 'active' && (
            <Button
              size="small"
              danger
              onClick={async () => {
                await http.post(`/api/portal/agents/${r.id}/archive`)
                load()
              }}
            >
              归档
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          创建 Agent
        </Button>
        <Switch checkedChildren="显示已归档" unCheckedChildren="隐藏归档" checked={includeArchived} onChange={setIncludeArchived} />
      </Space>

      <Table rowKey="id" columns={columns} dataSource={items} loading={loading} />

      <Modal
        title={editing ? '编辑 Agent' : '创建 Agent'}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={save}
        width={680}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Space size={8} style={{ display: 'flex' }}>
            <Form.Item name="modelId" label="模型" style={{ width: 280 }}>
              <Select options={MODELS} />
            </Form.Item>
            <Form.Item name="effort" label="推理力度" style={{ width: 140 }}>
              <Select
                options={[
                  { value: 'low', label: 'low' },
                  { value: 'high', label: 'high' },
                  { value: 'max', label: 'max' },
                ]}
              />
            </Form.Item>
          </Space>
          <Form.Item name="system" label="系统提示词">
            <Input.TextArea rows={5} placeholder="定义 Agent 的角色与行为" />
          </Form.Item>
          <Form.Item name="toolset" label="内置工具集" valuePropName="checked">
            <Switch checkedChildren="启用（bash/文件/搜索）" unCheckedChildren="停用" />
          </Form.Item>
          <Form.Item
            name="customTools"
            label="自定义工具"
            extra='JSON 数组，如 [{"type":"custom","name":"get_weather","description":"...","input_schema":{...}}]'
          >
            <Input.TextArea rows={3} placeholder="可选" />
          </Form.Item>
          <Form.Item
            name="mcpServers"
            label="MCP 服务器"
            extra='JSON 数组，如 [{"type":"url","name":"github","url":"https://..."}]'
          >
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`版本历史 - ${versions?.agent?.name || ''}`}
        open={!!versions}
        onCancel={() => setVersions(null)}
        footer={null}
        width={760}
      >
        <Table
          size="small"
          rowKey="version"
          pagination={false}
          dataSource={versions?.data || []}
          columns={[
            { title: '版本', dataIndex: 'version', width: 80, render: (v) => `v${v}` },
            { title: '名称', dataIndex: 'name', width: 150 },
            {
              title: '模型', width: 160,
              render: (_, r) => (typeof r.model === 'object' ? r.model?.id : r.model),
            },
            { title: '工具数', width: 80, render: (_, r) => (r.tools || []).length },
            { title: '系统提示词', ellipsis: true, render: (_, r) => (r.system || '').slice(0, 80) },
          ]}
        />
      </Modal>
    </Card>
  )
}
