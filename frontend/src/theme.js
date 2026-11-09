/**
 * 主题 token —— 遵循 Ant Design 设计体系（https://ant.design/design.md）：
 * - 品牌主色 #1677FF，语义色 success/warning/error/info
 * - 圆角：控件 6px / 表面 8px；基准字号 14px；仅 400/600 两档字重
 * - 4px 栅格；表面三层模型不硬编码颜色
 * - 组件级微调：SaaS 控制台常用的密度与表面质感
 */
export const themeConfig = {
  token: {
    colorPrimary: '#1677FF',
    colorInfo: '#1677FF',
    colorSuccess: '#52C41A',
    colorWarning: '#FAAD14',
    colorError: '#FF4D4F',
    borderRadius: 6,
    borderRadiusLG: 8,
    fontSize: 14,
    fontWeightStrong: 600,
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif",
    colorBgLayout: '#F5F7FA',
    // 中性透明文字（design.md：rgba 优于固定灰，避免破坏着色表面）
    colorText: 'rgba(0, 0, 0, 0.88)',
    colorTextSecondary: 'rgba(0, 0, 0, 0.65)',
    colorTextTertiary: 'rgba(0, 0, 0, 0.45)',
  },
  components: {
    Layout: {
      siderBg: '#101828',
      headerBg: '#ffffff',
      bodyBg: '#F5F7FA',
    },
    Menu: {
      darkItemBg: 'transparent',
      darkItemSelectedBg: 'rgba(22, 119, 255, 0.9)',
      darkItemHoverBg: 'rgba(255, 255, 255, 0.08)',
      itemBorderRadius: 6,
      itemMarginInline: 10,
      iconMarginInlineEnd: 12,
    },
    Card: {
      boxShadowTertiary:
        '0 1px 2px 0 rgba(16,24,40,0.04), 0 1px 6px -1px rgba(16,24,40,0.06)',
      paddingLG: 20,
    },
    Table: {
      headerBg: '#FAFAFB',
      headerColor: 'rgba(0, 0, 0, 0.88)',
      rowHoverBg: '#F0F7FF',
    },
    Button: {
      controlHeight: 32,
      fontWeight: 400,
      primaryShadow: '0 2px 4px rgba(22,119,255,0.25)',
    },
    Statistic: {
      contentFontSize: 26,
      titleFontSize: 13,
    },
    Modal: {
      titleFontSize: 16,
    },
  },
}
