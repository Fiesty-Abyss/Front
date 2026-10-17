<script setup>
import cytoscape from 'cytoscape'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, LABELS, Relations, thumb, Worlds } from '../api'
import { guard } from '../toast'

const route = useRoute()
const worlds = ref([])
const worldId = ref(route.query.world_id ? Number(route.query.world_id) : '')
const el = ref(null)
const graph = ref({ nodes: [], edges: [] })
const picked = ref([])
const sel = ref(null)
const kind = ref('')
let cy

const COLORS = { female: '#f472b6', male: '#60a5fa', other: '#a78bfa', unknown: '#94a3b8' }

async function load() {
  graph.value = await api.get('/api/graph', { world_id: worldId.value })
  await nextTick()
  draw()
}
function draw() {
  cy?.destroy()
  cy = cytoscape({
    container: el.value,
    elements: [
      ...graph.value.nodes.map((n) => ({ data: { id: `c${n.id}`, cid: n.id, label: n.name, color: COLORS[n.gender], img: n.avatar_asset_id ? thumb(n.avatar_asset_id) : 'none' } })),
      ...graph.value.edges.map((e) => ({ data: { id: `r${e.id}`, rid: e.id, source: `c${e.source}`, target: `c${e.target}`, label: e.kind + (e.confirmed ? '' : '（AI 待确认）'), pending: !e.confirmed, both: e.bidirectional } })),
    ],
    style: [
      { selector: 'node', style: { label: 'data(label)', color: '#e7e8f5', 'font-size': 15, 'text-valign': 'bottom', 'text-margin-y': 8, width: 64, height: 64, 'background-color': '#1f2340', 'background-image': 'data(img)', 'background-fit': 'cover', 'border-width': 3, 'border-color': 'data(color)', 'font-family': 'Noto Sans SC, Microsoft YaHei, sans-serif' } },
      { selector: 'node:selected', style: { 'border-color': '#fbbf24', 'border-width': 5 } },
      { selector: 'edge', style: { label: 'data(label)', 'font-size': 13, color: '#c9cbe6', 'text-background-color': '#0f1020', 'text-background-opacity': 0.85, 'text-background-padding': 3, width: 2, 'line-color': '#8b7cf6', 'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'target-arrow-color': '#8b7cf6', 'font-family': 'Noto Sans SC, Microsoft YaHei, sans-serif' } },
      { selector: 'edge[?both]', style: { 'source-arrow-shape': 'triangle', 'source-arrow-color': '#8b7cf6' } },
      { selector: 'edge[?pending]', style: { 'line-style': 'dashed', 'line-color': '#fbbf24', 'target-arrow-color': '#fbbf24', 'source-arrow-color': '#fbbf24' } },
      { selector: 'edge:selected', style: { width: 4, 'line-color': '#f472b6' } },
    ],
    layout: graph.value.nodes.length <= 10
      ? { name: 'circle', fit: false, radius: Math.max(140, Math.min(el.value.clientWidth, el.value.clientHeight) * 0.34), startAngle: -Math.PI / 2 }
      : { name: 'cose', animate: false, padding: 60, nodeRepulsion: () => 400000, idealEdgeLength: () => 180, nodeOverlap: 40 },
    wheelSensitivity: 0.3,
  })
  if (graph.value.nodes.length <= 10) cy.center()
  cy.on('tap', 'node', (evt) => {
    const id = evt.target.data('cid')
    picked.value = [...picked.value.filter((x) => x !== id), id].slice(-2)
    sel.value = null
  })
  cy.on('tap', 'edge', (evt) => { sel.value = graph.value.edges.find((e) => e.id === evt.target.data('rid')); picked.value = [] })
  cy.on('tap', (evt) => { if (evt.target === cy) { picked.value = []; sel.value = null } })
}
const nameOf = (id) => graph.value.nodes.find((n) => n.id === id)?.name
async function addRel() {
  const [a, b] = picked.value
  await guard(() => Relations.create({ source_id: a, target_id: b, kind: kind.value }), '已添加')
  kind.value = ''
  picked.value = []
  load()
}
async function confirmRel() { await guard(() => Relations.update(sel.value.id, { confirmed: true }), '已确认'); sel.value = null; load() }
async function delRel() { await guard(() => Relations.remove(sel.value.id), '已删除'); sel.value = null; load() }

onMounted(async () => { worlds.value = (await Worlds.list({ limit: 500 })).items; load() })
watch(worldId, load)
onBeforeUnmount(() => cy?.destroy())
</script>
<template>
  <div class="grid">
    <div class="row">
      <select v-model="worldId" style="width:220px"><option value="">全部角色</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }}</option></select>
      <span class="muted small">{{ graph.nodes.length }} 个角色 · {{ graph.edges.length }} 条关系 · 点两个角色可连线，点连线可确认/删除</span>
      <span class="spacer" />
      <span class="row small muted" style="gap:10px"><span v-for="(c, g) in COLORS" :key="g"><span :style="{ color: c }">●</span> {{ LABELS.gender[g] }}</span><span><span style="color:#fbbf24">┄</span> AI 待确认</span></span>
    </div>
    <div class="card" style="padding:0;position:relative">
      <div ref="el" style="height: calc(100vh - 190px); min-height: 460px" />
      <div v-if="picked.length === 2" class="card" style="position:absolute;right:14px;top:14px;width:300px">
        <b>{{ nameOf(picked[0]) }} → {{ nameOf(picked[1]) }}</b>
        <form class="row" style="margin-top:8px;flex-wrap:nowrap" @submit.prevent="addRel"><input v-model="kind" placeholder="关系名" required /><button class="primary" type="submit">连线</button></form>
      </div>
      <div v-if="sel" class="card" style="position:absolute;right:14px;top:14px;width:300px">
        <b>{{ nameOf(sel.source) }} → {{ nameOf(sel.target) }}：{{ sel.kind }}</b>
        <p class="small muted">{{ sel.description || '无说明' }}</p>
        <div class="row"><button v-if="!sel.confirmed" class="primary" @click="confirmRel">确认 AI 建议</button><button class="danger" @click="delRel">删除</button></div>
      </div>
    </div>
  </div>
</template>
