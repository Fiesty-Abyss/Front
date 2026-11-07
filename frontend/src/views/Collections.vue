<script setup>
import AssetThumb from '../components/AssetThumb.vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, Assets, Collections, LABELS, thumb, Works } from '../api'
import { toggleSelection, reorderPage } from '../collectionSelection'
import Modal from '../components/Modal.vue'
import TagPicker from '../components/TagPicker.vue'
import { toast } from '../toast'

const route = useRoute()
const list = ref([]), listTotal = ref(0), cur = ref(null), works = ref([])
const items = ref([]), total = ref(0), loading = ref(false), busy = ref(false), error = ref('')
const cursors = ref([null]), pageIndex = ref(0), next = ref(null), selected = ref([])
const f = reactive({ q: '', kind: '', tag: [], min_stars: '', min_preference: '', date_from: '', date_to: '' })
const canReorder = computed(() => !loading.value && !busy.value && !Object.values(f).some((v) => Array.isArray(v) ? v.length : v !== ''))
const picking = ref(false), pool = ref([]), poolTotal = ref(0), poolPage = ref(0), chosen = ref([])
const pf = reactive({ q: '', kind: '' })
const editingBatch = ref(false), batch = reactive({ stars: '', preference: '', favorite: '', add_tag_ids: [] })
const drag = reactive({ kind: null, from: -1, over: -1 })
let sequence = 0, filterTimer, pickerTimer

async function loadList(more = false) {
  const r = await api.get('/api/collections/summaries', { limit: 100, offset: more ? list.value.length : 0 })
  list.value = more ? [...list.value, ...r.items] : r.items; listTotal.value = r.total
}
async function loadMembers() {
  if (!cur.value) return
  const request = ++sequence, id = cur.value.id
  loading.value = true; error.value = ''
  try {
    const r = await api.get(`/api/collections/${id}/members`, { ...f, limit: 60, cursor: cursors.value[pageIndex.value] })
    if (request !== sequence) return
    items.value = r.items; total.value = r.total; next.value = r.next_cursor
    cur.value.members_revision = r.members_revision
  } catch (e) {
    if (request !== sequence) return
    items.value = []; next.value = null; error.value = e.message
    if (e.status === 409) { cursors.value = [null]; pageIndex.value = 0; selected.value = [] }
  } finally { if (request === sequence) loading.value = false }
}
function resetPage() { ++sequence; cursors.value = [null]; pageIndex.value = 0; items.value = []; next.value = null; return loadMembers() }
function select(c) { ++sequence; cur.value = c ? { ...c } : null; selected.value = []; items.value = []; total.value = 0; resetPage() }
function turn(delta) {
  if (loading.value || busy.value) return
  if (delta > 0) { cursors.value = [...cursors.value.slice(0, pageIndex.value + 1), next.value] }
  pageIndex.value += delta; loadMembers()
}
onMounted(async () => {
  try {
    works.value = (await Works.list({ limit: 500 })).items
    await loadList()
    const want = Number(route.query.id)
    const target = list.value.find((c) => c.id === want) ?? (want ? await api.get(`/api/collections/${want}/summary`) : list.value[0])
    select(target ?? null)
  } catch (e) { error.value = e.message }
})
watch(f, () => { ++sequence; clearTimeout(filterTimer); loading.value = true; filterTimer = setTimeout(resetPage, 200) }, { deep: true })
watch(pf, () => { clearTimeout(pickerTimer); poolPage.value = 0; if (picking.value) pickerTimer = setTimeout(loadPool, 200) })
onBeforeUnmount(() => { ++sequence; clearTimeout(filterTimer); clearTimeout(pickerTimer) })

async function write(fn, message, clear = false) {
  if (busy.value || !cur.value) return
  busy.value = true
  const id = cur.value.id
  try {
    const result = await fn(id)
    if (cur.value?.id !== id) return
    if (result) cur.value = { ...result }
    if (clear) selected.value = []
    await loadList(); await resetPage()
    if (message) toast(message)
    return true
  } catch (e) {
    toast(e.message, true)
    if (e.status === 409 && cur.value?.id === id) {
      cur.value = await api.get(`/api/collections/${id}/summary`).catch(() => cur.value)
      selected.value = []; await resetPage()
    }
  } finally { busy.value = false }
}
async function create() {
  try { const c = await Collections.create({ name: '新收藏集', position: listTotal.value }); await loadList(); select(await api.get(`/api/collections/${c.id}/summary`)) }
  catch (e) { toast(e.message, true) }
}
function saveMeta() { const c = cur.value; write((id) => api.patch(`/api/collections/${id}/summary`, { name: c.name, description: c.description, work_id: c.work_id || null }), '已保存') }
async function remove() {
  if (busy.value || !confirm(`删除收藏集「${cur.value.name}」？素材本身不会被删除。`)) return
  busy.value = true
  try { await Collections.remove(cur.value.id); await loadList(); select(list.value[0] ?? null) }
  catch (e) { toast(e.message, true) } finally { busy.value = false }
}
function setCover(a) { write((id) => api.patch(`/api/collections/${id}/summary`, { cover_asset_id: cur.value.cover_asset_id === a.id ? null : a.id }), '封面已保存') }
function toggle(id) { try { selected.value = toggleSelection(selected.value, id) } catch (e) { toast(e.message, true) } }
function selectPage() { try { let s = selected.value; for (const a of items.value) if (!s.includes(a.id)) s = toggleSelection(s, a.id); selected.value = s } catch (e) { toast(e.message, true) } }
async function removeSelected() {
  if (!confirm(`从本收藏集移出所选 ${selected.value.length} 项？源文件和其他收藏集不受影响。`)) return
  await write((id) => api.patch(`/api/collections/${id}/members/batch`, { expected_revision: cur.value.members_revision, asset_ids: selected.value, remove: true }), '已移出；保留原文件', true)
}
async function saveBatch() {
  const body = { expected_revision: cur.value.members_revision, asset_ids: selected.value, add_tag_ids: batch.add_tag_ids }
  for (const field of ['stars', 'preference']) if (batch[field] !== '') body[field] = Number(batch[field])
  if (batch.favorite !== '') body.favorite = batch.favorite === 'true'
  if (await write((id) => api.patch(`/api/collections/${id}/members/batch`, body), '所选素材属性已保存', true)) editingBatch.value = false
}
function dragStart(kind, i) { if (kind === 'item' && !canReorder.value) return; drag.kind = kind; drag.from = i }
function dragOver(kind, i, e) { if (drag.kind === kind) { e.preventDefault(); drag.over = i } }
async function drop(kind, i) {
  if (drag.kind !== kind || drag.from < 0 || busy.value) return
  const from = drag.from; Object.assign(drag, { kind: null, from: -1, over: -1 })
  if (kind === 'item' && canReorder.value) {
    const ordered = reorderPage(items.value, from, i)
    await write((id) => api.put(`/api/collections/${id}/members/order`, { expected_revision: cur.value.members_revision, first_asset_id: items.value[0].id, asset_ids: ordered.map((a) => a.id) }), '本页顺序已保存，已回到第一页')
  } else if (kind === 'col' && list.value.length === listTotal.value) {
    try { const arr = reorderPage(list.value, from, i); await api.put('/api/collections/order', { collection_ids: arr.map((c) => c.id) }); await loadList() }
    catch (e) { toast(e.message, true) }
  }
}
let poolSequence = 0
async function loadPool() {
  const request = ++poolSequence
  try { const r = await Assets.list({ ...pf, limit: 60, offset: poolPage.value * 60 }); if (request === poolSequence && picking.value) { pool.value = r.items; poolTotal.value = r.total } }
  catch (e) { toast(e.message, true) }
}
function openPicker() { chosen.value = []; pool.value = []; picking.value = true; poolPage.value = 0; loadPool() }
function choose(id) { try { chosen.value = toggleSelection(chosen.value, id) } catch (e) { toast(e.message, true) } }
async function addChosen() {
  if (await write((id) => api.post(`/api/collections/${id}/members`, { expected_revision: cur.value.members_revision, asset_ids: chosen.value }), '已加入；已有成员自动跳过')) picking.value = false
}
const workName = (id) => works.value.find((w) => w.id === id)?.title
</script>

<template>
  <div class="grid collections-layout">
    <aside class="card grid" style="gap:8px">
      <button class="primary" :disabled="busy" @click="create">新建收藏集</button>
      <p class="small muted" style="margin:0">{{ listTotal }} 个收藏集 · 加载完整列表后可拖动排序</p>
      <button v-for="(c, i) in list" :key="c.id" class="card row coll" :draggable="!busy && list.length === listTotal" style="padding:8px;flex-wrap:nowrap;text-align:left"
        :aria-pressed="cur?.id === c.id" :style="{ borderColor: cur?.id === c.id ? 'var(--accent)' : '' }"
        :disabled="busy" @click="select(c)" @dragstart="dragStart('col', i)" @dragover="dragOver('col', i, $event)" @drop="drop('col', i)">
        <div class="avatar" style="width:64px;height:64px;flex-shrink:0" :style="c.effective_cover_id ? { backgroundImage: `url(${thumb(c.effective_cover_id)})` } : {}" />
        <div style="min-width:0"><b>{{ c.name }}</b><div class="small muted">{{ c.member_count }} 项{{ c.work_id ? ' · ' + workName(c.work_id) : '' }}</div></div>
      </button>
      <button v-if="list.length < listTotal" @click="loadList(true)">更多收藏集</button>
    </aside>
    <section v-if="cur" class="grid">
      <div class="card row collection-heading">
        <div class="avatar" style="width:150px;height:150px" :style="cur.effective_cover_id ? { backgroundImage: `url(${thumb(cur.effective_cover_id)})` } : {}" />
        <div class="grid collection-details">
          <div class="grid cols-2"><label class="field">名称<input v-model="cur.name" :disabled="busy" /></label><label class="field">关联作品<select v-model="cur.work_id" :disabled="busy"><option :value="null">无</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select></label></div>
          <label class="field">说明<textarea v-model="cur.description" :disabled="busy" style="min-height:50px" /></label>
          <div class="row"><span class="small muted">封面：{{ cur.cover_asset_id ? '手动指定' : '自动（第一项）' }}</span><span class="spacer" /><button class="danger" :disabled="busy" @click="remove">删除收藏集</button><button class="primary" :disabled="busy" @click="saveMeta">保存</button></div>
        </div>
      </div>
      <div class="card">
        <div class="row"><h2>内容 · {{ total }} / {{ cur.member_count }} 项</h2><span class="spacer" /><button :disabled="busy" @click="openPicker">添加素材</button></div>
        <form class="row collection-filters" aria-label="收藏成员筛选" @submit.prevent="resetPage">
          <label>搜索<input v-model="f.q" :disabled="busy" /></label>
          <label>类型<select v-model="f.kind" :disabled="busy"><option value="">全部</option><option v-for="(l, k) in LABELS.assetKind" :key="k" :value="k">{{ l }}</option></select></label>
          <label>最低星级<select v-model="f.min_stars" :disabled="busy"><option value="">不限</option><option v-for="n in 6" :key="n" :value="String(n - 1)">{{ n - 1 }} 星</option></select></label>
          <label>最低喜爱度<input v-model="f.min_preference" :disabled="busy" type="number" min="0" max="100" /></label>
          <label>起始日期<input v-model="f.date_from" :disabled="busy" type="date" /></label><label>结束日期<input v-model="f.date_to" :disabled="busy" type="date" /></label>
        </form>
        <details><summary>标签筛选（多选交集，包含子标签）</summary><TagPicker v-model="f.tag" :allow-create="false" /></details>
        <p class="small muted">{{ canReorder ? '可拖动本页卡片排序；其他页位置不变。' : '筛选或加载期间不能拖动排序。' }}跨页保留明确选择，单次最多 1000 项。</p>
        <div class="row"><button :disabled="loading || busy || !items.length" @click="selectPage">选择本页</button><button :disabled="busy" @click="selected = []">清空选择</button><span role="status">已选 {{ selected.length }} 项</span><button :disabled="busy || !selected.length" @click="editingBatch = true">批量编辑</button><button :disabled="busy || !selected.length" @click="removeSelected">移出所选</button></div>
        <p v-if="loading" role="status">正在加载本页…</p>
        <div v-if="error" class="notice" role="alert">{{ error }} <button @click="loadMembers">重新加载</button></div>
        <div v-else-if="!loading && !items.length" class="empty">{{ cur.member_count ? '没有符合筛选的素材' : '空收藏集，可添加已有素材' }}</div>
        <div class="thumbgrid" :aria-busy="loading">
          <div v-for="(a, i) in items" :key="a.id" class="tile" :draggable="canReorder"
            :style="selected.includes(a.id) ? { borderColor: 'var(--accent)' } : {}"
            @dragstart="dragStart('item', i)" @dragover="dragOver('item', i, $event)" @drop="drop('item', i)" @dragend="drag.kind = null">
            <AssetThumb :asset="a" style="position:relative"><span class="badge" style="position:absolute;left:8px;top:8px;background:#000a;color:white">#{{ a.position + 1 }}</span></AssetThumb>
            <div class="meta"><label><input type="checkbox" :checked="selected.includes(a.id)" :disabled="busy" :aria-label="`选择 ${a.title}`" @change="toggle(a.id)" /> {{ a.title }}</label>
              <div class="row small"><span>{{ LABELS.assetKind[a.kind] }}</span><span>{{ a.stars }}★ · {{ a.preference }}/100</span><span class="spacer" /><button :disabled="busy" :aria-label="`设为封面 ${a.title}`" @click="setCover(a)">{{ cur.cover_asset_id === a.id ? '★' : '☆' }}</button><router-link :to="`/assets?open=${a.id}`">详情</router-link></div>
            </div>
          </div>
        </div>
        <div class="row pagination"><button :disabled="loading || busy || pageIndex === 0" @click="turn(-1)">上一页</button><span>第 {{ pageIndex + 1 }} 页 · 本页 {{ items.length }} 项</span><button :disabled="loading || busy || !next" @click="turn(1)">下一页</button><button :disabled="busy || loading" @click="resetPage">回到第一页 / 刷新</button></div>
      </div>
    </section>
    <p v-else-if="error" role="alert">{{ error }}</p>
    <div v-else class="empty">创建收藏集，引用已有素材即可归档</div>
  </div>
  <Modal v-if="picking" title="添加素材到收藏集" @close="picking = false; ++poolSequence">
    <div class="row"><label>搜索<input v-model="pf.q" /></label><label>类型<select v-model="pf.kind"><option value="">全部类型</option><option v-for="(l, k) in LABELS.assetKind" :key="k" :value="k">{{ l }}</option></select></label></div>
    <p class="small muted">只加载当前 60 项，已有成员再次加入时自动跳过。</p>
    <div class="thumbgrid" style="grid-template-columns:repeat(auto-fill,minmax(120px,1fr));max-height:48vh;overflow:auto">
      <label v-for="a in pool" :key="a.id" class="tile"><AssetThumb :asset="a" /><span class="meta small"><input type="checkbox" :checked="chosen.includes(a.id)" @change="choose(a.id)" /> {{ a.title }}</span></label>
    </div>
    <div class="row"><button :disabled="poolPage === 0" @click="poolPage--; loadPool()">上一页</button><span>第 {{ poolPage + 1 }} 页</span><button :disabled="(poolPage + 1) * 60 >= poolTotal" @click="poolPage++; loadPool()">下一页</button><span>已选 {{ chosen.length }}</span><button class="primary" :disabled="busy || !chosen.length" @click="addChosen">加入</button></div>
  </Modal>
  <Modal v-if="editingBatch" title="批量编辑所选素材" @close="editingBatch = false">
    <p>将修改 {{ selected.length }} 项的共享素材属性；其他收藏集中的同一素材也会显示这些属性。不填写的字段保留原值。</p>
    <div class="row"><label>收藏<select v-model="batch.favorite"><option value="">不修改</option><option value="true">收藏</option><option value="false">取消收藏</option></select></label><label>星级<select v-model="batch.stars"><option value="">不修改</option><option v-for="n in 6" :key="n" :value="String(n - 1)">{{ n - 1 }} 星</option></select></label><label>喜爱度<input v-model="batch.preference" type="number" min="0" max="100" /></label></div>
    <p>追加标签（保留已有标签）</p><TagPicker v-model="batch.add_tag_ids" />
    <button class="primary" :disabled="busy" @click="saveBatch">保存所选</button>
  </Modal>
</template>

<style scoped>
.collections-layout{grid-template-columns:300px minmax(0,1fr);align-items:start}
.collections-layout>*{min-width:0}
.collections-layout aside>*{min-width:0;max-width:100%}
.coll{white-space:normal;overflow-wrap:anywhere}
.collection-heading{flex-wrap:nowrap;align-items:flex-start}
.collection-details{min-width:0;flex:1}
.collection-filters{align-items:end;margin-bottom:12px}
.collection-filters label{display:grid;gap:4px;flex:1 1 130px;min-width:0}
.collection-filters input,.collection-filters select{width:100%;min-width:0}
.tile input[type=checkbox]{width:auto}
.pagination{margin-top:16px}
@media(max-width:900px){.collections-layout{grid-template-columns:minmax(0,1fr)}.collection-heading{flex-wrap:wrap}.collection-details{flex-basis:260px}.collection-heading>.avatar{width:96px!important;height:96px!important}}
</style>
