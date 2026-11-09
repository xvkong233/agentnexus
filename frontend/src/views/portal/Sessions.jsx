import { useEffect, useState } from 'react'
import {
  Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography, Upload, message,
} from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import http, { fmtMoney, fmtTime, fmtTokens, SOURCE_LABEL, STATUS_LABEL } from '../../api/client'

export default function Sessions() {
  const navigate = useNavigate()
  const [items, setItems] = useState([])
  const [agents, setAgents] = useState([])
  const [envs, setEnvs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [source, setSource] = useState('')
  const [includeArchived, setIncludeArchived] = useState(false)
  const [form] = Form.useForm()
  const [pendingFiles, setPendingFiles] = useState([])

  const load = async (p = 1) => {
    setLoading(true)
    try {
      const r = await http.get('/api/portal/sessions', {
        params: { keyword, status, source, include_archived: includeArchived, page: p, page_size: 50 },
      })
      setItems(r.items)
      setTotal(r.total)
      setPage(p)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(1)
    http.get('/api/portal/agents').then((r) => setAgents(r.items))
    http.get('/api/portal/environments').then((r) => setEnvs(r.items))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeArchived])

  const doCreate = async () => {
    const v = await form.validateFields()
    setCreating(true)
    try {
      const resources = []
      for (const f of pendingFiles) {
        const fd = new FormData()
        fd.append('file', f)
        const up = await http.post('/api/portal/files', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
        resources.push({ type: 'file', file_id: up.id, mount_path: `/data/${up.filename}` })
      }
      const r = await http.post('/api/portal/sessions', {
        agent_id: v.agent_id,
        environment_id: v.environment_id,
        title: v.title || '',
        initial_message: v.initial_message || null,
        resources: resources.length ? resources : null,
      })
      setCreateOpen(false)
      message.success('会话已创建')
      navigate(`/portal/chat/${r.id}`)
    } finally {
      setCreating(false)
    }
  }

  const refresh = async (row) => {
    const r = await http.get(`/api/portal/sessions/${row.id}`)
    setItems((prev) => prev.map((x) => (x.id === row.id ? { ...r, agent_name: row.agent_name } : x)))
    message.success('已刷新并完成实时对账')
  }

  const columns = [
    {
      title: '标题',
      render: (_, r) =>
        r.source === 'web_chat' ? (
          <Typography.Link onClick={() => navigate(`/portal/chat/${r.id}`)}>{r.title || '(未命名)'}</Typography.Link>
        ) : (
          (r.title || '(未命名)')
        ),
    },
    { title: 'Agent', dataIndex: 'agent_name', width: 140 },
    { title: '模型', dataIndex: 'model_id', width: 130 },
    { title: '来源', dataIndex: 'source', width: 90, render: (s) => SOURCE_LABEL[s] || s },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s) => (
        <Tag color={s === 'running' ? 'success' : s === 'terminated' ? 'error' : 'default'}>
          {STATUS_LABEL[s] || s}
        </Tag>
      ),
    },
    {
      title: 'Tokens(入/出)', width: 130,
      render: (_, r) => `${fmtTokens(r.usage.input_tokens)} / ${fmtTokens(r.usage.output_tokens)}`,
    },
    { title: '费用(¥)', dataIndex: 'cost_total', width: 100, render: (v) => fmtMoney(v, 4) },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: fmtTime },
    {
      title: '操作', width: 200,
      render: (_, r) => (
        <Space>
          {r.source === 'web_chat' && (
            <Button size="small" type="primary" onClick={() => navigate(`/portal/chat/${r.id}`)}>打开</Button>
          )}
          <Button size="small" icon={<ReloadOutlined />} onClick={() => refresh(r)}>刷新</Button>
          {!r.archived && (
            <Popconfirm
              title="确认归档该会话？归档后只读。"
              onConfirm={async () => {
                await http.post(`/api/portal/sessions/${r.id}/archive`)
                load(page)
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
      <Space style={{ marginBottom: 16 }} wrap>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setPendingFiles([]); setCreateOpen(true) }}>
          新建会话
        </Button>
        <Input
          placeholder="搜索标题"
          style={{ width: 200 }}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onPressEnter={() => load(1)}
          allowClear
        />
        <Select
          placeholder="状态"
          style={{ width: 110 }}
          value={status || undefined}
          onChange={setStatus}
          allowClear
          options={Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label }))}
        />
        <Select
          placeholder="来源"
          style={{ width: 110 }}
          value={source || undefined}
          onChange={setSource}
          allowClear
          options={Object.entries(SOURCE_LABEL).map(([value, label]) => ({ value, label }))}
        />
        <Switch checkedChildren="含归档" unCheckedChildren="隐藏" checked={includeArchived} onChange={setIncludeArchived} />
        <Button icon={<ReloadOutlined />} onClick={() => load(page)}>刷新</Button>
      </Space>

      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={{ current: page, pageSize: 50, total, onChange: load, showTotal: (t) => `共 ${t} 条` }}
      />

      <Modal
        title="新建会话"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={doCreate}
        confirmLoading={creating}
        okText="创建并进入"
        width={560}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="agent_id" label="Agent" rules={[{ required: true, message: '请选择 Agent' }]}>
            <Select
              placeholder="选择 Agent"
              options={agents.map((a) => ({ value: a.id, label: `${a.name}（${a.model_id} v${a.version}）` }))}
            />
          </Form.Item>
          <Form.Item name="environment_id" label="运行环境" rules={[{ required: true, message: '请选择运行环境' }]}>
            <Select placeholder="选择环境" options={envs.map((e) => ({ value: e.id, label: e.name }))} />
          </Form.Item>
          <Form.Item name="title" label="标题">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item name="initial_message" label="首条消息">
            <Input.TextArea rows={3} placeholder="可选：创建后立即执行的初始指令" />
          </Form.Item>
          <Form.Item label="挂载文件" extra="挂载到沙箱 /mnt/session/uploads 只读目录">
            <Upload
              maxCount={5}
              beforeUpload={(file, fileList) => {
                setPendingFiles(fileList)
                return false
              }}
              onRemove={(f) => setPendingFiles((prev) => prev.filter((x) => x.uid !== f.uid))}
              showUploadList
            >
              <Button size="small">选择文件（可选）</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
