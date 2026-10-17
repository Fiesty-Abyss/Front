<script setup>
// 图表画布编辑器：Vue Flow（MIT）。左侧节点面板、中间画布、右侧属性；自动保存、撤销重做、导出 PNG / SVG / JSON
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VueFlow, useVueFlow, ConnectionMode } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/node-resizer/dist/style.css'
import '../diagram/diagram.css'
import {
  ArrowLeft, Undo2, Redo2, Magnet, Map as MapIcon, ZoomIn, ZoomOut, Maximize, Download, Copy, Trash2, Plus, X,
  AlignStartVertical, AlignCenterVertical, AlignEndVertical, AlignStartHorizontal, AlignCenterHorizontal, AlignEndHorizontal,
  AlignHorizontalDistributeCenter, AlignVerticalDistributeCenter, BringToFront, SendToBack, Link2, Keyboard, Pin, PinOff,
} from 'lucide-vue-next'
import { api, Diagrams, Notes, Works } from '../api'
import { guard, toast } from '../toast'
import AssetPicker from '../components/AssetPicker.vue'
import TagPicker from '../components/TagPicker.vue'
import ShapeNode from '../diagram/ShapeNode.vue'
import NoteNode from '../diagram/NoteNode.vue'
import GroupNode from '../diagram/GroupNode.vue'
import WorkflowNode from '../diagram/WorkflowNode.vue'
import { COLORS, EDGE_TYPES, KINDS, PALETTE, SHAPES, hydrateEdge, hydrateNode, serializeEdge, serializeNode, tint, uid } from '../diagram/defs'
import { dataUrlToBlob, download, renderDiagram } from '../diagram/exporter'

const route = useRoute()
const router = useRouter()
const FLOW_ID = 'front-diagram'
const {
  onConnect, addEdges, addNodes, screenToFlowCoordinate, fitView, zoomIn, zoomOut, setViewport, viewport,
  getNodes, getEdges, getSelectedNodes, getSelectedEdges, updateNodeData, removeNodes, removeEdges, onMoveEnd, onPaneReady, findNode,
} = useVueFlow(FLOW_ID)

const diagram = ref(null)
const nodes = ref([])
const edges = ref([])
const nodeTypes = { shape: shallowRef(ShapeNode), note: shallowRef(NoteNode), group: shallowRef(GroupNode), workflow: shallowRef(WorkflowNode) }
const snap = ref(localStorage.getItem('front.dg.snap') !== '0')
const showMap = ref(localStorage.getItem('front.dg.map') !== '0')
const saving = ref('')
const works = ref([])
const noteList = ref([])
const pickingAsset = ref(false)
const showKeys = ref(false)
const editingTags = ref(false)
const wrap = ref(null)
const edgeColor = () => getComputedStyle(document.documentElement).getPropertyValue('--faint').trim() || '#8a8ca3'
const kind = computed(() => diagram.value?.kind || 'flowchart')

watch(snap, (v) => localStorage.setItem('front.dg.snap', v ? '1' : '0'))
watch(showMap, (v) => localStorage.setItem('front.dg.map', v ? '1' : '0'))

// ── 载入 ──
async function load() {
  const d = await Diagrams.get(route.params.id)
  diagram.value = { ...d, tag_ids: d.tags.map((t) => t.id) }
  applyState(d.data || {}, true)
  lastSaved = snapshot()
  history = [lastSaved]; hIndex = 0; syncHistory()
  await nextTick()
  if (d.data?.viewport?.zoom) setViewport(d.data.viewport)
  else setTimeout(() => fitView({ padding: 0.2, maxZoom: 1.2 }), 60)
  setTimeout(uploadPreview, 1200) // 打开时刷新一次列表缩略图
}
function applyState(data, initial = false) {
  applying = true
  nodes.value = (data.nodes || []).map(hydrateNode)
  edges.value = (data.edges || []).map((e) => hydrateEdge(e, kind.value, edgeColor()))
  nextTick(() => { applying = false; if (!initial) schedule() })
}
onPaneReady(() => {})
onMounted(async () => {
  await guard(load)
  works.value = (await Works.list({ limit: 500 })).items
  noteList.value = await api.get('/api/notes/tree')
  window.addEventListener('keydown', onKey)
  window.addEventListener('beforeunload', flush)
})
onBeforeUnmount(() => { window.removeEventListener('keydown', onKey); window.removeEventListener('beforeunload', flush); flush() })
watch(() => route.params.id, (id, old) => { if (id && id !== old) { flush(); load() } })

// ── 状态快照、撤销重做、自动保存 ──
const snapshot = () => JSON.stringify({ nodes: getNodes.value.map(serializeNode), edges: getEdges.value.map(serializeEdge) })
let lastSaved = ''
let history = []
let hIndex = 0
let applying = false
let hTimer = 0
let sTimer = 0
let lastPreview = 0
const canUndo = ref(false)
const canRedo = ref(false)
function syncHistory() { canUndo.value = hIndex > 0; canRedo.value = hIndex < history.length - 1 }
watch([nodes, edges], () => { if (!applying) schedule() }, { deep: true })
function schedule() {
  clearTimeout(hTimer); clearTimeout(sTimer)
  hTimer = setTimeout(record, 300)
  sTimer = setTimeout(save, 900)
}
function record() {
  const s = snapshot()
  if (s === history[hIndex]) return
  history = history.slice(0, hIndex + 1); history.push(s)
  if (history.length > 120) history.shift()
  hIndex = history.length - 1; syncHistory()
}
const recordSoon = () => nextTick(() => setTimeout(record, 0)) // 离散操作（添加、连线、删除……）各占一步撤销
function undo() { record(); if (hIndex > 0) { hIndex--; applyState(JSON.parse(history[hIndex])); syncHistory() } }
function redo() { if (hIndex < history.length - 1) { hIndex++; applyState(JSON.parse(history[hIndex])); syncHistory() } }
async function save(force = false) {
  const d = diagram.value
  if (!d) return
  const s = snapshot()
  if (s === lastSaved && !force) return
  saving.value = '保存中…'
  try {
    await Diagrams.update(d.id, { data: { ...JSON.parse(s), viewport: { ...viewport.value } } })
    lastSaved = s
    saving.value = '已保存'
    if (Date.now() - lastPreview > 4000) uploadPreview()
  } catch (e) { saving.value = '保存失败'; toast(e.message, true) }
}
function flush() { clearTimeout(sTimer); if (diagram.value && snapshot() !== lastSaved) save() }
onMoveEnd(() => { clearTimeout(vTimer); vTimer = setTimeout(() => diagram.value && Diagrams.update(diagram.value.id, { data: { ...JSON.parse(snapshot()), viewport: { ...viewport.value } } }).catch(() => {}), 1500) })
let vTimer = 0
async function uploadPreview() {
  lastPreview = Date.now()
  const d = diagram.value
  try {
    if (!getNodes.value.length) { await api.del(`/api/diagrams/${d.id}/preview`); return }
    const url = await renderDiagram(wrap.value, getNodes.value, { format: 'png', scale: 1, maxWidth: 1200 })
    const form = new FormData(); form.append('file', await dataUrlToBlob(url), 'preview.png')
    await api.upload(`/api/diagrams/${d.id}/preview`, form, 'PUT')
  } catch { /* 预览图失败不影响保存 */ }
}
async function saveMeta(patch) {
  Object.assign(diagram.value, patch)
  const r = await guard(() => Diagrams.update(diagram.value.id, patch))
  if (r) { diagram.value.updated_at = r.updated_at; diagram.value.tags = r.tags; if ('kind' in patch) applyState(JSON.parse(snapshot())) }
}

// ── 新建节点 / 连线 ──
function makeNode(preset, pos) {
  const n = JSON.parse(JSON.stringify(preset))
  return hydrateNode({ id: uid(), ...n, position: pos })
}
function center() {
  const r = wrap.value.getBoundingClientRect()
  return screenToFlowCoordinate({ x: r.left + r.width / 2, y: r.top + r.height / 2 })
}
function addFromPalette(item, pos) {
  const p = pos || center()
  const w = item.node.style?.width || 200
  const h = item.node.style?.height || 90
  const at = { x: Math.round(p.x - w / 2), y: Math.round(p.y - h / 2) }
  if (!pos) while (getNodes.value.some((o) => Math.abs(o.position.x - at.x) < 12 && Math.abs(o.position.y - at.y) < 12)) { at.x += 32; at.y += 32 } // 连点几次不叠在一起
  const n = makeNode(item.node, at)
  addNodes([n])
  select([n.id])
  recordSoon()
}
function onDragStart(e, item) { e.dataTransfer.setData('application/front-node', item.key); e.dataTransfer.effectAllowed = 'move' }
const allItems = PALETTE.flatMap((g) => g.items)
function onDrop(e) {
  const key = e.dataTransfer.getData('application/front-node')
  const item = allItems.find((i) => i.key === key)
  if (item) addFromPalette(item, screenToFlowCoordinate({ x: e.clientX, y: e.clientY }))
}
onConnect((c) => {
  const src = findNode(c.source)
  const color = kind.value === 'workflow' ? src?.data?.color : undefined
  const type = kind.value === 'flowchart' ? 'smoothstep' : 'default'
  addEdges([hydrateEdge({ id: uid('e'), ...c, type, data: color ? { color } : {} }, kind.value, edgeColor())])
  recordSoon()
})
function select(ids) { for (const n of getNodes.value) n.selected = ids.includes(n.id); for (const e of getEdges.value) e.selected = false }

// Tab：在选中节点旁边接一个新节点（流程图向下，脑图向右）
function addChild() {
  const [n] = getSelectedNodes.value
  if (!n || n.type === 'group') return
  const w = n.dimensions.width, h = n.dimensions.height
  const right = kind.value !== 'flowchart'
  const siblings = getEdges.value.filter((e) => e.source === n.id).length
  const preset = n.type === 'workflow' ? PALETTE[1].items[0].node : { type: 'shape', data: { label: '新节点', shape: n.data.shape === 'diamond' ? 'rect' : n.data.shape || 'rect', color: n.data.color }, style: { width: n.type === 'shape' ? w : 168, height: n.type === 'shape' && n.data.shape !== 'diamond' ? h : 64 } }
  const pos = right ? { x: n.position.x + w + 90, y: n.position.y + siblings * (h + 24) } : { x: n.position.x + siblings * (w + 40), y: n.position.y + h + 80 }
  const c = makeNode(preset, pos)
  addNodes([c])
  const sh = right ? 'r' : 'b', th = right ? 'l' : 't'
  const isWf = n.type === 'workflow'
  addEdges([hydrateEdge({ id: uid('e'), source: n.id, target: c.id, sourceHandle: isWf ? `out-${n.data.outputs?.[0]?.id}` : sh, targetHandle: isWf ? `in-${c.data.inputs?.[0]?.id}` : th, type: kind.value === 'flowchart' ? 'smoothstep' : 'default', data: {} }, kind.value, edgeColor())])
  select([c.id])
  recordSoon()
}

// ── 复制粘贴 ──
let clipboard = null
function copySel() {
  const sel = getSelectedNodes.value
  if (!sel.length) return
  const ids = new Set(sel.map((n) => n.id))
  clipboard = { nodes: sel.map(serializeNode), edges: getEdges.value.filter((e) => ids.has(e.source) && ids.has(e.target)).map(serializeEdge) }
}
function paste(offset = 40) {
  if (!clipboard) return
  const map = {}
  const ns = clipboard.nodes.map((n) => { const id = uid(); map[n.id] = id; return hydrateNode({ ...JSON.parse(JSON.stringify(n)), id, position: { x: n.position.x + offset, y: n.position.y + offset } }) })
  const es = clipboard.edges.map((e) => hydrateEdge({ ...e, id: uid('e'), source: map[e.source], target: map[e.target] }, kind.value, edgeColor()))
  addNodes(ns); addEdges(es)
  clipboard = { nodes: ns.map((n) => ({ ...n })), edges: es.map(serializeEdge) }
  select(ns.map((n) => n.id))
  recordSoon()
}
function duplicateSel() { copySel(); paste(32) }
function deleteSel() { removeEdges(getSelectedEdges.value); removeNodes(getSelectedNodes.value); recordSoon() }

function onKey(e) {
  const t = e.target
  if (t && (t.closest?.('input, textarea, select, [contenteditable="true"]'))) return
  const mod = e.ctrlKey || e.metaKey
  const k = e.key.toLowerCase()
  if (mod && k === 's') { e.preventDefault(); save(true) }
  else if (mod && k === 'z' && !e.shiftKey) { e.preventDefault(); undo() }
  else if (mod && (k === 'y' || (k === 'z' && e.shiftKey))) { e.preventDefault(); redo() }
  else if (mod && k === 'c') copySel()
  else if (mod && k === 'v') { e.preventDefault(); paste() }
  else if (mod && k === 'd') { e.preventDefault(); duplicateSel() }
  else if (mod && k === 'a') { e.preventDefault(); select(getNodes.value.map((n) => n.id)) }
  else if (k === 'tab') { e.preventDefault(); addChild() }
  else if (k === '?') showKeys.value = !showKeys.value
}

// ── 对齐与层级 ──
function align(mode) {
  const sel = getSelectedNodes.value
  if (sel.length < 2) return
  const box = (n) => ({ x: n.position.x, y: n.position.y, w: n.dimensions.width, h: n.dimensions.height })
  const bs = sel.map(box)
  const minX = Math.min(...bs.map((b) => b.x)), maxX = Math.max(...bs.map((b) => b.x + b.w))
  const minY = Math.min(...bs.map((b) => b.y)), maxY = Math.max(...bs.map((b) => b.y + b.h))
  if (mode === 'dh' || mode === 'dv') {
    const horiz = mode === 'dh'
    const order = sel.map((n, i) => [n, bs[i]]).sort((a, b) => (horiz ? a[1].x - b[1].x : a[1].y - b[1].y))
    const total = order.reduce((s, [, b]) => s + (horiz ? b.w : b.h), 0)
    const gap = ((horiz ? maxX - minX : maxY - minY) - total) / (order.length - 1)
    let cur = horiz ? minX : minY
    for (const [n, b] of order) { n.position = horiz ? { x: cur, y: n.position.y } : { x: n.position.x, y: cur }; cur += (horiz ? b.w : b.h) + gap }
    return
  }
  sel.forEach((n, i) => {
    const b = bs[i]
    const p = { ...n.position }
    if (mode === 'l') p.x = minX
    if (mode === 'c') p.x = (minX + maxX) / 2 - b.w / 2
    if (mode === 'r') p.x = maxX - b.w
    if (mode === 't') p.y = minY
    if (mode === 'm') p.y = (minY + maxY) / 2 - b.h / 2
    if (mode === 'b') p.y = maxY - b.h
    n.position = p
  })
}
function layer(front) {
  const zs = getNodes.value.map((n) => n.zIndex || 0)
  for (const n of getSelectedNodes.value) n.zIndex = front ? Math.max(...zs) + 1 : Math.min(...zs) - 1
  schedule()
}

// ── 属性面板 ──
const selNodes = computed(() => getSelectedNodes.value)
const selEdges = computed(() => getSelectedEdges.value)
const node = computed(() => (selNodes.value.length === 1 && !selEdges.value.length ? selNodes.value[0] : null))
const edge = computed(() => (selEdges.value.length === 1 && !selNodes.value.length ? selEdges.value[0] : null))
function setData(patch) { updateNodeData(node.value.id, patch) }
function setList(key, i, patch) { const list = [...(node.value.data[key] || [])]; list[i] = { ...list[i], ...patch }; setData({ [key]: list }) }
function addPort(key) {
  const list = [...(node.value.data[key] || [])]
  const ids = new Set(list.map((p) => p.id))
  let n = list.length; const pre = key === 'inputs' ? 'i' : 'o'
  while (ids.has(pre + n)) n++
  list.push({ id: pre + n, label: key === 'inputs' ? '输入' : '输出' }); setData({ [key]: list })
}
function removeItem(key, i) {
  const list = [...(node.value.data[key] || [])]
  const [gone] = list.splice(i, 1)
  if (gone?.id) { const h = (key === 'inputs' ? 'in-' : 'out-') + gone.id; removeEdges(getEdges.value.filter((e) => (e.source === node.value.id && e.sourceHandle === h) || (e.target === node.value.id && e.targetHandle === h))) }
  setData({ [key]: list })
}
function setEdge(patch) {
  const e = edge.value
  const data = { ...(e.data || {}), ...(patch.data || {}) }
  const next = hydrateEdge({ ...serializeEdge(e), ...patch, data }, kind.value, edgeColor())
  edges.value = edges.value.map((x) => (x.id === e.id ? { ...next, selected: true } : x))
}
function pickLink(kind2, val) { setData({ link: val }); if (kind2 === 'asset') pickingAsset.value = false }
function openLink(link) {
  if (!link) return
  if (/^https?:\/\//.test(link)) window.open(link, '_blank', 'noopener')
  else { flush(); router.push(link) }
}
provide('openLink', openLink)

// ── 导出与其他操作 ──
const exportOpen = ref(false)
async function exportImage(format) {
  exportOpen.value = false
  try {
    const url = await renderDiagram(wrap.value, getNodes.value, { format, scale: 2 })
    download(url, `${diagram.value.title}.${format}`)
  } catch (e) { toast(e.message, true) }
}
function exportJson() { exportOpen.value = false; flush(); download(`/api/diagrams/${diagram.value.id}/export`, `${diagram.value.title}.diagram.json`) }
async function duplicate() { flush(); const d = await guard(() => api.post(`/api/diagrams/${diagram.value.id}/duplicate`), '已复制'); if (d) router.push(`/diagrams/${d.id}`) }
async function remove() {
  if (!confirm(`删除图表“${diagram.value.title}”？`)) return
  clearTimeout(sTimer); lastSaved = snapshot()
  await guard(() => Diagrams.remove(diagram.value.id), '已删除')
  diagram.value = null
  router.push('/diagrams')
}
const zoomPct = computed(() => Math.round((viewport.value?.zoom || 1) * 100))
const KEYS = [['双击', '编辑文字'], ['拖动连接点', '连线'], ['Tab', '接一个新节点'], ['Delete', '删除所选'], ['Ctrl/⌘ Z / ⇧Z', '撤销 / 重做'], ['Ctrl/⌘ C / V / D', '复制 / 粘贴 / 再制'], ['Ctrl/⌘ A', '全选'], ['Shift + 拖动', '框选'], ['Ctrl/⌘ S', '立即保存'], ['?', '显示快捷键']]
const shapeIcon = { rect: 'M3,6 h18 v12 h-18 z', pill: 'M8,6 h8 a6,6 0 0 1 0,12 h-8 a6,6 0 0 1 0,-12 z', diamond: 'M12,3 L21,12 L12,21 L3,12 Z', parallelogram: 'M7,6 h14 l-4,12 h-14 z', document: 'M4,5 h16 v12 c-4,-2 -6,3 -10,1 c-3,-1 -4,-1 -6,0 z', cylinder: 'M5,7 c0,-3 14,-3 14,0 v10 c0,3 -14,3 -14,0 z M5,7 c0,3 14,3 14,0', hexagon: 'M7,5 h10 l4,7 l-4,7 h-10 l-4,-7 z', circle: 'M12,5 a7,7 0 1 0 0.01,0 z', note: 'M5,4 h14 v11 l-5,5 h-9 z M14,20 v-5 h5', group: 'M3,6 h18 v13 h-18 z', wf: 'M4,6 h16 v12 h-16 z M4,10 h16', 'wf-src': 'M4,6 h16 v12 h-16 z M4,10 h16' }
</script>

<template>
  <div v-if="diagram" class="dg">
    <header class="dg-bar">
      <RouterLink to="/diagrams" class="btn ghost iconbtn" title="全部图表"><ArrowLeft :size="16" /></RouterLink>
      <input :value="diagram.title" class="dg-title" aria-label="图表标题" @change="saveMeta({ title: $event.target.value.trim() || '未命名图表' })" />
      <span class="badge">{{ KINDS[diagram.kind] }}</span>
      <span class="small faint">{{ saving }}</span>
      <span class="spacer" />
      <div class="dg-group">
        <button class="ghost iconbtn" :disabled="!canUndo" title="撤销（Ctrl+Z）" @click="undo"><Undo2 :size="16" /></button>
        <button class="ghost iconbtn" :disabled="!canRedo" title="重做（Ctrl+Shift+Z）" @click="redo"><Redo2 :size="16" /></button>
      </div>
      <div class="dg-group">
        <button class="ghost iconbtn" :class="{ on: snap }" title="吸附网格" @click="snap = !snap"><Magnet :size="16" /></button>
        <button class="ghost iconbtn" :class="{ on: showMap }" title="小地图" @click="showMap = !showMap"><MapIcon :size="16" /></button>
        <button class="ghost iconbtn" title="快捷键（?）" @click="showKeys = !showKeys"><Keyboard :size="16" /></button>
      </div>
      <div class="dg-group">
        <button class="ghost iconbtn" title="缩小" @click="zoomOut()"><ZoomOut :size="16" /></button>
        <span class="dg-zoom mono">{{ zoomPct }}%</span>
        <button class="ghost iconbtn" title="放大" @click="zoomIn()"><ZoomIn :size="16" /></button>
        <button class="ghost iconbtn" title="适应画布" @click="fitView({ padding: 0.2, duration: 300 })"><Maximize :size="16" /></button>
      </div>
      <div class="dg-pop-wrap">
        <button class="primary" @click="exportOpen = !exportOpen"><Download :size="15" />导出</button>
        <div v-if="exportOpen" class="dg-pop" @mouseleave="exportOpen = false">
          <button class="ghost" @click="exportImage('png')">PNG 图片（2 倍）</button>
          <button class="ghost" @click="exportImage('svg')">SVG 矢量图</button>
          <button class="ghost" @click="exportJson">JSON（可再导入）</button>
        </div>
      </div>
    </header>

    <div class="dg-body">
      <aside class="dg-palette">
        <div v-for="g in PALETTE" :key="g.group" class="dg-pal-group">
          <div class="eyebrow">{{ g.group }}</div>
          <div class="dg-pal-grid">
            <button v-for="it in g.items" :key="it.key" class="dg-pal-item" draggable="true" :title="'拖到画布，或点击添加：' + it.label" @dragstart="onDragStart($event, it)" @click="addFromPalette(it)">
              <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"><path :d="shapeIcon[it.key]" :stroke="it.node.data.color" :fill="tint(it.node.data.color, 22)" stroke-width="1.4" stroke-linejoin="round" /></svg>
              <span>{{ it.label }}</span>
            </button>
          </div>
        </div>
        <p class="small faint dg-tip">拖到画布上，或点一下加在中间。双击节点改文字，拖动节点边上的圆点连线。</p>
      </aside>

      <div ref="wrap" class="dg-canvas" @drop.prevent="onDrop" @dragover.prevent>
        <VueFlow :id="FLOW_ID" v-model:nodes="nodes" v-model:edges="edges" class="dg-flow" :node-types="nodeTypes"
          :connection-mode="ConnectionMode.Loose" :snap-to-grid="snap" :snap-grid="[16, 16]" :min-zoom="0.1" :max-zoom="3"
          :delete-key-code="['Delete', 'Backspace']" :selection-key-code="'Shift'" :multi-selection-key-code="['Meta', 'Control']"
          :default-edge-options="{ type: 'smoothstep' }" :connect-on-click="false" fit-view-on-init elevate-edges-on-select>
          <Background :gap="16" :size="1.2" pattern-color="var(--line-strong)" />
          <MiniMap v-if="showMap" :width="168" :height="112" pannable zoomable :node-color="(n) => n.data?.color || '#8a8ca3'" :node-stroke-width="0" :mask-color="'transparent'" />
        </VueFlow>
        <div v-if="!nodes.length" class="dg-empty">
          <div class="eyebrow">空白画布</div>
          <p>从左侧拖入一个节点开始，或者 <RouterLink to="/diagrams?new=1">用模板新建</RouterLink>。</p>
        </div>
        <div v-if="showKeys" class="dg-keys">
          <div class="row"><b>快捷键</b><span class="spacer" /><button class="ghost iconbtn" @click="showKeys = false"><X :size="14" /></button></div>
          <div v-for="[k, v] in KEYS" :key="k" class="dg-key"><kbd>{{ k }}</kbd><span>{{ v }}</span></div>
        </div>
      </div>

      <aside class="dg-inspector">
        <!-- 多选：对齐 -->
        <template v-if="selNodes.length > 1">
          <div class="eyebrow">已选 {{ selNodes.length }} 个节点</div>
          <div class="dg-align">
            <button class="ghost iconbtn" title="左对齐" @click="align('l')"><AlignStartVertical :size="16" /></button>
            <button class="ghost iconbtn" title="水平居中" @click="align('c')"><AlignCenterVertical :size="16" /></button>
            <button class="ghost iconbtn" title="右对齐" @click="align('r')"><AlignEndVertical :size="16" /></button>
            <button class="ghost iconbtn" title="顶对齐" @click="align('t')"><AlignStartHorizontal :size="16" /></button>
            <button class="ghost iconbtn" title="垂直居中" @click="align('m')"><AlignCenterHorizontal :size="16" /></button>
            <button class="ghost iconbtn" title="底对齐" @click="align('b')"><AlignEndHorizontal :size="16" /></button>
            <button class="ghost iconbtn" title="水平等距" @click="align('dh')"><AlignHorizontalDistributeCenter :size="16" /></button>
            <button class="ghost iconbtn" title="垂直等距" @click="align('dv')"><AlignVerticalDistributeCenter :size="16" /></button>
          </div>
          <div class="row"><button class="small" @click="duplicateSel"><Copy :size="13" />再制</button><button class="small danger" @click="deleteSel"><Trash2 :size="13" />删除</button></div>
        </template>

        <!-- 单个节点 -->
        <template v-else-if="node">
          <div class="eyebrow">{{ { shape: '形状', note: '便签', group: '分组框', workflow: '工作流节点' }[node.type] }}</div>
          <label class="field">文字<textarea :value="node.data.label" rows="2" @input="setData({ label: $event.target.value })" /></label>
          <div v-if="node.type === 'shape'" class="field">形状
            <div class="dg-shapes">
              <button v-for="[s, l] in SHAPES" :key="s" class="ghost iconbtn" :class="{ on: node.data.shape === s }" :title="l" @click="setData({ shape: s })">
                <svg viewBox="0 0 24 24" width="18" height="18"><path :d="shapeIcon[s]" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" /></svg>
              </button>
            </div>
          </div>
          <div class="field">颜色
            <div class="dg-swatches"><button v-for="[c, l] in COLORS" :key="c" class="dg-sw" :class="{ on: node.data.color === c }" :style="{ background: c }" :title="l" @click="setData({ color: c })" /></div>
          </div>
          <template v-if="node.type === 'workflow'">
            <div v-for="key in ['inputs', 'outputs']" :key="key" class="field">
              <div class="row">{{ key === 'inputs' ? '输入端口' : '输出端口' }}<span class="spacer" /><button class="ghost small" @click="addPort(key)"><Plus :size="12" />添加</button></div>
              <div v-for="(p, i) in node.data[key] || []" :key="p.id" class="dg-li"><input :value="p.label" @input="setList(key, i, { label: $event.target.value })" /><button class="ghost iconbtn" title="删除" @click="removeItem(key, i)"><X :size="13" /></button></div>
            </div>
            <div class="field">
              <div class="row">参数<span class="spacer" /><button class="ghost small" @click="setData({ fields: [...(node.data.fields || []), { label: '参数', value: '' }] })"><Plus :size="12" />添加</button></div>
              <div v-for="(f, i) in node.data.fields || []" :key="i" class="dg-li two"><input :value="f.label" placeholder="名称" @input="setList('fields', i, { label: $event.target.value })" /><input :value="f.value" placeholder="值" @input="setList('fields', i, { value: $event.target.value })" /><button class="ghost iconbtn" title="删除" @click="removeItem('fields', i)"><X :size="13" /></button></div>
            </div>
          </template>
          <div v-if="node.type === 'shape'" class="field">链接
            <div class="dg-li"><input :value="node.data.link || ''" placeholder="/notes/1 或 https://…" @change="setData({ link: $event.target.value.trim() || null })" /><button v-if="node.data.link" class="ghost iconbtn" title="打开" @click="openLink(node.data.link)"><Link2 :size="13" /></button></div>
            <div class="row" style="gap:6px">
              <button class="small" @click="pickingAsset = true">素材</button>
              <select class="dg-mini" @change="$event.target.value && pickLink('note', `/notes/${$event.target.value}`); $event.target.value = ''"><option value="">笔记…</option><option v-for="n in noteList" :key="n.id" :value="n.id">{{ n.icon || '·' }} {{ n.title }}</option></select>
              <button v-if="node.data.link" class="ghost small" @click="setData({ link: null })">清除</button>
            </div>
          </div>
          <div class="row" style="gap:6px">
            <button class="ghost small" @click="layer(true)"><BringToFront :size="13" />置顶</button>
            <button class="ghost small" @click="layer(false)"><SendToBack :size="13" />置底</button>
            <span class="spacer" />
            <button class="ghost small danger" @click="deleteSel"><Trash2 :size="13" /></button>
          </div>
        </template>

        <!-- 连线 -->
        <template v-else-if="edge">
          <div class="eyebrow">连线</div>
          <label class="field">文字<input :value="edge.label || ''" placeholder="例如：是 / 否" @change="setEdge({ label: $event.target.value || undefined })" /></label>
          <div class="field">样式<div class="seg"><button v-for="[t, l] in EDGE_TYPES" :key="t" :class="{ on: (edge.type || 'smoothstep') === t }" @click="setEdge({ type: t })">{{ l }}</button></div></div>
          <div class="field">颜色
            <div class="dg-swatches"><button class="dg-sw none" :class="{ on: !edge.data?.color }" title="默认" @click="setEdge({ data: { color: null } })" /><button v-for="[c, l] in COLORS" :key="c" class="dg-sw" :class="{ on: edge.data?.color === c }" :style="{ background: c }" :title="l" @click="setEdge({ data: { color: c } })" /></div>
          </div>
          <label class="row small"><input type="checkbox" :checked="!!edge.data?.dashed" @change="setEdge({ data: { dashed: $event.target.checked } })" />虚线</label>
          <label class="row small"><input type="checkbox" :checked="!!edge.markerEnd" @change="setEdge({ data: { arrow: $event.target.checked } })" />箭头</label>
          <label class="row small"><input type="checkbox" :checked="!!edge.animated" @change="setEdge({ animated: $event.target.checked })" />流动动画</label>
          <button class="ghost small danger" @click="deleteSel"><Trash2 :size="13" />删除连线</button>
        </template>

        <!-- 图表属性 -->
        <template v-else>
          <div class="eyebrow">图表</div>
          <label class="field">类型<select :value="diagram.kind" @change="saveMeta({ kind: $event.target.value })"><option v-for="(l, k) in KINDS" :key="k" :value="k">{{ l }}</option></select></label>
          <label class="field">说明<textarea :value="diagram.description || ''" rows="3" placeholder="这张图讲什么" @change="saveMeta({ description: $event.target.value })" /></label>
          <label class="field">关联作品<select :value="diagram.work_id" @change="saveMeta({ work_id: $event.target.value ? +$event.target.value : null })"><option :value="null">不关联</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select></label>
          <div class="field">
            <div class="row">标签<span class="spacer" /><button class="ghost small" @click="editingTags = !editingTags">{{ editingTags ? '收起' : '编辑' }}</button></div>
            <div class="row" style="gap:5px;flex-wrap:wrap"><span v-for="t in diagram.tags.filter((t) => diagram.tag_ids.includes(t.id))" :key="t.id" class="chip on">{{ t.name }}</span><span v-if="!diagram.tag_ids.length" class="small faint">暂无标签</span></div>
            <TagPicker v-if="editingTags" :model-value="diagram.tag_ids" class="dg-tags" @update:model-value="saveMeta({ tag_ids: $event })" />
          </div>
          <div class="dg-stats small muted"><span>{{ nodes.length }} 个节点</span><span>{{ edges.length }} 条连线</span></div>
          <div class="row" style="gap:6px">
            <button class="small" @click="saveMeta({ pinned: !diagram.pinned })"><component :is="diagram.pinned ? PinOff : Pin" :size="13" />{{ diagram.pinned ? '取消置顶' : '置顶' }}</button>
            <button class="small" @click="duplicate"><Copy :size="13" />复制图表</button>
            <button class="small danger" @click="remove"><Trash2 :size="13" />删除</button>
          </div>
        </template>
      </aside>
    </div>
    <AssetPicker v-if="pickingAsset" @pick="(a) => pickLink('asset', `/assets?open=${a.id}`)" @close="pickingAsset = false" />
  </div>
</template>

<style scoped>
.dg { display: grid; grid-template-rows: auto 1fr; gap: 10px; height: calc(100vh - 104px); min-height: 520px; }
.dg-bar { display: flex; align-items: center; gap: 8px; padding: 6px 8px; background: var(--panel); border: 1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow); }
.dg-title { width: auto; min-width: 140px; max-width: 360px; font-size: 15px; font-weight: 600; background: transparent; border-color: transparent; }
.dg-title:hover { border-color: var(--line); }
.dg-group { display: flex; align-items: center; gap: 2px; padding: 0 6px; border-left: 1px solid var(--line); }
.dg-group button.on { color: var(--accent); background: var(--accent-soft); }
.dg-zoom { width: 44px; text-align: center; font-size: 12px; color: var(--muted); }
.dg-pop-wrap { position: relative; margin-left: 4px; }
.dg-pop { position: absolute; right: 0; top: calc(100% + 6px); z-index: 30; display: grid; min-width: 180px; padding: 6px; background: var(--panel); border-radius: 12px; box-shadow: var(--shadow-pop); }
.dg-pop button { justify-content: flex-start; border-radius: 8px; }
.dg-body { display: grid; grid-template-columns: 156px 1fr 248px; gap: 10px; min-height: 0; }
.dg-palette, .dg-inspector { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 12px; overflow: auto; box-shadow: var(--shadow); }
.dg-pal-group + .dg-pal-group { margin-top: 14px; }
.dg-pal-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 8px; }
.dg-pal-item { flex-direction: column; gap: 4px; padding: 7px 2px; border-radius: 10px; font-size: 11.5px; color: var(--muted); background: var(--panel2); border-color: transparent; cursor: grab; white-space: normal; text-align: center; line-height: 1.2; }
.dg-pal-item:hover { color: var(--text); border-color: var(--line-strong); }
.dg-pal-item:active { cursor: grabbing; }
.dg-tip { margin: 14px 2px 0; line-height: 1.6; }
.dg-canvas { position: relative; border-radius: 14px; overflow: hidden; border: 1px solid var(--line); min-height: 0; }
.dg-canvas :deep(.vue-flow) { height: 100%; }
.dg-empty { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; pointer-events: none; color: var(--muted); }
.dg-empty a { pointer-events: auto; color: var(--accent); }
.dg-keys { position: absolute; left: 12px; bottom: 12px; z-index: 10; width: 250px; padding: 10px 12px; background: var(--chrome); backdrop-filter: blur(14px); border-radius: 12px; box-shadow: var(--shadow-pop); font-size: 12px; }
.dg-key { display: flex; justify-content: space-between; gap: 10px; padding: 3px 0; color: var(--muted); }
kbd { font: 11px var(--font); padding: 1px 6px; border-radius: 5px; background: var(--panel2); border: 1px solid var(--line); color: var(--text); }
.dg-inspector { display: grid; gap: 12px; align-content: start; }
.dg-shapes, .dg-align { display: flex; flex-wrap: wrap; gap: 2px; }
.dg-shapes button.on { color: var(--accent); background: var(--accent-soft); }
.dg-swatches { display: flex; flex-wrap: wrap; gap: 7px; }
.dg-sw { width: 22px; height: 22px; padding: 0; border-radius: 50%; border: 2px solid transparent; box-shadow: 0 0 0 1px var(--line) inset; }
.dg-sw.on { border-color: var(--text); }
.dg-sw.none { background: linear-gradient(135deg, transparent 45%, var(--danger) 45% 55%, transparent 55%), var(--panel2); }
.dg-li { display: flex; gap: 4px; align-items: center; }
.dg-li input { padding: 5px 8px; font-size: 12.5px; }
.dg-li.two input:first-child { width: 40%; }
.dg-mini { width: auto; padding: 4px 8px; font-size: 12px; }
.dg-stats { display: flex; gap: 14px; }
.dg-tags :deep(.chip) { font-size: 11px; }
@media (max-width: 1100px) { .dg-body { grid-template-columns: 150px 1fr 230px; } }
</style>
