import { useEffect, useState } from 'react'
import { Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import http, { fmtTime } from '../../api/client'

const STATUS = { active: ['运行', 'success'], paused: ['已暂停', 'warning'], archived: ['已归档', 'default'] }

export default function Deployments() {
  const [items, setItems] = useState([])
  const [agents, setAgents] = useState([])
  const [envs, setEnvs] = useState([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [runs, setRuns] = useState(null) // { deployment, data }
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const r = await http.get('/api/portal/deployments')
      setItems(r.items)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    http.get('/api/portal/agents').then((r) => setAgents(r.items))
    http.get('/api/portal/environments').then((r) => setEnvs(r.items))
  }, [])

  const save = async () => {
    const v = await form.validateFields()
    await http.post('/api/portal/deployments', {
      name: v.name,
      agent_id: v.agent_id,
      environment_id: v.environment_id,
      schedule: v.expression
        ? { type: 'cron', expression: v.expression, timezone: v.timezone || 'Asia/Shanghai' }
        : null,
      initial_message: v.initial_message,
    })
    message.success('已创建')
    setCreateOpen(false)
    form.resetFields()
    load()
  }

  const showRuns = async (row) => {
    const r = await http.get(`/api/portal/deployments/${row.id}/runs`)
    setRuns({ deployment: row, data: (r.data || []).slice().reverse() })
  }

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: 'Agent', dataIndex: 'agent_name', width: 140 },
    {
      title: '调度', width: 240,
      render: (_, r) =>
        r.schedule ? (
          `${r.schedule.expression}（${r.schedule.timezone || 'Asia/Shanghai'}）`
        ) : (
          <Tag variant="filled">手动触发</Tag>
        ),
    },
    {
      title: '状态', dataIndex: 'status', width: 110,
      render: (_, r) => (
        <Space size={4}>
          <Tag color={STATUS[r.status]?.[1]}>{STATUS[r.status]?.[0] || r.status}</Tag>
          {r.paused_by_guard && <Tag color="error">欠费</Tag>}
        </Space>
      ),
    },
    {
      title: '操作', width: 300,
      render: (_, r) => (
        <Space>
          <Button
            size="small"
            type="primary"
            onClick={async () => {
              await http.post(`/api/portal/deployments/${r.id}/run`)
              message.success('已触发，可在运行记录与会话列表查看')
            }}
          >
            立即运行
          </Button>
          {r.status === 'active' ? (
            <Button
              size="small"
              onClick={async () => {
                await http.post(`/api/portal/deployments/${r.id}/pause`)
                load()
              }}
            >
              暂停
            </Button>
          ) : r.status === 'paused' ? (
            <Button
              size="small"
              onClick={async () => {
                await http.post(`/api/portal/deployments/${r.id}/unpause`)
                load()
              }}
            >
              恢复
            </Button>
          ) : null}
          <Button size="small" onClick={() => showRuns(r)}>运行记录</Button>
          <Popconfirm
            title="确认归档该定时任务？"
            onConfirm={async () => {
              await http.post(`/api/portal/deployments/${r.id}/archive`)
              load()
            }}
          >
            <Button size="small" danger>归档</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <Button
        type="primary"
        icon={<PlusOutlined />}
        style={{ marginBottom: 16 }}
        onClick={() => {
          form.resetFields()
          setCreateOpen(true)
        }}
      >
        创建定时任务
      </Button>
      <Table rowKey="id" columns={columns} dataSource={items} loading={loading} />

      <Modal
        title="创建定时任务"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={save}
        width={620}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="agent_id" label="Agent" rules={[{ required: true }]}>
            <Select options={agents.map((a) => ({ value: a.id, label: `${a.name}（${a.model_id}）` }))} />
          </Form.Item>
          <Form.Item name="environment_id" label="运行环境" rules={[{ required: true }]}>
            <Select options={envs.map((e) => ({ value: e.id, label: e.name }))} />
          </Form.Item>
          <Form.Item name="expression" label="cron 表达式" extra="如 0 9 * * 1-5（留空 = 仅手动触发）">
            <Input placeholder="0 9 * * 1-5" />
          </Form.Item>
          <Form.Item name="timezone" label="时区" initialValue="Asia/Shanghai">
            <Select options={[{ value: 'Asia/Shanghai', label: 'Asia/Shanghai' }]} style={{ width: 220 }} />
          </Form.Item>
          <Form.Item name="initial_message" label="初始指令" rules={[{ required: true }]}>
            <Input.TextArea rows={3} placeholder="每次触发时发给 Agent 的初始任务" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`运行记录 - ${runs?.deployment?.name || ''}`}
        open={!!runs}
        onCancel={() => setRuns(null)}
        footer={null}
        width={720}
      >
        <Table
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={runs?.data || []}
          columns={[
            { title: '运行 ID', dataIndex: 'id', width: 200, ellipsis: true },
            {
              title: '触发', dataIndex: 'trigger_type', width: 90,
              render: (t) => ({ schedule: '定时', manual: '手动' }[t] || t),
            },
            {
              title: '状态', dataIndex: 'status', width: 90,
              render: (s) => <Tag color={s === 'succeeded' ? 'success' : 'error'}>{s}</Tag>,
            },
            { title: '会话', dataIndex: 'session_id', ellipsis: true },
            { title: '时间', dataIndex: 'created_at', width: 160, render: fmtTime },
          ]}
        />
      </Modal>
    </Card>
  )
}
