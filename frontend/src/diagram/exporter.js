// 导出整张图为 PNG / SVG：按全部节点的范围渲染视口，不受当前缩放影响（html-to-image，MIT）
import { toPng, toSvg } from 'html-to-image'
import { getRectOfNodes, getTransformForBounds } from '@vue-flow/core'

export async function renderDiagram(root, nodes, { format = 'png', scale = 2, maxWidth = 4096, padding = 48 } = {}) {
  const viewport = root.querySelector('.vue-flow__transformationpane') || root.querySelector('.vue-flow__viewport') // 视图变换在这一层
  if (!viewport || !nodes.length) throw new Error('画布是空的')
  const r = getRectOfNodes(nodes)
  const top = nodes.some((n) => n.type === 'group') ? 30 : 0 // 分组框的标题画在框外上方
  const b = { x: r.x, y: r.y - top, width: r.width, height: r.height + top }
  const width = Math.min(maxWidth, Math.ceil(b.width + padding * 2))
  const height = Math.ceil((b.height + padding * 2) * (width / (b.width + padding * 2)))
  const t = getTransformForBounds(b, width, height, 0.05, 2, 0)
  const zoom = Math.min(t.zoom ?? t[2], 2)
  const x = (width - b.width * zoom) / 2 - b.x * zoom
  const y = (height - b.height * zoom) / 2 - b.y * zoom
  const bg = getComputedStyle(root).getPropertyValue('--sunken').trim() || '#101018'
  const opts = {
    width, height, backgroundColor: bg, pixelRatio: format === 'png' ? scale : 1,
    style: { width: `${width}px`, height: `${height}px`, transform: `translate(${x}px, ${y}px) scale(${zoom})`, transformOrigin: '0 0' },
    filter: (el) => !(el.classList && (el.classList.contains('vue-flow__resize-control') || el.classList.contains('dn-h'))),
  }
  // html-to-image 不会带上样式表给 SVG 元素的 fill / stroke（会变成黑色），导出前把算好的值临时写到行内
  const PROPS = ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-opacity', 'fill-opacity', 'font-size', 'font-family']
  const saved = []
  for (const el of viewport.querySelectorAll('svg *')) {
    const cs = getComputedStyle(el)
    saved.push([el, el.getAttribute('style')])
    for (const p of PROPS) el.style.setProperty(p, cs.getPropertyValue(p))
  }
  try {
    return await (format === 'svg' ? toSvg(viewport, opts) : toPng(viewport, opts))
  } finally {
    for (const [el, st] of saved) st == null ? el.removeAttribute('style') : el.setAttribute('style', st)
  }
}

export function download(dataUrl, name) {
  const a = document.createElement('a')
  a.href = dataUrl; a.download = name
  document.body.appendChild(a); a.click(); a.remove()
}

export async function dataUrlToBlob(url) { return (await fetch(url)).blob() }
