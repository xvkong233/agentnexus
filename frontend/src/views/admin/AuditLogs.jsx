import { useEffect, useState } from 'react'
import { Button, Card, Input, Space, Table, Tag } from 'antd'
import http, { fmtTime } from '../../api/client'

const ACTOR = { admin: '管理员', tenant: '客户', system: '系统', tenant_api: '开放API' }

export default function AuditLogs() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [action, setAction] = useState('')

  const load = async (p = 1) => {
    setLoading(true)
    try {
      const r = await http.get('/api/admin/audit-logs', { params: { action, page: p } })
      setItems(r.items)
      setTotal(r.total)
      setPage(p)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const columns = [
    { title: '时间', dataIndex: 'created_at', width: 160, render: fmtTime },
    { title: '操作者', dataIndex: 'actor_name', width: 120 },
    {
      title: '身份', dataIndex: 'actor_type', width: 90,
      render: (t) => <Tag variant="filled">{ACTOR[t] || t}</Tag>,
    },
    { title: '操作', dataIndex: 'action', width: 180 },
    { title: '目标类型', dataIndex: 'target_type', width: 120 },
    { title: '目标 ID', dataIndex: 'target_id', width: 200, ellipsis: true },
    {
      title: '详情', dataIndex: 'detail',
      render: (d) => <code style={{ fontSize: 12 }}>{JSON.stringify(d)}</code>,
    },
  ]

  return (
    <Card>
      <Space style={{ marginBottom: 16 }}>
        <Input
          placeholder="按操作过滤，如 wallet.recharge"
          style={{ width: 260 }}
          value={action}
          onChange={(e) => setAction(e.target.value)}
          onPressEnter={() => load(1)}
          allowClear
        />
        <Button type="primary" onClick={() => load(1)}>查询</Button>
      </Space>
      <Table
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={{ current: page, pageSize: 20, total, onChange: load, showTotal: (t) => `共 ${t} 条` }}
      />
    </Card>
  )
}
