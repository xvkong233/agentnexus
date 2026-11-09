import { useEffect, useMemo, useState } from 'react'
import { Card, Col, Row, Statistic, Table, Typography } from 'antd'
import http, { fmtMoney, fmtTokens } from '../../api/client'
import VChart from '../../components/VChart'

export default function Dashboard() {
  const [d, setD] = useState({})

  useEffect(() => {
    http.get('/api/admin/dashboard').then(setD)
  }, [])

  const costOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 16, top: 24, bottom: 24 },
      xAxis: { type: 'category', data: (d.series || []).map((s) => s.date.slice(5)) },
      yAxis: { type: 'value' },
      series: [
        { type: 'line', smooth: true, areaStyle: { opacity: 0.15 }, data: (d.series || []).map((s) => s.cost) },
      ],
    }),
    [d.series],
  )

  const tokenOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis' },
      legend: { data: ['输入', '输出'], top: 0 },
      grid: { left: 48, right: 16, top: 32, bottom: 24 },
      xAxis: { type: 'category', data: (d.series || []).map((s) => s.date.slice(5)) },
      yAxis: { type: 'value' },
      series: [
        { name: '输入', type: 'bar', stack: 't', data: (d.series || []).map((s) => s.input_tokens) },
        { name: '输出', type: 'bar', stack: 't', data: (d.series || []).map((s) => s.output_tokens) },
      ],
    }),
    [d.series],
  )

  const columns = [
    { title: '模型', dataIndex: 'model_id' },
    { title: '消费(¥)', render: (_, r) => fmtMoney(r.cost) },
    { title: '输入', render: (_, r) => fmtTokens(r.input_tokens) },
    { title: '输出', render: (_, r) => fmtTokens(r.output_tokens) },
  ]

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card className="kpi-card">
            <Statistic title="本月消费" prefix="¥" value={d.month_cost || 0} precision={2} />
          </Card>
        </Col>
        <Col span={6}>
          <Card className="kpi-card">
            <Statistic title="今日消费" prefix="¥" value={d.today_cost || 0} precision={2} />
          </Card>
        </Col>
        <Col span={6}>
          <Card className="kpi-card">
            <Statistic
              title="本月 Tokens"
              value={fmtTokens((d.month_input_tokens || 0) + (d.month_output_tokens || 0))}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card className="kpi-card">
            <Statistic title="租户 / 运行会话" value={d.tenant_count || 0} suffix={`/ ${d.running_sessions || 0}`} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="近 14 天消费趋势（¥）" variant="borderless">
            <VChart option={costOption} height={300} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="近 14 天 Token 用量" variant="borderless">
            <VChart option={tokenOption} height={300} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card title="本月模型分布（消费 ¥）" variant="borderless">
            <Table
              size="small"
              rowKey="model_id"
              columns={columns}
              dataSource={d.model_breakdown || []}
              pagination={false}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="累计总消费" variant="borderless">
            <Statistic prefix="¥" value={d.total_cost || 0} precision={2} />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              自平台上线以来的全部计量消费
            </Typography.Text>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
