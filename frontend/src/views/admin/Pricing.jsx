import { useEffect, useState } from 'react'
import { Alert, Button, Card, InputNumber, Table, message } from 'antd'
import http from '../../api/client'

export default function Pricing() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const r = await http.get('/api/admin/pricing')
      setItems(r.items.map((x) => ({ ...x, _saving: false })))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const save = async (row) => {
    row._saving = true
    setItems([...items])
    try {
      await http.put(`/api/admin/pricing/${row.model_id}`, {
        cost_input_per_m: row.cost_input_per_m,
        cost_output_per_m: row.cost_output_per_m,
        cost_cache_read_per_m: row.cost_cache_read_per_m,
        markup_rate: row.markup_rate,
        web_search_price_per_call: row.web_search_price_per_call,
      })
      message.success('已保存')
      load()
    } finally {
      row._saving = false
    }
  }

  const num = (dataIndex) => ({
    dataIndex,
    render: (_, row) => (
      <InputNumber
        min={0}
        precision={4}
        size="small"
        style={{ width: 110 }}
        value={row[dataIndex]}
        onChange={(v) => { row[dataIndex] = v; setItems([...items]) }}
      />
    ),
  })

  const columns = [
    { title: '模型', dataIndex: 'model_id', width: 150 },
    { ...num('cost_input_per_m'), title: '成本输入(¥/M)' },
    { ...num('cost_output_per_m'), title: '成本输出(¥/M)' },
    { ...num('cost_cache_read_per_m'), title: '成本缓存读(¥/M)' },
    { ...num('markup_rate'), title: '加价率' },
    { ...num('web_search_price_per_call'), title: '搜索单价(¥/次)' },
    {
      title: '生效售价(输入/输出 ¥/M)',
      width: 180,
      render: (_, r) => `${r.sale_input_per_m} / ${r.sale_output_per_m}`,
    },
    {
      title: '操作',
      width: 90,
      render: (_, r) => (
        <Button size="small" type="primary" loading={r._saving} onClick={() => save(r)}>
          保存
        </Button>
      ),
    },
  ]

  return (
    <Card>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        title="售价 = 官方成本价 × 加价率。成本价单位：元 / 百万 Token；计费时按当时单价快照入账，改价不影响历史账单。"
      />
      <Table rowKey="id" columns={columns} dataSource={items} loading={loading} pagination={false} />
    </Card>
  )
}
