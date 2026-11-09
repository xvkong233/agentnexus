import React from 'react'
import { Alert, Descriptions, Statistic } from 'antd'
import { XCard } from '@ant-design/x-card'

/** 简易错误边界：XCard 渲染异常时回退到 antd Descriptions */
class XCardBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (this.state.failed) return this.props.fallback
    return this.props.children
  }
}

/**
 * 会话用量卡片：以 A2UI v0.9 命令流驱动 XCard 动态渲染，
 * Catalog 组件映射到 antd 组件（体现 Agent → UI 的协议化渲染）。
 */
export default function UsageCard({ usage, model, cost }) {
  const surfaceId = `usage-${usage.seq || Math.random().toString(36).slice(2, 8)}`

  const components = {
    Card: ({ children }) => (
      <div
        style={{
          background: '#FAFAFA',
          border: '1px solid #F0F0F0',
          borderRadius: 8,
          padding: 12,
          minWidth: 320,
        }}
      >
        {children}
      </div>
    ),
    Title: ({ text }) => (
      <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13, color: 'rgba(0,0,0,0.88)' }}>{text}</div>
    ),
    Row: ({ children }) => (
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>{children}</div>
    ),
    Metric: ({ label, value }) => (
      <Statistic title={<span style={{ fontSize: 12 }}>{label}</span>} value={value} styles={{ content: { fontSize: 16 } }} />
    ),
    Foot: ({ text }) => (
      <div style={{ marginTop: 8, color: 'rgba(0,0,0,0.45)', fontSize: 12 }}>{text}</div>
    ),
  }

  const commands = [
    { version: 'v0.9', createSurface: { surfaceId, catalogId: 'local://platform-usage-catalog' } },
    {
      version: 'v0.9',
      updateComponents: {
        surfaceId,
        components: [
          { id: 'root', component: 'Card', children: ['t', 'row', 'foot'] },
          { id: 't', component: 'Title', text: '本轮用量' },
          {
            id: 'row',
            component: 'Row',
            children: ['m1', 'm2', 'm3', 'm4'],
          },
          { id: 'm1', component: 'Metric', label: '输入 tokens', value: usage.input_tokens || 0 },
          { id: 'm2', component: 'Metric', label: '输出 tokens', value: usage.output_tokens || 0 },
          { id: 'm3', component: 'Metric', label: '缓存读 tokens', value: usage.cache_read_input_tokens || 0 },
          { id: 'm4', component: 'Metric', label: '搜索次数', value: usage.web_search_requests || 0 },
          {
            id: 'foot',
            component: 'Foot',
            text: `模型 ${model || '-'}${cost != null ? ` · 本轮费用 ¥${cost.toFixed(6)}` : ''}`,
          },
        ],
      },
    },
  ]

  return (
    <XCardBoundary
      fallback={
        <Descriptions size="small" column={2} style={{ maxWidth: 420 }}>
          <Descriptions.Item label="输入 tokens">{usage.input_tokens || 0}</Descriptions.Item>
          <Descriptions.Item label="输出 tokens">{usage.output_tokens || 0}</Descriptions.Item>
          <Descriptions.Item label="缓存读 tokens">{usage.cache_read_input_tokens || 0}</Descriptions.Item>
          <Descriptions.Item label="搜索次数">{usage.web_search_requests || 0}</Descriptions.Item>
        </Descriptions>
      }
    >
      <XCard.Box commands={commands} components={components} onAction={() => {}}>
        <XCard.Card id={surfaceId} />
      </XCard.Box>
    </XCardBoundary>
  )
}

export { XCardBoundary }

/* 供 Sender 上方提示使用 */
export function BlockedAlert({ reason }) {
  return <Alert type="error" showIcon title={reason || '余额不足，服务已暂停，请前往钱包充值'} />
}
