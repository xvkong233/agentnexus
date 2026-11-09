import { useEffect, useState } from 'react'
import { Button, Card, DatePicker, Select, Space, Table } from 'antd'
import { useSearchParams } from 'react-router-dom'
import http, { fmtMoney, fmtTime, fmtTokens, SOURCE_LABEL } from '../../api/client'

const MODELS = ['glm-5.3', 'glm-5.3-flash', 'glm-5.3-flashx', 'glm-5.3-flashx-legal']

export default function UsageRecords() {
  const [searchParams] = useSearchParams()
  const [items, setItems] = useState([])
  const [tenants, setTenants] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [tenantId, setTenantId] = useState(searchParams.get('tenant_id') || '')
  const [modelId, setModelId] = useState('')
  const [source, setSource] = useState('')
  const [range, setRange] = useState(null)

  const params = () => {
    const p = { tenant_id: tenantId, model_id: modelId, source, page, page_size: 20 }
    if (range) {
      p.start = range[0].format('YYYY-MM-DDTHH:mm:ss')
      p.end = range[1].format('YYYY-MM-DDTHH:mm:ss')
    }
    return p
  }

  const load = async (p = 1) => {
    setLoading(true)
    try {
      const r = await http.get('/api/admin/usage-records', { params: { ...params(), page: p } })
      setItems(r.items)
      setTotal(r.total)
      setPage(p)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(1)
    http.get('/api/admin/tenants', { params: { page: 1, page_size: 200 } }).then((t) => setTenants(t.items))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const exportCsv = () => {
    const p = params()
    const qs = new URLSearchParams()
    Object.entries(p).forEach(([k, v]) => v && qs.set(k, v))
    window.open(`/api/admin/usage-records/export.csv?${qs.toString()}`, '_blank')
  }

  const columns = [
    { title: '时间', dataIndex: 'created_at', width: 160, render: fmtTime },
    { title: '租户', dataIndex: 'tenant_name' },
    { title: '模型', dataIndex: 'model_id', width: 130 },
    { title: '来源', dataIndex: 'source', width: 90, render: (s) => SOURCE_LABEL[s] || s },
    { title: '输入', dataIndex: 'input_tokens', width: 90, render: fmtTokens },
    { title: '输出', dataIndex: 'output_tokens', width: 90, render: fmtTokens },
    { title: '缓存读', dataIndex: 'cache_read_tokens', width: 90, render: fmtTokens },
    { title: '搜索', dataIndex: 'web_search_requests', width: 60 },
    { title: '费用(¥)', dataIndex: 'cost_total', width: 110, render: (v) => <b>{fmtMoney(v, 6)}</b> },
    { title: '会话', dataIndex: 'upstream_session_id', width: 180, ellipsis: true },
  ]

  return (
    <Card>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="租户"
          style={{ width: 180 }}
          showSearch
          optionFilterProp="label"
          value={tenantId || undefined}
          onChange={(v) => setTenantId(v || '')}
          allowClear
          options={tenants.map((t) => ({ value: t.id, label: t.name }))}
        />
        <Select
          placeholder="模型"
          style={{ width: 150 }}
          value={modelId || undefined}
          onChange={(v) => setModelId(v || '')}
          allowClear
          options={MODELS.map((m) => ({ value: m, label: m }))}
        />
        <Select
          placeholder="来源"
          style={{ width: 120 }}
          value={source || undefined}
          onChange={(v) => setSource(v || '')}
          allowClear
          options={Object.entries(SOURCE_LABEL).map(([value, label]) => ({ value, label }))}
        />
        <DatePicker.RangePicker showTime value={range} onChange={setRange} />
        <Button type="primary" onClick={() => load(1)}>查询</Button>
        <Button onClick={exportCsv}>导出 CSV</Button>
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
