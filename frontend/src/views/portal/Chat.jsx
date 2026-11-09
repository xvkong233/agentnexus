import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert, Avatar, Button, Card, Drawer, Flex, Space, Spin, Tag, Typography, message,
} from 'antd'
import {
  ApiOutlined,
  ArrowLeftOutlined,
  BulbOutlined,
  DownloadOutlined,
  FileTextOutlined,
  RobotOutlined,
  ToolOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import { Bubble, Sender } from '@ant-design/x'
import { XMarkdown } from '@ant-design/x-markdown'
import http, { STATUS_LABEL } from '../../api/client'
import { sseConnect } from '../../api/sse'
import UsageCard from '../../components/UsageCard'

const STOP_REASON = {
  end_turn: '本轮结束',
  requires_action: '等待工具结果/审批',
  retries_exhausted: '重试耗尽',
  refusal: '模型拒答',
}

let seq = 0
const nextKey = () => `m-${++seq}`

export default function Chat() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [session, setSession] = useState({})
  const [items, setItems] = useState([]) // Bubble.List items
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [blocked, setBlocked] = useState(false)
  const [filesOpen, setFilesOpen] = useState(false)
  const [files, setFiles] = useState([])
  const streamRef = useRef(null)
  const seenIds = useRef(new Set())
  const usageSeq = useRef(0)

  /* ---------- 列表操作 ---------- */
  const push = useCallback((item) => {
    setItems((prev) => [...prev, { key: nextKey(), ...item }])
  }, [])

  const patchLastNote = useCallback((text, tagType = 'default') => {
    setItems((prev) => {
      const last = prev[prev.length - 1]
      if (last && last.role === 'note') {
        return [...prev.slice(0, -1), { ...last, content: noteNode(text, tagType) }]
      }
      return [...prev, { key: nextKey(), role: 'note', content: noteNode(text, tagType) }]
    })
  }, [])

  const noteNode = (text, tagType) => (
    <div style={{ textAlign: 'center', margin: '4px 0' }}>
      <Tag color={tagType} variant="filled">{text}</Tag>
    </div>
  )

  /* ---------- 事件 → 气泡 ---------- */
  const applyEvent = useCallback(
    (ev) => {
      if (ev.id) {
        if (seenIds.current.has(ev.id)) return
        seenIds.current.add(ev.id)
      }
      const t = ev.type
      const textOf = (content) =>
        Array.isArray(content)
          ? content.filter((b) => b.type === 'text').map((b) => b.text).join('\n')
          : String(content || '')

      if (t === 'user.message') {
        push({ role: 'user', content: textOf(ev.content) })
      } else if (t === 'agent.thinking') {
        const txt = textOf(ev.content)
        if (txt) push({ role: 'note', content: <ThinkingCard text={txt} /> })
      } else if (t === 'agent.message') {
        const text = textOf(ev.content)
        setItems((prev) => {
          const last = prev[prev.length - 1]
          // 替换流式气泡
          if (last && last.role === 'ai' && last.streaming) {
            return [...prev.slice(0, -1), { ...last, streaming: false, content: <AiText text={text} /> }]
          }
          return [...prev, { key: nextKey(), role: 'ai', content: <AiText text={text} /> }]
        })
      } else if (t === 'agent.tool_use' || t === 'agent.mcp_tool_use') {
        const name = t === 'agent.mcp_tool_use' ? `[MCP:${ev.mcp_server_name}] ${ev.name}` : ev.name
        push({ role: 'tool', content: <ToolCard name={name} input={ev.input} /> })
      } else if (t === 'agent.tool_result') {
        setItems((prev) => {
          const idx = [...prev].reverse().findIndex((m) => m.role === 'tool' && m.toolName === ev.name && !m.result)
          if (idx === -1) return prev
          const realIdx = prev.length - 1 - idx
          const target = prev[realIdx]
          const out = Array.isArray(ev.output) ? ev.output.map((b) => b.text || '').join('\n') : ''
          return prev.map((m, i) =>
            i === realIdx
              ? {
                  ...m,
                  result: String(out).slice(0, 2000),
                  isError: !!ev.is_error,
                  content: <ToolCard name={m.toolName} input={m.toolInput} output={String(out).slice(0, 2000)} isError={!!ev.is_error} />,
                }
              : m,
          )
        })
      } else if (t === 'agent.custom_tool_use') {
        push({ role: 'tool', content: <CustomToolCard name={ev.name} input={ev.input} /> })
      } else if (t === 'session.status_running') {
        setBusy(true)
        setSession((s) => ({ ...s, status: 'running' }))
        patchLastNote('Agent 开始执行', 'processing')
      } else if (t === 'session.status_idle') {
        setBusy(false)
        setSession((s) => ({ ...s, status: 'idle' }))
        patchLastNote(`已空闲（${STOP_REASON[ev.stop_reason?.type] || ev.stop_reason?.type || '-'}）`, 'default')
      } else if (t === 'session.error') {
        patchLastNote(`执行出错：${ev.error?.message || ''}（${ev.error?.retry_status?.type || ''}）`, 'error')
      } else if (t === 'session.usage') {
        usageSeq.current += 1
        const u = { ...ev.usage, seq: usageSeq.current }
        const model = typeof (ev.usage?.model || session.model_id) === 'string' ? session.model_id : ''
        push({ role: 'usage', content: <UsageCard usage={u} model={model} /> })
      }
    },
    [push, patchLastNote, session.model_id],
  )

  /* ---------- 流式 delta → 流式气泡 ---------- */
  const handleDelta = useCallback((data) => {
    if (data.type === 'event_start' && data.event?.type === 'agent.message') {
      setItems((prev) => {
        const last = prev[prev.length - 1]
        if (last && last.role === 'ai' && last.streaming) return prev
        return [...prev, { key: nextKey(), role: 'ai', streaming: true, content: <AiText text="" /> }]
      })
    } else if (data.type === 'event_delta' && data.content_delta) {
      const delta = typeof data.content_delta === 'string' ? data.content_delta : data.content_delta.text || ''
      setItems((prev) => {
        const last = prev[prev.length - 1]
        if (last && last.role === 'ai' && last.streaming) {
          const acc = (last._acc || '') + delta
          return [...prev.slice(0, -1), { ...last, _acc: acc, content: <AiText text={acc} /> }]
        }
        return prev
      })
    }
  }, [])

  /* ---------- 数据加载 ---------- */
  const loadSession = useCallback(async () => {
    const s = await http.get(`/api/portal/sessions/${id}`)
    setSession(s)
  }, [id])

  const loadHistory = useCallback(async () => {
    const r = await http.get(`/api/portal/sessions/${id}/events`, { params: { limit: 100, order: 'desc' } })
    const events = (r.data || []).slice().reverse()
    for (const ev of events) applyEvent(ev)
    try {
      const s = await http.get(`/api/portal/sessions/${id}`)
      setSession(s)
      setBusy(s.status === 'running')
    } catch {
      /* ignore */
    }
  }, [id, applyEvent])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const me = await http.get('/api/portal/me')
        setBlocked(me.wallet?.blocked)
      } catch {
        /* ignore */
      }
      await loadSession()
      if (cancelled) return
      // 官方建议顺序：先连 SSE（live-only），再补拉历史并按 id 去重，避免空窗丢事件
      streamRef.current = await sseConnect(`/api/portal/sessions/${id}/events/stream?deltas=true`, {
        onEvent: ({ data }) => {
          if (!data || typeof data !== 'object') return
          if (data.type === 'event_start' || data.type === 'event_delta') handleDelta(data)
          else applyEvent(data)
        },
        onError: () => {},
      })
      if (cancelled) return
      await loadHistory()
    })()
    return () => {
      cancelled = true
      streamRef.current?.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  /* ---------- 发送 / 打断 ---------- */
  const send = async (text) => {
    if (!text.trim() || busy) return
    setInput('')
    try {
      await http.post(`/api/portal/sessions/${id}/events`, {
        events: [{ type: 'user.message', content: [{ type: 'text', text }] }],
      })
      push({ role: 'user', content: text })
      setBusy(true)
    } catch {
      /* 拦截器已提示 */
    }
  }

  const interrupt = async () => {
    await http.post(`/api/portal/sessions/${id}/events`, { events: [{ type: 'user.interrupt' }] })
    message.info('已发送打断指令')
  }

  const loadFiles = useCallback(async () => {
    if (!filesOpen) return
    const r = await http.get(`/api/portal/sessions/${id}/files`)
    setFiles(r.data || [])
  }, [filesOpen, id])

  useEffect(() => {
    loadFiles()
    const timer = setInterval(loadFiles, 15000)
    return () => clearInterval(timer)
  }, [loadFiles])

  const download = async (f) => {
    const token = localStorage.getItem('token')
    const resp = await fetch(`/api/portal/files/${f.id}/content`, { headers: { Authorization: `Bearer ${token}` } })
    const blob = await resp.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = f.filename
    a.click()
  }

  /* ---------- Bubble.List roles ---------- */
  const roles = useMemo(
    () => ({
      user: { placement: 'end', variant: 'shadow', avatar: <Avatar icon={<UserOutlined />} style={{ background: '#1677FF' }} /> },
      ai: { placement: 'start', variant: 'outlined', avatar: <Avatar icon={<RobotOutlined />} style={{ background: '#52C41A' }} /> },
      note: { placement: 'start', variant: 'borderless' },
      tool: { placement: 'start', variant: 'borderless' },
      usage: { placement: 'start', variant: 'borderless' },
    }),
    [],
  )

  const statusColor = { running: 'processing', idle: 'default', rescheduling: 'warning', terminated: 'error' }[session.status] || 'default'

  return (
    <Flex vertical style={{ height: 'calc(100vh - 116px)' }}>
      <Card styles={{ body: { display: 'flex', flexDirection: 'column', height: '100%', padding: 16 } }}>
        {/* 头部 */}
        <Flex align="center" gap={8} style={{ paddingBottom: 12, borderBottom: '1px solid #f0f0f0' }}>
          <Button size="small" icon={<ArrowLeftOutlined />} onClick={() => navigate('/portal/sessions')}>
            返回
          </Button>
          <Typography.Text strong>{session.title || '(未命名会话)'}</Typography.Text>
          <Tag color={statusColor} variant="filled">{STATUS_LABEL[session.status] || '-'}</Tag>
          {session.model_id && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>{session.model_id}</Typography.Text>
          )}
          <Flex flex={1} justify="flex-end">
            <Button size="small" icon={<FileTextOutlined />} onClick={() => setFilesOpen(true)}>
              产物文件
            </Button>
          </Flex>
        </Flex>

        {blocked && (
          <Alert
            type="error"
            showIcon
            style={{ marginTop: 8 }}
            title="余额不足，服务已暂停，请前往「钱包与账单」充值后继续使用"
          />
        )}

        {/* 消息列表 */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 4px' }}>
          {items.length === 0 && (
            <div style={{ textAlign: 'center', padding: 40, color: 'rgba(0,0,0,0.45)' }}>
              <Spin spinning={busy} />
              <div style={{ marginTop: 8 }}>发送第一条消息开始对话</div>
            </div>
          )}
          <Bubble.List
            items={items}
            roles={roles}
            autoScroll
            style={{ height: items.length ? '100%' : 0 }}
          />
        </div>

        {/* 输入区 */}
        <Sender
          placeholder={blocked ? '余额不足，服务已暂停' : busy ? 'Agent 执行中…可点击取消按钮打断' : '输入消息，Enter 发送 / Shift+Enter 换行'}
          value={input}
          onChange={setInput}
          onSubmit={send}
          loading={busy}
          onCancel={interrupt}
          disabled={blocked}
          submitType="enter"
        />
      </Card>

      {/* 产物文件抽屉 */}
      <Drawer
        title="会话产物文件"
        open={filesOpen}
        onClose={() => setFilesOpen(false)}
        size="default"
      >
        {files.length === 0 && <Typography.Text type="secondary">暂无产物。Agent 写入 /mnt/session/outputs 的文件会出现在这里。</Typography.Text>}
        <Space direction="vertical" style={{ width: '100%' }}>
          {files.map((f) => (
            <Flex key={f.id} align="center" gap={8} style={{ borderBottom: '1px solid #f0f0f0', padding: '6px 0' }}>
              <FileTextOutlined />
              <Typography.Text ellipsis style={{ flex: 1 }}>{f.filename}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {(f.size_bytes / 1024).toFixed(1)} KB
              </Typography.Text>
              {f.downloadable && (
                <Button size="small" icon={<DownloadOutlined />} onClick={() => download(f)}>下载</Button>
              )}
            </Flex>
          ))}
        </Space>
      </Drawer>
    </Flex>
  )
}

/* ---------- 内容渲染组件 ---------- */

function AiText({ text }) {
  if (!text) return <Spin size="small" />
  return <XMarkdown content={text} style={{ fontSize: 14, lineHeight: 1.7 }} />
}

function ThinkingCard({ text }) {
  return (
    <div
      style={{
        maxWidth: 560,
        padding: '8px 12px',
        background: '#FAFAFA',
        borderLeft: '3px solid #D9D9D9',
        color: 'rgba(0,0,0,0.45)',
        fontSize: 12,
        whiteSpace: 'pre-wrap',
      }}
    >
      <BulbOutlined style={{ color: 'rgba(0,0,0,0.35)', marginRight: 6 }} />{text}
    </div>
  )
}

function ToolCard({ name, input, output, isError }) {
  return (
    <div
      style={{
        maxWidth: 560,
        padding: '8px 12px',
        background: isError ? '#FFF2F0' : '#F6FFED',
        border: `1px solid ${isError ? '#FFCCC7' : '#B7EB8F'}`,
        borderRadius: 8,
        fontSize: 13,
      }}
    >
      <ToolOutlined style={{ color: isError ? '#FF4D4F' : '#52C41A', marginRight: 6 }} /><b>{name}</b>{isError && <Tag color="error" style={{ marginLeft: 8 }}>失败</Tag>}
      {input != null && (
        <pre style={{ margin: '6px 0 0', background: '#fff', padding: 6, borderRadius: 4, fontSize: 12, maxHeight: 180, overflow: 'auto' }}>
          {typeof input === 'string' ? input : JSON.stringify(input, null, 2)}
        </pre>
      )}
      {output && <div style={{ marginTop: 6, color: 'rgba(0,0,0,0.65)', whiteSpace: 'pre-wrap', maxHeight: 180, overflow: 'auto' }}>{output}</div>}
    </div>
  )
}

function CustomToolCard({ name, input }) {
  return (
    <div
      style={{
        maxWidth: 560,
        padding: '8px 12px',
        background: '#FFFBE6',
        border: '1px solid #FFE58F',
        borderRadius: 8,
        fontSize: 13,
      }}
    >
      <ApiOutlined style={{ color: '#FAAD14', marginRight: 6 }} />自定义工具 <b>{name}</b> 等待执行
      <pre style={{ margin: '6px 0 0', background: '#fff', padding: 6, borderRadius: 4, fontSize: 12 }}>
        {typeof input === 'string' ? input : JSON.stringify(input, null, 2)}
      </pre>
      <div style={{ color: 'rgba(0,0,0,0.45)', fontSize: 12, marginTop: 4 }}>
        平台将转发到租户工具回调；若未配置回调，请在「工具回调设置」中配置。
      </div>
    </div>
  )
}
