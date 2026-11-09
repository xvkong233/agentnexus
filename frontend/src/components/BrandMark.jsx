/** 品牌标：渐变圆角方块 + N 字标，替代 emoji，适配 Sider / 登录页两种底色 */
export function BrandMark({ size = 30, dark = false }) {
  return (
    <span
      aria-hidden
      style={{
        width: size,
        height: size,
        borderRadius: Math.round(size * 0.28),
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: dark
          ? 'linear-gradient(135deg, #4096FF 0%, #2F54EB 100%)'
          : 'linear-gradient(135deg, #1677FF 0%, #2F54EB 100%)',
        color: '#fff',
        fontWeight: 700,
        fontSize: Math.round(size * 0.52),
        fontFamily: "'Segoe UI', 'PingFang SC', sans-serif",
        letterSpacing: '-0.5px',
        boxShadow: dark ? '0 2px 8px rgba(22,119,255,0.4)' : '0 3px 10px rgba(22,119,255,0.35)',
        flexShrink: 0,
        userSelect: 'none',
        transition: 'transform 0.2s cubic-bezier(0.34, 0.69, 0.63, 0.9)',
      }}
    >
      N
    </span>
  )
}
