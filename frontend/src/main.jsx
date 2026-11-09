import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider, App as AntdApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import { themeConfig } from './theme'
import './styles.css'
import App from './App'
import { setMessageApi } from './api/message'

dayjs.locale('zh-cn')

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={themeConfig}>
      <AntdApp>
        <Bridge />
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>,
)

/** 把 App.useApp 的 message 桥接给 axios 拦截器等非组件环境 */
function Bridge() {
  const { message, notification, modal } = AntdApp.useApp()
  setMessageApi({ message, notification, modal })
  return null
}
