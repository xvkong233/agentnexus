import { XStream } from '@ant-design/x-sdk'

/**
 * 基于 XStream（@ant-design/x-sdk）的 SSE 读取。
 * 平台后端对上游 SSE 做流式转发（含 Authorization 头），前端用 fetch 拿到
 * ReadableStream 后交给 XStream 解析（默认 sseTransformStream）。
 *
 * onEvent({ event, data }) — data 为解析后的 JSON 对象。
 * 返回 { close() }。
 */
export async function sseConnect(url, { onEvent, onOpen, onError } = {}) {
  const token = localStorage.getItem('token')
  const controller = new AbortController()
  let closed = false

  ;(async () => {
    try {
      const resp = await fetch(url, {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        console.warn('[sse] connect failed', resp.status)
        onError?.(`SSE 连接失败: HTTP ${resp.status}`)
        return
      }
      console.log('[sse] connected', url)
      onOpen?.()
      for await (const chunk of XStream({ readableStream: resp.body })) {
        if (closed) return
        // XStream 按 SSE 解析：{ event?: string, data: string }；过滤 ping 注释帧
        if (!chunk || chunk.data == null) continue
        let data = chunk.data
        if (typeof data === 'string') {
          try {
            data = JSON.parse(data)
          } catch {
            /* 非 JSON 跳过 */
          }
        }
        if (data && typeof data === 'object') {
          console.log('[sse] frame', data.type || chunk.event)
          onEvent({ event: chunk.event, data })
        }
      }
    } catch (err) {
      if (!closed && err.name !== 'AbortError') { console.warn('[sse] error', err); onError?.(String(err)) }
    }
  })()

  return {
    close() {
      closed = true
      controller.abort()
    },
  }
}
