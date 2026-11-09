import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

/** ECharts 轻封装：option 变更自动重绘，容器尺寸自适应 */
export default function VChart({ option, height = 300 }) {
  const el = useRef(null)
  const chart = useRef(null)

  useEffect(() => {
    chart.current = echarts.init(el.current)
    const onResize = () => chart.current?.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.current?.dispose()
    }
  }, [])

  useEffect(() => {
    chart.current?.setOption(option, true)
  }, [option])

  return <div ref={el} style={{ height, width: '100%' }} />
}
