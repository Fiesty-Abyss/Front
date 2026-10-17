<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, Assets, Collections, LABELS, thumb, Works } from '../api'
import Modal from '../components/Modal.vue'
import { guard } from '../toast'

const route = useRoute()
const list = ref([])
const cur = ref(null)
const works = ref([])
const picking = ref(false)
const pf = reactive({ q: '', kind: '' })
const pool = ref([])
const chosen = ref([])
const drag = reactive({ kind: null, from: -1, over: -1 })

async function load() { list.value = (await Collections.list({ limit: 500 })).items }
onMounted(async () => {
  works.value = (await Works.list({ limit: 500 })).items
  await load()
  const want = Number(route.query.id)
  select(list.value.find((c) => c.id === want) ?? list.value[0] ?? null)
})
function select(c) { cur.value = c ? { ...c } : null }
async function refresh(c) {
  await load()
  select(list.value.find((x) => x.id === c.id) ?? c)
}
async function create() {
  const c = await guard(() => Collections.create({ name: '新收藏集', position: list.value.length }), '已创建')
  await refresh(c)
}
async function saveMeta() {
  const c = cur.value
  await guard(() => Collections.update(c.id, { name: c.name, description: c.description, work_id: c.work_id || null }), '已保存')
  refresh(c)
}
async function remove() {
  if (!confirm(`删除收藏集「${cur.value.name}」？素材本身不会被删除。`)) return
  await guard(() => Collections.remove(cur.value.id), '已删除')
  await load(); select(list.value[0] ?? null)
}
async function setCover(a) {
  const c = await guard(() => Collections.update(cur.value.id, { cover_asset_id: cur.value.cover_asset_id === a.id ? null : a.id }))
  refresh(c)
}
async function removeItem(a) { refresh(await guard(() => api.del(`/api/collections/${cur.value.id}/items/${a.id}`))) }

// ---- 拖拽排序（收藏集内容 / 收藏集本身） ----
function dragStart(kind, i) { drag.kind = kind; drag.from = i }
function dragOver(kind, i, e) { if (drag.kind === kind) { e.preventDefault(); drag.over = i } }
async function drop(kind, i) {
  if (drag.kind !== kind || drag.from < 0) return
  const arr = kind === 'item' ? [...cur.value.assets] : [...list.value]
  const [moved] = arr.splice(drag.from, 1)
  arr.splice(i, 0, moved)
  Object.assign(drag, { kind: null, from: -1, over: -1 })
  if (kind === 'item') {
    cur.value.assets = arr
    refresh(await guard(() => api.put(`/api/collections/${cur.value.id}/order`, { asset_ids: arr.map((a) => a.id) }), '已调整顺序'))
  } else {
    list.value = arr
    await guard(() => api.put('/api/collections/order', { collection_ids: arr.map((c) => c.id) }))
  }
}

async function openPicker() { chosen.value = []; picking.value = true; loadPool() }
async function loadPool() {
  const inCol = new Set(cur.value.assets.map((a) => a.id))
  pool.value = (await Assets.list({ ...pf, limit: 200 })).items.filter((a) => !inCol.has(a.id))
}
let t
watch(pf, () => { clearTimeout(t); t = setTimeout(loadPool, 200) })
function toggle(id) { chosen.value = chosen.value.includes(id) ? chosen.value.filter((x) => x !== id) : [...chosen.value, id] }
async function addChosen() {
  refresh(await guard(() => api.post(`/api/collections/${cur.value.id}/items`, { asset_ids: chosen.value }), `已加入 ${chosen.value.length} 项`))
  picking.value = false
}
const workName = (id) => works.value.find((w) => w.id === id)?.title
</script>

<template>
  <div class="grid" style="grid-template-columns: 300px 1fr; align-items:start">
    <aside class="card grid" style="gap:8px">
      <button class="primary" @click="create"><Ico g="＋" />新建收藏集</button>
      <p class="small muted" style="margin:0">拖动可调整收藏集顺序</p>
      <div v-for="(c, i) in list" :key="c.id" class="card row coll" draggable="true" style="padding:8px;flex-wrap:nowrap;cursor:pointer"
        :style="{ borderColor: cur?.id === c.id ? 'var(--accent)' : drag.kind === 'col' && drag.over === i ? 'var(--accent2)' : '' }"
        @click="select(c)" @dragstart="dragStart('col', i)" @dragover="dragOver('col', i, $event)" @drop="drop('col', i)">
        <div class="avatar" style="width:64px;height:64px" :style="c.effective_cover_id ? { backgroundImage: `url(${thumb(c.effective_cover_id)})` } : {}" />
        <div style="min-width:0"><b>{{ c.name }}</b><div class="small muted">{{ c.assets.length }} 项{{ c.work_id ? ' · ' + workName(c.work_id) : '' }}</div></div>
      </div>
    </aside>
    <section v-if="cur" class="grid">
      <div class="card row" style="flex-wrap:nowrap;align-items:flex-start">
        <div class="avatar" style="width:150px;height:150px" :style="cur.effective_cover_id ? { backgroundImage: `url(${thumb(cur.effective_cover_id)})` } : {}" />
        <div class="grid" style="flex:1">
          <div class="grid cols-2"><label class="field">名称<input v-model="cur.name" /></label><label class="field">关联作品<select v-model="cur.work_id"><option :value="null">无</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select></label></div>
          <label class="field">说明<textarea v-model="cur.description" style="min-height:50px" /></label>
          <div class="row"><span class="small muted">封面：{{ cur.cover_asset_id ? '手动指定' : '自动（第一项）' }}</span><span class="spacer" /><button class="danger" @click="remove">删除收藏集</button><button class="primary" @click="saveMeta">保存</button></div>
        </div>
      </div>
      <div class="card">
        <div class="row" style="margin-bottom:10px"><h2 style="margin:0">内容 · {{ cur.assets.length }} 项</h2><span class="small muted">拖动卡片排序，★ 设为封面</span><span class="spacer" /><button class="primary" @click="openPicker"><Ico g="＋" />添加素材</button></div>
        <div v-if="!cur.assets.length" class="empty">空收藏集，点右上角添加素材</div>
        <div v-reveal class="thumbgrid">
          <div v-for="(a, i) in cur.assets" :key="a.id" class="tile" draggable="true"
            :style="drag.kind === 'item' && drag.over === i ? { borderColor: 'var(--accent2)' } : {}"
            @dragstart="dragStart('item', i)" @dragover="dragOver('item', i, $event)" @drop="drop('item', i)">
            <div class="img" style="position:relative" :style="a.width ? { backgroundImage: `url(${thumb(a.id)})` } : {}">
              {{ a.width ? '' : '📖' }}
              <span class="badge" style="position:absolute;left:8px;top:8px;background:#000a;color:#fff">#{{ i + 1 }}</span>
              <span v-if="cur.effective_cover_id === a.id" class="badge" style="position:absolute;right:8px;top:8px;background:var(--accent2);color:#fff">封面</span>
            </div>
            <div class="meta"><div class="title">{{ a.title }}</div>
              <div class="row small" style="gap:6px"><span class="badge">{{ LABELS.assetKind[a.kind] }}</span><span class="spacer" /><a title="设为封面" @click="setCover(a)">{{ cur.cover_asset_id === a.id ? '★' : '☆' }}</a><a title="移出" @click="removeItem(a)"><Ico g="✕" /></a></div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
  <Modal v-if="picking" title="添加素材到收藏集" @close="picking = false">
    <div class="row" style="margin-bottom:10px;flex-wrap:nowrap"><input v-model="pf.q" placeholder="搜索" /><select v-model="pf.kind" style="width:140px"><option value="">全部类型</option><option v-for="(l, k) in LABELS.assetKind" :key="k" :value="k">{{ l }}</option></select></div>
    <div class="thumbgrid" style="grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));max-height:56vh;overflow:auto">
      <div v-for="a in pool" :key="a.id" class="tile" :style="chosen.includes(a.id) ? { borderColor: 'var(--accent)', outline: '2px solid var(--accent)' } : {}" @click="toggle(a.id)">
        <div class="img" :style="a.width ? { backgroundImage: `url(${thumb(a.id)})` } : {}">{{ a.width ? '' : '📖' }}</div>
        <div class="meta small"><div class="title">{{ a.title }}</div></div>
      </div>
    </div>
    <div class="row" style="margin-top:12px"><span class="muted">已选 {{ chosen.length }}</span><span class="spacer" /><button class="primary" :disabled="!chosen.length" @click="addChosen">加入</button></div>
  </Modal>
</template>
