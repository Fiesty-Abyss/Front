<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, Assets, Generations, LABELS, Prompts, SDModels, thumb } from '../api'
import Modal from '../components/Modal.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard, toast } from '../toast'

const f = reactive({ q: '', tag: [] })
const items = ref([])
const initializing = ref(true), initializationError = ref('')
const cur = ref(null)
const cmp = ref(null)
const models = ref([])
const images = ref([])
const gen = reactive({ model_id: '', asset_id: '' })
const adding = ref(false)

async function load() { items.value = (await Prompts.list({ ...f, limit: 500 })).items }
const route = useRoute()
async function initialize() {
  initializing.value = true; initializationError.value = ''
  try {
  await load()
  const want = items.value.find((p) => p.id === Number(route.query.id))
  if (want || items.value.length) await select(want ?? items.value[items.value.length - 1])
  if (route.query.batch) { view.value = 'xy'; xy.batch = String(route.query.batch); loadXY() }
  else if (route.query.view === 'xy') { view.value = 'xy'; loadXY() }
  } catch (e) { initializationError.value = e.message || '资料加载失败'; if (cur.value) toast(initializationError.value, true) }
  finally { initializing.value = false }
}
onMounted(initialize)
let t
watch(f, () => { clearTimeout(t); t = setTimeout(load, 200) }, { deep: true })

async function select(p) {
  cur.value = p ? { ...p, tag_ids: p.tags.map((x) => x.id), paramsText: JSON.stringify(p.params, null, 2) } : { title: '', positive: '', negative: '', tag_ids: [], paramsText: '{}' }
  cmp.value = p ? await api.get(`/api/prompts/${p.id}/compare`) : null
  batches.value = p ? await api.get(`/api/prompts/${p.id}/batches`) : []
  grid.value = null
  Object.assign(xy, { batch: '', x: '', y: '' })
  if (p && view.value === 'xy') loadXY()
}
// ---------- 对比：差异高亮 / XY 网格 ----------
const view = ref('model')
const batches = ref([])
const grid = ref(null)
const xy = reactive({ batch: '', x: '', y: '' })
const big = ref(null)
const plabel = (k) => LABELS.param[k] ?? k
const fmtv = (v) => (v === undefined || v === null ? '—' : Array.isArray(v) ? v.join(', ') : String(v))
const flatItems = computed(() => (cmp.value?.groups || []).flatMap((g) => g.items))
const tableKeys = computed(() => (cmp.value?.diff_keys || []).filter((k) => k !== 'model'))
const modeOf = computed(() => {
  const out = {}
  for (const k of cmp.value?.diff_keys || []) {
    const c = {}
    for (const it of flatItems.value) if (it.norm[k] != null) c[fmtv(it.norm[k])] = (c[fmtv(it.norm[k])] || 0) + 1
    out[k] = Object.entries(c).sort((a, b) => b[1] - a[1])[0]?.[0]
  }
  return out
})
const commonText = computed(() => Object.entries(cmp.value?.common || {}).map(([k, v]) => `${plabel(k)} ${fmtv(v)}`).join(' · '))
async function loadXY(changedAxis = false) {
  if (!cur.value?.id) return
  const params = { batch: xy.batch || undefined }
  if (changedAxis || !xy.batch) { if (xy.x) params.x = xy.x; if (xy.y) params.y = xy.y }
  grid.value = await api.get(`/api/prompts/${cur.value.id}/xy`, params)
  xy.x = grid.value.x || ''; xy.y = grid.value.y || ''
}
function pickBatch() { xy.x = ''; xy.y = ''; loadXY() }
const batchLabel = (b) => `${new Date(/(Z|[+-]\d\d:\d\d)$/.test(b.created_at) ? b.created_at : b.created_at + 'Z').toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })} · ${Object.values(b.axes).map(plabel).join(' × ') || '单图'} · ${b.count} 张`
async function save() {
  const p = cur.value
  let params
  try { params = JSON.parse(p.paramsText || '{}') } catch { return toast('参数需要是 JSON', true) }
  const body = { title: p.title, positive: p.positive, negative: p.negative, notes: p.notes, params, tag_ids: p.tag_ids }
  const saved = await guard(() => (p.id ? Prompts.update(p.id, body) : Prompts.create(body)), '已保存')
  await load(); select(saved)
}
async function remove() {
  if (!confirm('删除提示词及其对比记录？')) return
  await guard(() => Prompts.remove(cur.value.id), '已删除'); cur.value = null; cmp.value = null; load()
}
const copy = (s) => navigator.clipboard?.writeText(s).then(() => toast('已复制'))
async function openAdd() {
  models.value = (await SDModels.list({ limit: 500 })).items
  images.value = (await Assets.list({ kind: 'ai_image', limit: 500 })).items
  adding.value = true
}
async function addGen() {
  await guard(() => Generations.create({ prompt_id: cur.value.id, model_id: gen.model_id || null, asset_id: gen.asset_id || null }), '已加入对比')
  adding.value = false
  cmp.value = await api.get(`/api/prompts/${cur.value.id}/compare`)
}
</script>
<template>
  <div class="grid prompt-layout">
    <aside class="card grid" style="align-content:start;gap:8px">
      <input v-model="f.q" placeholder="搜索提示词内容" />
      <button class="primary" :disabled="initializing" @click="select(null)"><Ico g="＋" />新建提示词</button>
      <div v-for="p in items" :key="p.id" class="card" style="cursor:pointer;padding:10px" :style="cur?.id === p.id ? { borderColor: 'var(--accent)' } : {}" @click="select(p)">
        <b>{{ p.title }}</b><div class="small muted mono" style="max-height:34px;overflow:hidden">{{ p.positive }}</div>
      </div>
    </aside>
    <section v-if="cur" class="grid" style="align-content:start">
      <div class="card grid">
        <label class="field">标题<input v-model="cur.title" /></label>
        <label class="field"><span class="row">正向提示词<span class="spacer" /><a class="small" @click="copy(cur.positive)">复制</a></span><textarea v-model="cur.positive" class="mono" /></label>
        <label class="field"><span class="row">反向提示词<span class="spacer" /><a class="small" @click="copy(cur.negative || '')">复制</a></span><textarea v-model="cur.negative" class="mono" style="min-height:50px" /></label>
        <div class="grid cols-2">
          <label class="field">参数（JSON：steps / sampler / cfg / seed / size）<textarea v-model="cur.paramsText" class="mono" /></label>
          <label class="field">备注<textarea v-model="cur.notes" /></label>
        </div>
        <TagPicker v-model="cur.tag_ids" />
        <div class="row"><button v-if="cur.id" class="danger" @click="remove">删除</button><span class="spacer" /><button class="primary" @click="save">保存</button></div>
      </div>
      <div v-if="cmp" class="card">
        <div class="row">
          <h2 style="margin:0">对比</h2>
          <span class="chip click" :class="{ on: view === 'model' }" style="padding:4px 12px" @click="view = 'model'">同一提示词 × 不同模型</span>
          <span class="chip click" :class="{ on: view === 'table' }" style="padding:4px 12px" @click="view = 'table'">参数差异表</span>
          <span class="chip click" :class="{ on: view === 'xy' }" style="padding:4px 12px" @click="view = 'xy'; loadXY()">XY 网格</span>
          <span class="spacer" />
          <RouterLink class="btn" :to="{ path: '/generate', query: { prompt_id: cur.id } }"><Ico g="✦" />用它出图</RouterLink>
          <button @click="openAdd"><Ico g="＋" />加入一张出图</button>
        </div>
        <div v-if="!cmp.groups.length" class="empty">还没有出图记录。把 AI 图上传到素材库后在这里关联模型，或者直接「用它出图」。</div>
        <template v-else-if="view === 'model'">
          <div class="diffbar small">
            <div v-if="cmp.diff_keys.length"><span class="muted">不同的参数</span> <span v-for="k in cmp.diff_keys" :key="k" class="chip hl">{{ plabel(k) }}</span></div>
            <div v-if="commonText"><span class="muted">相同的参数</span> <span class="mono">{{ commonText }}</span></div>
          </div>
          <div class="grid" :style="{ gridTemplateColumns: `repeat(${Math.max(cmp.groups.length, 1)}, 1fr)` }">
            <div v-for="(g, i) in cmp.groups" :key="i">
              <div class="row" style="margin:8px 0"><b>{{ g.model?.name ?? '未指定模型' }}</b><span v-if="g.model" class="badge">{{ g.model.base_model }}</span><span class="small muted">{{ g.items.length }} 张</span></div>
              <div class="grid" style="grid-template-columns: repeat(2, 1fr); gap:8px">
              <div v-for="it in g.items" :key="it.generation_id" class="tile" style="cursor:zoom-in" @click="it.asset && (big = it.asset)">
                <div class="img" :style="it.asset?.width ? { backgroundImage: `url(${thumb(it.asset.id)})` } : {}" />
                <div class="meta small">
                  <div class="row" style="gap:4px">
                    <span v-for="k in cmp.diff_keys.filter((k) => k !== 'model' && it.norm[k] != null)" :key="k" class="chip hl mono">{{ plabel(k) }} {{ fmtv(it.norm[k]) }}</span>
                  </div>
                  <div v-if="it.prompt_added.length || it.prompt_removed.length" class="mono" style="margin-top:4px">
                    <span v-for="t in it.prompt_added" :key="'a' + t" class="tok add">+ {{ t }}</span><span v-for="t in it.prompt_removed" :key="'r' + t" class="tok del">− {{ t }}</span>
                  </div>
                  <div v-if="it.notes" class="muted">{{ it.notes }}</div>
                </div>
              </div>
              </div>
            </div>
          </div>
        </template>
        <template v-else-if="view === 'table'">
          <div class="small muted" style="margin:10px 0">每一列是一个取值不同的参数；<span class="chip hl">高亮</span> 表示和这一列最常见的取值不一样，— 表示这张图没有记录该参数。</div>
          <div style="overflow:auto">
            <table class="ptable">
              <thead><tr><th /><th>模型</th><th v-for="k in tableKeys" :key="k">{{ plabel(k) }}</th><th>提示词变化</th></tr></thead>
              <tbody>
                <tr v-for="it in flatItems" :key="it.generation_id">
                  <td><div class="pthumb" :style="it.asset?.width ? { backgroundImage: `url(${thumb(it.asset.id)})` } : {}" @click="it.asset && (big = it.asset)" /></td>
                  <td class="small"><b>{{ it.norm.model ?? '—' }}</b></td>
                  <td v-for="k in tableKeys" :key="k" class="mono small"><span v-if="it.norm[k] == null" class="muted">—</span><span v-else :class="{ 'chip hl': fmtv(it.norm[k]) !== modeOf[k] }">{{ fmtv(it.norm[k]) }}</span></td>
                  <td class="mono small"><span v-for="t in it.prompt_added" :key="'a' + t" class="tok add">+ {{ t }}</span><span v-for="t in it.prompt_removed" :key="'r' + t" class="tok del">− {{ t }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
        <template v-else>
          <div class="row" style="margin:10px 0">
            <label class="row small" style="gap:6px">批次<select v-model="xy.batch" style="width:300px" @change="pickBatch"><option value="">全部出图（{{ cmp.groups.reduce((n, g) => n + g.items.length, 0) }} 张）</option><option v-for="b in batches" :key="b.batch" :value="b.batch">{{ batchLabel(b) }}</option></select></label>
            <label class="row small" style="gap:6px">X<select v-model="xy.x" style="width:130px" @change="loadXY(true)"><option v-for="a in grid?.axes || []" :key="a.key" :value="a.key">{{ plabel(a.key) }}</option><option v-if="xy.x && !(grid?.axes || []).some((a) => a.key === xy.x)" :value="xy.x">{{ plabel(xy.x) }}</option></select></label>
            <label class="row small" style="gap:6px">Y<select v-model="xy.y" style="width:130px" @change="loadXY(true)"><option value="">不分行</option><option v-for="a in (grid?.axes || []).filter((a) => a.key !== xy.x)" :key="a.key" :value="a.key">{{ plabel(a.key) }}</option></select></label>
            <span class="small muted">可选的轴 = 这些图之间取值不同的参数</span>
          </div>
          <div v-if="grid" class="xy" :style="{ gridTemplateColumns: `90px repeat(${grid.x_values.length}, minmax(110px, 200px))` }">
            <div class="corner small muted">{{ grid.y ? plabel(grid.y) : '' }} ＼ {{ plabel(grid.x) }}</div>
            <div v-for="xv in grid.x_values" :key="'h' + xv" class="head">{{ xv }}</div>
            <template v-for="(row, yi) in grid.cells" :key="yi">
              <div class="head side">{{ grid.y ? grid.y_values[yi] : '' }}</div>
              <div v-for="(cell, xi) in row" :key="xi" class="cell">
                <div v-if="cell[0]?.asset" class="img" :style="{ backgroundImage: `url(${thumb(cell[0].asset.id)})` }" :title="cell[0].asset.title" @click="big = cell[0].asset"><span v-if="cell.length > 1" class="badge more">+{{ cell.length - 1 }}</span></div>
                <div v-else class="img none small muted">—</div>
              </div>
            </template>
          </div>
        </template>
      </div>
    </section>
    <section v-else-if="initializing" class="card empty" role="status">正在读取资料…</section>
    <section v-else-if="initializationError" class="card empty" role="alert"><p>{{ initializationError }}</p><button @click="initialize">重新加载</button></section>
    <section v-else class="card empty"><h2>记录提示词与效果</h2><p>保存提示词后可手动关联模型和效果图，未配置生图服务也能使用。</p><button class="primary" @click="select(null)">记录第一条提示词</button></section>
  </div>
  <div v-if="big" class="modal-mask" style="cursor:zoom-out" @click="big = null"><div style="text-align:center"><img :src="`/api/assets/${big.id}/file`" style="max-width:90vw;max-height:84vh;border-radius:10px" /><div class="small" style="margin-top:8px">{{ big.title }}</div></div></div>
  <Modal v-if="adding" title="加入对比" @close="adding = false">
    <div class="grid cols-2">
      <label class="field">模型<select v-model="gen.model_id"><option value="">未指定</option><option v-for="m in models" :key="m.id" :value="m.id">{{ m.name }}</option></select></label>
      <label class="field">图片（素材库中的 AI 生成图）<select v-model="gen.asset_id"><option value="">无</option><option v-for="a in images" :key="a.id" :value="a.id">{{ a.title }}</option></select></label>
    </div>
    <div class="row" style="margin-top:12px"><span class="spacer" /><button class="primary" @click="addGen">加入</button></div>
  </Modal>
</template>
<style scoped>
.prompt-layout{grid-template-columns:300px minmax(0,1fr);align-items:start}
.prompt-layout>*{min-width:0}
@media(max-width:900px){.prompt-layout{grid-template-columns:minmax(0,1fr)}}
.diffbar { display: grid; gap: 6px; margin: 10px 0; padding: 8px 12px; border-radius: 8px; background: var(--panel2); }
.chip.hl { background: #fbbf2422; border-color: #fbbf2466; color: #fde68a; white-space: nowrap; }
.meta .chip { font-size: 10.5px; padding: 0 6px; }
.ptable td, .ptable th { padding: 6px 8px; white-space: nowrap; }
.pthumb { width: 46px; height: 58px; border-radius: 6px; background: var(--sunken) center/cover; cursor: zoom-in; }
.tok { display: inline-block; margin: 2px 4px 0 0; padding: 0 6px; border-radius: 5px; font-size: 11px; }
.tok.add { background: #34d39922; color: #6ee7b7; }
.tok.del { background: #f8717122; color: #fca5a5; text-decoration: line-through; }
.xy { display: grid; gap: 6px; align-items: center; }
.xy .head { text-align: center; font-weight: 600; font-size: 13px; color: #fde68a; }
.xy .side { text-align: right; padding-right: 6px; }
.xy .corner { text-align: right; padding-right: 6px; }
.xy .img { aspect-ratio: 4/5; border-radius: 8px; background: var(--sunken) center/cover; cursor: zoom-in; position: relative; border: 1px solid var(--line); }
.xy .img.none { display: grid; place-items: center; cursor: default; }
.xy .more { position: absolute; right: 6px; top: 6px; background: #000a; color: #fff; }
</style>
