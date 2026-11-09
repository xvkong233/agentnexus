import axios from 'axios'
import { getMsg } from './message'

const http = axios.create({ baseURL: '', timeout: 60000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (resp) => resp.data,
  (error) => {
    const status = error.response?.status
    const data = error.response?.data
    const message = data?.message || error.message || '请求失败'
    if (status === 401 && !location.pathname.startsWith('/login')) {
      localStorage.removeItem('token')
      localStorage.removeItem('role')
      location.href = '/login'
    }
    getMsg().message?.error(`${message}${data?.code === 'insufficient_balance' ? '（余额不足）' : ''}`)
    return Promise.reject(error)
  },
)

export default http

export function fmtMoney(v, digits = 4) {
  const n = Number(v || 0)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function fmtTokens(n) {
  n = Number(n || 0)
  if (n >= 1e8) return (n / 1e8).toFixed(2) + ' 亿'
  if (n >= 1e4) return (n / 1e4).toFixed(2) + ' 万'
  return String(n)
}

export function fmtTime(s) {
  if (!s) return '-'
  return String(s).replace('T', ' ').replace('Z', '').slice(0, 19)
}

export const SOURCE_LABEL = {
  web_chat: '网页聊天',
  open_api: '开放API',
  deployment: '定时任务',
  channel: '聊天渠道',
  imported: '同步导入',
}

export const STATUS_LABEL = {
  idle: '空闲',
  running: '运行中',
  rescheduling: '调度中',
  terminated: '已终止',
}
