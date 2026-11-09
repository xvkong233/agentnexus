import { useEffect, useState } from 'react'
import { Card, Table, Tag } from 'antd'
import http, { fmtTime } from '../../api/client'

export default function AgentsView() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)

  const load = async (p = 1) => {
    setLoading(true)
    try {
      const r = await http.get('/api/admin/agents', { params: { page: p, page_size: 50 } })
      setItems(r.items)
      setTotal(r.total)
      setPage(p)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(1)
  }, [])

  const columns = [
    { title: '租户', dataIndex: 'tenant_name', width: 120 },
    { title: '名称', dataIndex: 'name' },
    { title: '模型', dataIndex: 'model_id', width: 140 },
    { title: '版本', dataIndex: 'upstream_version', width: 70, render: (v) => `v${v}` },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s) => <Tag color={s === 'active' ? 'success' : 'default'}>{s === 'active' ? '可用' : '已归档'}</Tag>,
    },
    { title: '描述', dataIndex: 'description', ellipsis: true },
    { title: '上游 ID', dataIndex: 'upstream_id', width: 200, ellipsis: true },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: fmtTime },
  ]

  return (
    <Card>
      <Table
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={{ current: page, pageSize: 50, total, onChange: load, showTotal: (t) => `共 ${t} 条` }}
      />
    </Card>
  )
}
