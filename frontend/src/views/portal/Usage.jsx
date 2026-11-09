import { useEffect, useState } from 'react'
import { Button, Card, DatePicker, Select, Space, Table, Typography } from 'antd'
import http, { fmtMoney, fmtTime, fmtTokens, SOURCE_LABEL } from '../../api/client'

const MODELS = ['glm-5.3', 'glm-5.3-flash', 'glm-5.3-flashx', 'glm-5.3-flashx-legal']

export default function Usage() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [modelId, setModelId] = useState('')
  const [source, setSource] = useState('')
  const [range, setRange] = useState(null)

  const load = async (p = 1) => {
    setLoading(true)
    try {
      const p2 = { model_id: modelId, source, page: p, page_size: 20 }
      if (range) {
        p2.start = range[0].format('YYYY-MM-DDTHH:mm:ss')
        p2.end = range[1].format('YYYY-MM-DDTHH:mm:ss')
      }
      const r = await http.get('/api/portal/usage-records', { params: p2 })
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

  const exportCsv = () => {
    const qs = new URLSearchParams()
    if (modelId) qs.set('model_id', modelId)
    if (source) qs.set('source', source)
    if (range) {
      qs.set('start', range[0].format('YYYY-MM-DDTHH:mm:ss'))
      qs.set('end', range[1].format('YYYY-MM-DDTHH:mm:ss'))
    }
    window.open(`/api/portal/usage-records/export.csv?${qs.toString()}`, '_blank')
  }

  const columns = [
    { title: '时间', dataIndex: 'created_at', width: 160, render: fmtTime },
    { title: '模型', dataIndex: 'model_id', width: 130 },
    { title: '来源', dataIndex: 'source', width: 90, render: (s) => SOURCE_LABEL[s] || s },
    { title: '输入', dataIndex: 'input_tokens', width: 90, render: fmtTokens },
    { title: '输出', dataIndex: 'output_tokens', width: 90, render: fmtTokens },
    { title: '缓存读', dataIndex: 'cache_read_tokens', width: 90, render: fmtTokens },
    {
      title: '单价快照(入/出 ¥/M)', width: 180,
      render: (_, r) =>
        `${r.price_snapshot?.input_per_m ? Number(r.price_snapshot.input_per_m) : '-'} / ${
          r.price_snapshot?.output_per_m ? Number(r.price_snapshot.output_per_m) : '-'
        }`,
    },
    {
      title: '费用(¥)', dataIndex: 'cost_total', width: 110,
      render: (v) => <Typography.Text strong>{fmtMoney(v, 6)}</Typography.Text>,
    },
  ]

  return (
    <Card>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="模型"
          style={{ width: 150 }}
          value={modelId || undefined}
          onChange={setModelId}
          allowClear
          options={MODELS.map((m) => ({ value: m, label: m }))}
        />
        <Select
          placeholder="来源"
          style={{ width: 130 }}
          value={source || undefined}
          onChange={setSource}
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
