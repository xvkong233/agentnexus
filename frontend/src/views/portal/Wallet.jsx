import { useEffect, useState } from 'react'
import { Alert, Card, Col, Descriptions, Row, Select, Table, Tag, Typography } from 'antd'
import http, { fmtMoney, fmtTime, fmtTokens } from '../../api/client'

const TX_TYPE = { recharge: ['充值', 'success'], adjust: ['调整', 'warning'], consumption: ['消费', 'error'], refund: ['退款', 'default'] }

export default function Wallet() {
  const [wallet, setWallet] = useState({ balance: 0, blocked: false })
  const [summary, setSummary] = useState({})
  const [month, setMonth] = useState('')
  const [txType, setTxType] = useState('')
  const [tx, setTx] = useState({ items: [], total: 0, page: 1 })

  const monthOptions = (() => {
    const out = []
    const now = new Date()
    for (let i = 0; i < 12; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
      out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
    }
    return out
  })()

  useEffect(() => {
    setMonth(monthOptions[0])
    http.get('/api/portal/wallet').then(setWallet)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (month) http.get('/api/portal/usage/summary', { params: { month } }).then(setSummary)
  }, [month])

  const loadTx = async (page = 1) => {
    const r = await http.get('/api/portal/wallet/transactions', { params: { type: txType, page, page_size: 20 } })
    setTx({ ...r, page })
  }

  useEffect(() => {
    loadTx(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [txType])

  const columns = [
    { title: '时间', dataIndex: 'created_at', width: 160, render: fmtTime },
    {
      title: '类型', dataIndex: 'type', width: 90,
      render: (t) => <Tag color={TX_TYPE[t]?.[1]}>{TX_TYPE[t]?.[0] || t}</Tag>,
    },
    {
      title: '金额', dataIndex: 'amount', width: 130,
      render: (v) => (
        <Typography.Text type={v >= 0 ? 'success' : 'danger'} strong>
          {v >= 0 ? '+' : ''}{fmtMoney(v, 6)}
        </Typography.Text>
      ),
    },
    { title: '变动后余额', dataIndex: 'balance_after', width: 130, render: (v) => fmtMoney(v, 6) },
    { title: '备注', dataIndex: 'note' },
    { title: '操作方', dataIndex: 'operator', width: 110 },
  ]

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col span={8}>
          <Card title="当前余额">
            <Typography.Title level={2} type={wallet.blocked ? 'danger' : 'success'} style={{ margin: 0 }}>
              ¥{fmtMoney(wallet.balance, 4)}
            </Typography.Title>
            {wallet.blocked && (
              <Alert type="error" showIcon style={{ marginTop: 12 }} title={wallet.blocked_reason || '服务已暂停，请联系管理员充值'} />
            )}
          </Card>
        </Col>
        <Col span={16}>
          <Card
            title="月度账单"
            extra={
              <Select value={month} onChange={setMonth} style={{ width: 140 }} options={monthOptions.map((m) => ({ value: m, label: m }))} />
            }
          >
            <Descriptions size="small" column={4} border>
              <Descriptions.Item label="总费用">¥{fmtMoney(summary.total?.cost, 4)}</Descriptions.Item>
              <Descriptions.Item label="输入 tokens">{fmtTokens(summary.total?.input_tokens)}</Descriptions.Item>
              <Descriptions.Item label="输出 tokens">{fmtTokens(summary.total?.output_tokens)}</Descriptions.Item>
              <Descriptions.Item label="搜索次数">{summary.total?.web_search_requests || 0}</Descriptions.Item>
            </Descriptions>
            <Table
              size="small"
              rowKey="model_id"
              style={{ marginTop: 12 }}
              pagination={false}
              dataSource={summary.by_model || []}
              columns={[
                { title: '模型', dataIndex: 'model_id' },
                { title: '费用(¥)', render: (_, r) => fmtMoney(r.cost, 4) },
                { title: '输入', render: (_, r) => fmtTokens(r.input_tokens) },
                { title: '输出', render: (_, r) => fmtTokens(r.output_tokens) },
                { title: '计量次数', dataIndex: 'records' },
              ]}
            />
          </Card>
        </Col>
      </Row>
      <Card title="钱包流水" style={{ marginTop: 16 }}>
        <Select
          placeholder="类型"
          style={{ width: 120, marginBottom: 8 }}
          value={txType || undefined}
          onChange={(v) => setTxType(v || '')}
          allowClear
          options={[
            { value: 'recharge', label: '充值' },
            { value: 'adjust', label: '调整' },
            { value: 'consumption', label: '消费' },
          ]}
        />
        <Table
          rowKey="id"
          size="small"
          columns={columns}
          dataSource={tx.items}
          pagination={{ current: tx.page, pageSize: 20, total: tx.total, onChange: loadTx, showTotal: (t) => `共 ${t} 条` }}
        />
      </Card>
    </div>
  )
}
