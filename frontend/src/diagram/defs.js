// 图表画布的共享定义：形状、配色、节点面板
export const COLORS = [
  ['#9a6ad0', '雾紫'], ['#5b9cf0', '天蓝'], ['#23d2e2', '青'], ['#4fd1a5', '薄荷'],
  ['#f2c26b', '琥珀'], ['#f9515c', '珊瑚'], ['#8a8ca3', '石墨'],
]
export const SHAPES = [
  ['rect', '处理'], ['pill', '开始 / 结束'], ['diamond', '判断'], ['parallelogram', '输入 / 输出'],
  ['document', '文档'], ['cylinder', '数据'], ['hexagon', '准备'], ['circle', '连接点'],
]
export const KINDS = { flowchart: '流程图', workflow: '节点工作流', mindmap: '思维导图', other: '其他' }
export const EDGE_TYPES = [['smoothstep', '折线'], ['default', '曲线'], ['straight', '直线'], ['step', '直角']]

const size = (w, h) => ({ width: w, height: h })
const SIZE = { rect: size(168, 64), pill: size(152, 52), diamond: size(176, 100), parallelogram: size(180, 64), document: size(168, 80), cylinder: size(120, 90), hexagon: size(168, 64), circle: size(64, 64) }

// 面板里可拖出的节点
export const PALETTE = [
  { group: '流程图', items: SHAPES.map(([shape, label]) => ({ key: shape, label, node: { type: 'shape', data: { label, shape, color: shape === 'diamond' ? '#f2c26b' : shape === 'pill' ? '#4fd1a5' : '#9a6ad0' }, style: SIZE[shape] } })) },
  { group: '工作流', items: [
    { key: 'wf', label: '节点', node: { type: 'workflow', data: { label: '新节点', color: '#5b9cf0', inputs: [{ id: 'i0', label: '输入' }], outputs: [{ id: 'o0', label: '输出' }], fields: [] } } },
    { key: 'wf-src', label: '来源节点', node: { type: 'workflow', data: { label: '来源', color: '#4fd1a5', inputs: [], outputs: [{ id: 'o0', label: '输出' }], fields: [{ label: '参数', value: '' }] } } },
  ] },
  { group: '标注', items: [
    { key: 'note', label: '便签', node: { type: 'note', data: { label: '写点什么…', color: '#f2c26b' }, style: { width: 180, height: 110 } } },
    { key: 'group', label: '分组框', node: { type: 'group', data: { label: '分组', color: '#8a8ca3' }, style: { width: 360, height: 240 }, zIndex: -1 } },
  ] },
]

export const uid = (p = 'n') => p + Math.random().toString(36).slice(2, 8) + Date.now().toString(36).slice(-3)
export const tint = (c, pct = 16) => `color-mix(in srgb, ${c} ${pct}%, var(--panel))`

// Vue Flow 节点 → 存储结构（只保留需要的字段，尺寸取实际测得的大小）
export function serializeNode(n) {
  const out = { id: n.id, type: n.type, position: { x: Math.round(n.position.x), y: Math.round(n.position.y) }, data: { ...n.data } }
  const w = parseFloat(n.style?.width) || (n.type !== 'workflow' && n.dimensions?.width) || 0
  const h = parseFloat(n.style?.height) || (n.type !== 'workflow' && n.dimensions?.height) || 0
  if (n.type !== 'workflow' && w && h) out.style = { width: Math.round(w), height: Math.round(h) }
  if (n.zIndex) out.zIndex = n.zIndex
  return out
}
export function serializeEdge(e) {
  const out = { id: e.id, source: e.source, target: e.target, type: e.type || 'smoothstep' }
  for (const k of ['sourceHandle', 'targetHandle', 'label', 'animated']) if (e[k]) out[k] = e[k]
  if (e.data && Object.keys(e.data).length) out.data = { ...e.data }
  return out
}
// 存储结构 → Vue Flow：尺寸写成 px（Vue 的 style 绑定不会给数字补单位）
export function hydrateNode(n) {
  const out = { ...n, data: { ...n.data } }
  if (n.style) out.style = Object.fromEntries(Object.entries(n.style).map(([k, v]) => [k, typeof v === 'number' ? `${v}px` : v]))
  return out
}
// 存储结构 → Vue Flow：补上箭头、颜色、虚线
export function hydrateEdge(e, kind, edgeColor = '#8a8ca3') {
  const color = e.data?.color || null
  const arrow = e.data?.arrow ?? (kind !== 'workflow' && kind !== 'mindmap')
  return {
    ...e,
    markerEnd: arrow ? { type: 'arrowclosed', color: color || edgeColor, width: 18, height: 18 } : undefined,
    style: { stroke: color || undefined, strokeDasharray: e.data?.dashed ? '6 5' : undefined, strokeWidth: e.data?.width || (kind === 'workflow' ? 2.2 : 1.6) },
    class: e.data?.dashed ? 'dashed' : '',
  }
}
