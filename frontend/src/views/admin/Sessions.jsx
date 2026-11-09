import { useEffect, useState } from 'react'
import { Button, Card, Input, Popconfirm, Select, Space, Table, Tag, Typography, message } from 'antd'
import { useSearchParams } from 'react-router-dom'
import http, { fmtMoney, fmtTime, fmtTokens, SOURCE_LABEL, STATUS_LABEL } from '../../api/client'

export default function Sessions() {
  const [searchParams] = useSearchParams()
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState(searchParams.get('keyword') || '')
  const [status, setStatus] = useState('')
  const [source, setSource] = useState('')

  const load = async (p = 1) => {
    setLoading(true)
    try {
      const r = await http.get('/api/admin/sessions', {
        params: { keyword, status, source, page: p, page_size: 20, tenant_id: searchParams.get('tenant_id') || '' },
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refresh = async (row) => {
    const r = await http.get(`/api/admin/sessions/${row.id}`)
    setItems((prev) => prev.map((x) => (x.id === row.id ? { ...r, tenant_name: row.tenant_name } : x)))
    message.success('已刷新（并完成实时对账）')
  }

  const columns = [
    { title: '时间', dataIndex: 'created_at', width: 160, render: fmtTime },
    { title: '租户', dataIndex: 'tenant_name' },
    { title: '标题', dataIndex: 'title', render: (t) => t || '(未命名)' },
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
    {
      title: '操作', width: 140,
      render: (_, r) => (
        <Space>
          <Button size="small" onClick={() => refresh(r)}>刷新</Button>
          <Popconfirm
            title="确认删除该会话？上游会话与本地记录一并删除。"
            onConfirm={async () => {
              await http.post(`/api/admin/sessions/${r.id}/ops`, { action: 'delete' })
              message.success('已删除')
              load(page)
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
      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder="标题/会话ID"
          style={{ width: 200 }}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onPressEnter={() => load(1)}
          allowClear
        />
        <Select
          placeholder="状态"
          style={{ width: 120 }}
          value={status || undefined}
          onChange={(v) => setStatus(v || '')}
          allowClear
          options={Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label }))}
        />
        <Select
          placeholder="来源"
          style={{ width: 120 }}
          value={source || undefined}
          onChange={(v) => setSource(v || '')}
          allowClear
          options={Object.entries(SOURCE_LABEL).map(([value, label]) => ({ value, label }))}
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
