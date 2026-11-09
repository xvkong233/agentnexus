import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Col, Row, Statistic, Table, Tag } from 'antd'
import { useNavigate } from 'react-router-dom'
import http, { fmtMoney, fmtTokens, SOURCE_LABEL, STATUS_LABEL } from '../../api/client'
import VChart from '../../components/VChart'

export default function Dashboard() {
  const navigate = useNavigate()
  const [d, setD] = useState({})

  useEffect(() => {
    http.get('/api/portal/dashboard').then(setD)
  }, [])

  const chartOption = useMemo(
    () => ({
      tooltip: { trigger: 'axis' },
      legend: { data: ['消费(¥)', 'Tokens'], top: 0 },
      grid: { left: 48, right: 48, top: 32, bottom: 24 },
      xAxis: { type: 'category', data: (d.series || []).map((s) => s.date.slice(5)) },
      yAxis: [
        { type: 'value', name: '¥' },
        { type: 'value', name: 'tokens' },
      ],
      series: [
        { name: '消费(¥)', type: 'line', smooth: true, data: (d.series || []).map((s) => s.cost) },
        { name: 'Tokens', type: 'bar', yAxisIndex: 1, data: (d.series || []).map((s) => s.tokens) },
      ],
    }),
    [d.series],
  )

  return (
    <div>
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card className="kpi-card">
            <Statistic
              title="钱包余额"
              prefix="¥"
              value={d.wallet?.balance || 0}
              precision={2}
              styles={{ content: { color: d.wallet?.blocked ? '#FF4D4F' : '#52C41A' } }}
            />
            <Button size="small" style={{ marginTop: 8 }} onClick={() => navigate('/portal/wallet')}>
              查看账单
            </Button>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="kpi-card">
            <Statistic title="本月消费" prefix="¥" value={d.month_cost || 0} precision={2} />
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
            <Statistic title="Agent / 运行中会话" value={d.agent_count || 0} suffix={`/ ${d.running_sessions || 0}`} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={14}>
          <Card title="近 14 天用量" variant="borderless">
            <VChart option={chartOption} height={280} />
          </Card>
        </Col>
        <Col span={10}>
          <Card
            title="最近会话"
            variant="borderless"
            extra={<Button size="small" type="primary" onClick={() => navigate('/portal/sessions')}>全部会话</Button>}
          >
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={d.recent_sessions || []}
              columns={[
                {
                  title: '标题',
                  render: (_, r) => (
                    <a onClick={() => navigate(`/portal/chat/${r.id}`)}>{r.title || '(未命名)'}</a>
                  ),
                },
                {
                  title: '状态', width: 80,
                  render: (_, r) => (
                    <Tag color={r.status === 'running' ? 'success' : 'default'}>
                      {STATUS_LABEL[r.status] || r.status}
                    </Tag>
                  ),
                },
                { title: '来源', dataIndex: 'source', width: 80, render: (s) => SOURCE_LABEL[s] || s },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
