<script setup>
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim()
import cytoscape from 'cytoscape'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, LABELS, Relations, thumb, Worlds } from '../api'
import { guard, toast } from '../toast'

const route = useRoute()
const worlds = ref([])
const worldId = ref(route.query.world_id ? Number(route.query.world_id) : '')
const el = ref(null)
const graph = ref({ nodes: [], edges: [], kinds: [], layout: { positions: {}, kind_colors: {} } })
const picked = ref([])
const sel = ref(null)
const kind = ref('')
const hidden = reactive(new Set())
const colors = reactive({})
const showPending = ref(true)
let cy

const GENDER = { female: '#f472b6', male: '#60a5fa', other: '#a78bfa', unknown: '#94a3b8' }
const PALETTE = ['#a78bfa', '#f472b6', '#34d399', '#fbbf24', '#60a5fa', '#f87171', '#2dd4bf', '#fb923c', '#c084fc', '#a3e635']
function hashColor(k) { let h = 0; for (const ch of k) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return PALETTE[h % PALETTE.length] }
const colorOf = (k) => colors[k] || hashColor(k)

async function load() {
  graph.value = await api.get('/api/graph', { world_id: worldId.value })
  hidden.clear()
  for (const k of Object.keys(colors)) delete colors[k]
  Object.assign(colors, graph.value.layout.kind_colors)
  await nextTick()
  draw()
}
const visibleEdges = computed(() => graph.value.edges.filter((e) => !hidden.has(e.kind) && (showPending.value || e.confirmed)))
function draw() {
  cy?.destroy()
  const saved = graph.value.layout.positions || {}
  const allSaved = graph.value.nodes.length && graph.value.nodes.every((n) => saved[n.id])
  cy = cytoscape({
    container: el.value,
    elements: [
      ...graph.value.nodes.map((n) => ({ data: { id: `c${n.id}`, cid: n.id, label: n.name, color: GENDER[n.gender], img: n.avatar_asset_id ? thumb(n.avatar_asset_id) : 'none' } })),
      ...graph.value.edges.map((e) => ({ data: { id: `r${e.id}`, rid: e.id, kind: e.kind, source: `c${e.source}`, target: `c${e.target}`, label: e.kind + (e.confirmed ? '' : '（AI 待确认）'), pending: !e.confirmed, both: e.bidirectional, ecolor: colorOf(e.kind) } })),
    ],
    style: [
      { selector: 'node', style: { label: 'data(label)', color: css('--text'), 'font-size': 15, 'text-valign': 'bottom', 'text-margin-y': 8, width: 64, height: 64, 'background-color': css('--panel2'), 'background-image': 'data(img)', 'background-fit': 'cover', 'border-width': 3, 'border-color': 'data(color)', 'font-family': 'Noto Sans SC, Microsoft YaHei, sans-serif' } },
      { selector: 'node:selected', style: { 'border-color': '#fbbf24', 'border-width': 5 } },
      { selector: 'edge', style: { label: 'data(label)', 'font-size': 13, color: css('--text'), 'text-background-color': css('--bg'), 'text-background-opacity': 0.85, 'text-background-padding': 3, width: 2.5, 'line-color': 'data(ecolor)', 'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'target-arrow-color': 'data(ecolor)', 'font-family': 'Noto Sans SC, Microsoft YaHei, sans-serif' } },
      { selector: 'edge[?both]', style: { 'source-arrow-shape': 'triangle', 'source-arrow-color': 'data(ecolor)' } },
      { selector: 'edge[?pending]', style: { 'line-style': 'dashed' } },
      { selector: 'edge:selected', style: { width: 5 } },
      { selector: '.hidden', style: { display: 'none' } },
    ],
    layout: allSaved
      ? { name: 'preset', positions: (n) => saved[n.data('cid')], fit: true, padding: 60 }
      : graph.value.nodes.length <= 10
        ? { name: 'circle', fit: false, radius: Math.max(140, Math.min(el.value.clientWidth, el.value.clientHeight) * 0.34), startAngle: -Math.PI / 2 }
        : { name: 'cose', animate: false, padding: 60, nodeRepulsion: () => 400000, idealEdgeLength: () => 180, nodeOverlap: 40 },
    wheelSensitivity: 0.3,
  })
  if (!allSaved) {
    for (const [id, p] of Object.entries(saved)) cy.$id(`c${id}`).position(p)
    if (graph.value.nodes.length <= 10) cy.center()
  }
  applyVisibility()
  if (route.query.focus) cy.$id(`c${route.query.focus}`).select()
  cy.on('tap', 'node', (evt) => {
    const id = evt.target.data('cid')
    picked.value = [...picked.value.filter((x) => x !== id), id].slice(-2)
    sel.value = null
  })
  cy.on('tap', 'edge', (evt) => { sel.value = graph.value.edges.find((e) => e.id === evt.target.data('rid')); picked.value = [] })
  cy.on('tap', (evt) => { if (evt.target === cy) { picked.value = []; sel.value = null } })
}
function applyVisibility() {
  if (!cy) return
  const vis = new Set(visibleEdges.value.map((e) => `r${e.id}`))
  cy.edges().forEach((e) => (vis.has(e.id()) ? e.removeClass('hidden') : e.addClass('hidden')))
}
watch([() => [...hidden], showPending], applyVisibility)
function toggleKind(k) { hidden.has(k) ? hidden.delete(k) : hidden.add(k) }
let colorTimer
function setColor(k, v) {
  colors[k] = v
  cy?.edges().filter((e) => e.data('kind') === k).data('ecolor', v)
  clearTimeout(colorTimer)
  colorTimer = setTimeout(() => api.put('/api/graph/layout', { world_id: worldId.value || null, kind_colors: { ...colors } }), 500)
}

const nameOf = (id) => graph.value.nodes.find((n) => n.id === id)?.name
async function addRel() {
  const [a, b] = picked.value
  await guard(() => Relations.create({ source_id: a, target_id: b, kind: kind.value }), '已添加')
  kind.value = ''; picked.value = []
  await saveLayout(true)
  load()
}
async function confirmRel() { await guard(() => Relations.update(sel.value.id, { confirmed: true }), '已确认'); sel.value = null; load() }
async function delRel() { await guard(() => Relations.remove(sel.value.id), '已删除'); sel.value = null; load() }
async function saveLayout(silent = false) {
  const positions = {}
  cy.nodes().forEach((n) => { positions[n.data('cid')] = n.position() })
  await api.put('/api/graph/layout', { world_id: worldId.value || null, positions })
  if (silent !== true) toast('布局已保存，下次打开会按这个位置显示')
}
async function resetLayout() {
  await api.del(`/api/graph/layout${worldId.value ? `?world_id=${worldId.value}` : ''}`)
  toast('已恢复自动布局')
  load()
}
function exportPng() {
  const png = cy.png({ full: true, scale: 2, bg: css('--bg'), output: 'base64uri' })
  const a = document.createElement('a')
  a.href = png
  a.download = `关系网-${worlds.value.find((w) => w.id === worldId.value)?.name ?? '全部'}.png`
  a.click()
}
const exportJsonUrl = computed(() => `/api/graph/export${worldId.value ? `?world_id=${worldId.value}` : ''}`)

onMounted(async () => { worlds.value = (await Worlds.list({ limit: 500 })).items; load() })
watch(worldId, load)
onBeforeUnmount(() => cy?.destroy())
</script>
<template>
  <div class="grid">
    <div class="row">
      <select v-model="worldId" style="width:200px"><option value="">全部角色</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }}</option></select>
      <span class="muted small">{{ graph.nodes.length }} 个角色 · {{ visibleEdges.length }} / {{ graph.edges.length }} 条关系</span>
      <span class="spacer" />
      <button @click="saveLayout">📌 保存布局</button>
      <button @click="resetLayout">↺ 自动布局</button>
      <button @click="exportPng"><Ico g="⇩" />导出 PNG</button>
      <a class="btn" :href="exportJsonUrl"><Ico g="⇩" />导出 JSON</a>
    </div>
    <div class="row card" style="padding:10px 14px;gap:8px">
      <span class="small muted">关系类型（点击显示 / 隐藏，色块可改颜色）</span>
      <span v-for="k in graph.kinds" :key="k.kind" class="chip click kind" :style="{ opacity: hidden.has(k.kind) ? 0.35 : 1, borderColor: colorOf(k.kind) }">
        <input type="color" :value="colorOf(k.kind)" @input="setColor(k.kind, $event.target.value)" @click.stop />
        <span @click="toggleKind(k.kind)">{{ k.kind }} · {{ k.count }}</span>
      </span>
      <label class="row small" style="gap:4px;margin-left:8px"><input v-model="showPending" type="checkbox" style="width:auto" />显示 AI 待确认</label>
      <span class="spacer" />
      <span class="row small muted" style="gap:10px"><span v-for="(c, g) in GENDER" :key="g"><span :style="{ color: c }">●</span> {{ LABELS.gender[g] }}</span><span>┄ AI 待确认</span></span>
    </div>
    <div class="card" style="padding:0;position:relative">
      <div ref="el" style="height: calc(100vh - 250px); min-height: 440px" />
      <div v-if="picked.length === 1" class="card" style="position:absolute;right:14px;top:14px;width:260px">
        <b>{{ nameOf(picked[0]) }}</b>
        <p class="small muted">再点一个角色可以连线</p>
        <RouterLink class="btn" :to="`/characters/${picked[0]}`">查看角色详情 →</RouterLink>
      </div>
      <div v-if="picked.length === 2" class="card" style="position:absolute;right:14px;top:14px;width:300px">
        <b>{{ nameOf(picked[0]) }} → {{ nameOf(picked[1]) }}</b>
        <form class="row" style="margin-top:8px;flex-wrap:nowrap" @submit.prevent="addRel"><input v-model="kind" placeholder="关系名" required list="kinds" /><button class="primary" type="submit">连线</button></form>
        <datalist id="kinds"><option v-for="k in graph.kinds" :key="k.kind" :value="k.kind" /></datalist>
      </div>
      <div v-if="sel" class="card" style="position:absolute;right:14px;top:14px;width:300px">
        <b>{{ nameOf(sel.source) }} → {{ nameOf(sel.target) }}：{{ sel.kind }}</b>
        <p class="small muted">{{ sel.description || '无说明' }}</p>
        <div class="row"><button v-if="!sel.confirmed" class="primary" @click="confirmRel">确认 AI 建议</button><button class="danger" @click="delRel">删除</button></div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.kind input[type=color] { width: 18px; height: 18px; padding: 0; border: none; border-radius: 50%; background: none; cursor: pointer; }
.kind input[type=color]::-webkit-color-swatch-wrapper { padding: 0; }
.kind input[type=color]::-webkit-color-swatch { border: none; border-radius: 50%; }
.kind { padding: 3px 10px 3px 4px; }
</style>
