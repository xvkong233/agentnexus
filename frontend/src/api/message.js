// message API 桥：供 axios 拦截器等非组件环境使用（antd 官方推荐经由 App 上下文）
let api = { message: null, notification: null, modal: null }

export function setMessageApi(next) {
  api = next
}

export function getMsg() {
  return api
}
