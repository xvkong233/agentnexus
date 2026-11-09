import { useEffect, useState } from 'react'
import { Alert, Button, Card, Input, Space, Typography, message } from 'antd'
import http from '../../api/client'

export default function Settings() {
  const [url, setUrl] = useState('')
  const [secret, setSecret] = useState('')

  const load = async () => {
    const r = await http.get('/api/portal/tool-webhook')
    setUrl(r.url)
    setSecret(r.secret)
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <Card>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        title="配置租户级「自定义工具执行回调」。Agent 会话停在 requires_action 时，平台将 agent.custom_tool_use 事件以 HMAC-SHA256 签名 POST 到此 URL，并用响应内容自动回传工具结果，使渠道/定时任务等无人值守场景也能使用自定义工具。"
      />

      <Card type="inner" title="回调配置" style={{ maxWidth: 720 }}>
        <Typography.Paragraph>
          <Typography.Text type="secondary">回调 URL</Typography.Text>
        </Typography.Paragraph>
        <Input
          placeholder="https://your-app.example.com/tools/callback（留空停用）"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <Typography.Paragraph style={{ marginTop: 16 }}>
          <Typography.Text type="secondary">签名密钥</Typography.Text>
        </Typography.Paragraph>
        <Space.Compact style={{ width: '100%' }}>
          <Input value={secret} readOnly />
          <Button
            onClick={async () => {
              const r = await http.post('/api/portal/tool-webhook/rotate-secret')
              setSecret(r.secret)
              message.success('密钥已轮换，请同步更新你的服务端')
            }}
          >
            轮换
          </Button>
        </Space.Compact>
        <Button
          type="primary"
          style={{ marginTop: 16 }}
          onClick={async () => {
            const r = await http.put('/api/portal/tool-webhook', { url })
            setSecret(r.secret)
            message.success('已保存')
          }}
        >
          保存配置
        </Button>
      </Card>

      <Card type="inner" title="回调协议" style={{ maxWidth: 720, marginTop: 16 }}>
        <ul style={{ fontSize: 13, color: 'rgba(0,0,0,0.65)', lineHeight: 2, paddingLeft: 20 }}>
          <li>请求：POST JSON <code>{'{"session_id","upstream_session_id","tool_use_id","name","input"}'}</code></li>
          <li>请求头：<code>X-Timestamp</code>（Unix 秒）与 <code>X-Signature = HMAC-SHA256(secret, "{'{timestamp}.'} + 原始请求体")</code> 十六进制</li>
          <li>期望响应：200 + JSON <code>{'{"is_error": false, "content": [{"type":"text","text":"工具结果"}]}'}</code></li>
          <li>非 200 或解析失败将回传 is_error 结果给 Agent（会话可继续）</li>
        </ul>
        <pre style={{ background: '#FAFAFA', padding: 12, borderRadius: 8, fontSize: 12, overflow: 'auto' }}>
{`# 校验签名示例（Python）
import hmac, hashlib

def verify(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    msg = timestamp.encode() + b"." + body
    expect = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expect, signature)`}
        </pre>
      </Card>
    </Card>
  )
}
