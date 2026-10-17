<script setup>
import QuickSearch from '../components/QuickSearch.vue'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, Assets, Collections, LABELS, thumb, Works } from '../api'
import CGViewer from '../components/CGViewer.vue'
import Modal from '../components/Modal.vue'
import TagChips from '../components/TagChips.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard, toast } from '../toast'

const kind = ref('')
const items = ref([])
const cur = ref(null)
const cgs = ref([])
const assets = ref([])
const collections = ref([])
const editing = ref(null)
const viewing = ref(null)
const route = useRoute()
const chars = ref([])

async function load() { items.value = (await Works.list({ kind: kind.value, limit: 500 })).items }
onMounted(async () => {
  await load()
  const want = Number(route.query.id)
  const w = items.value.find((x) => x.id === want) ?? items.value.find((x) => x.kind === 'galgame') ?? items.value[0]
  if (w) select(w)
  if (route.query.view !== undefined) viewing.value = Number(route.query.view) || 0
})
async function select(w) {
  cur.value = w
  cgs.value = (await api.get(`/api/works/${w.id}/cg`)).groups
  chars.value = await api.get(`/api/works/${w.id}/characters`)
  assets.value = (await Assets.list({ work_id: w.id, limit: 500 })).items.filter((a) => a.kind !== 'cg')
  collections.value = (await Collections.list({ limit: 500 })).items.filter((c) => c.work_id === w.id)
}
function edit(w) { editing.value = w ? { ...w, tag_ids: w.tags.map((t) => t.id) } : { title: '', kind: 'galgame', tag_ids: [] } }
async function save() {
  const e = editing.value
  const body = { title: e.title, kind: e.kind, year: e.year || null, publisher: e.publisher, url: e.url, description: e.description, tag_ids: e.tag_ids }
  const saved = await guard(() => (e.id ? Works.update(e.id, body) : Works.create(body)), '已保存')
  editing.value = null
  await load()
  select(saved)
}
async function remove() {
  if (!confirm('删除这个作品条目？素材不会被删除。')) return
  await guard(() => Works.remove(editing.value.id), '已删除')
  editing.value = null; cur.value = null; load()
}
async function regroup() {
  const r = await guard(() => api.post(`/api/works/${cur.value.id}/cg/regroup`))
  toast(`重新识别：${r.groups} 组 / ${r.items} 张`)
  select(cur.value)
}
const cgTotal = () => cgs.value.reduce((n, g) => n + g.count, 0)
async function newCollection() {
  const name = prompt('收藏集名称')
  if (!name) return
  await guard(() => Collections.create({ name, work_id: cur.value.id }), '已创建')
  select(cur.value)
}
</script>
<template>
  <div class="grid" style="grid-template-columns: 280px 1fr">
    <aside class="card grid" style="align-content:start;gap:6px">
      <div class="row" style="flex-wrap:nowrap"><select v-model="kind" @change="load"><option value="">全部类型</option><option v-for="(l, k) in LABELS.workKind" :key="k" :value="k">{{ l }}</option></select><button class="primary" @click="edit(null)"><Ico g="＋" /></button></div>
      <div v-for="w in items" :key="w.id" class="card" style="cursor:pointer;padding:10px" :style="cur?.id === w.id ? { borderColor: 'var(--accent)' } : {}" @click="select(w)">
        <div class="row" style="gap:6px"><b>{{ w.title }}</b><span class="badge">{{ LABELS.workKind[w.kind] }}</span></div>
        <div class="small muted">{{ [w.year, w.publisher].filter(Boolean).join(' · ') }}</div>
      </div>
    </aside>
    <section v-if="cur" class="grid" style="align-content:start">
      <div class="card">
        <div class="row"><h2 style="margin:0">{{ cur.title }}</h2><span class="badge">{{ LABELS.workKind[cur.kind] }}</span><span class="spacer" /><a v-if="cur.url" class="btn" :href="cur.url" target="_blank" rel="noopener noreferrer">官网 ↗</a><QuickSearch :q="cur.title" kind="work" /><button @click="edit(cur)">编辑</button></div>
        <p class="muted">{{ cur.description }}</p>
        <TagChips :tags="cur.tags" show-cat />
      </div>
      <div v-if="chars.length" class="card">
        <h2 style="margin-top:0">登场角色 · {{ chars.length }}</h2>
        <div class="row" style="gap:14px">
          <RouterLink v-for="c in chars" :key="c.id" :to="`/characters/${c.id}`" class="row" style="gap:8px">
            <span class="avatar" style="width:40px;height:40px;border-radius:50%" :style="c.avatar_asset_id ? { backgroundImage: `url(${thumb(c.avatar_asset_id)})` } : {}" />
            <span><b>{{ c.name }}</b><div class="small muted">{{ c.role || '登场' }}</div></span>
          </RouterLink>
        </div>
      </div>
      <div class="card">
        <div class="row"><h2 style="margin:0">CG 档案 · {{ cgs.length }} 组 / {{ cgTotal() }} 张</h2><span class="spacer" />
          <button v-if="cgs.length" class="primary" @click="viewing = 0"><Ico g="▶" />鉴赏模式</button>
          <button v-if="cgs.length" @click="regroup">重新识别差分</button>
          <RouterLink class="btn" to="/import">批量导入 CG</RouterLink></div>
        <p class="small muted">同一张 CG 的差分会自动归为一组（如 ev01a / ev01b、ev03_01 / ev03_02、ev0101 / ev0102），点击进入鉴赏模式。</p>
        <div v-reveal class="thumbgrid" style="grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))">
          <div v-for="(g, i) in cgs" :key="g.key" class="tile" @click="viewing = i">
            <div class="img" style="aspect-ratio:16/9;position:relative" :style="{ backgroundImage: `url(${thumb(g.cover_id)})` }"><span v-if="g.count > 1" class="badge" style="position:absolute;right:8px;top:8px;background:#000a;color:#fff">差分 × {{ g.count }}</span></div>
            <div class="meta"><div class="title">{{ g.key }}</div><div class="small muted">{{ g.size }}</div></div>
          </div>
        </div>
        <div v-if="!cgs.length" class="empty">还没有 CG</div>
      </div>
      <div class="card">
        <div class="row"><h2 style="margin:0">收藏集</h2><span class="spacer" /><button @click="newCollection"><Ico g="＋" />新建收藏集</button></div>
        <RouterLink v-for="c in collections" :key="c.id" :to="{ path: '/collections', query: { id: c.id } }" class="row" style="margin-top:8px"><b>{{ c.name }}</b><span class="small muted">{{ c.assets.length }} 项 · {{ c.description }}</span></RouterLink>
        <div v-if="assets.length" class="small muted" style="margin-top:10px">关联素材：{{ assets.map((a) => a.title).join('、') }}</div>
      </div>
    </section>
  </div>
  <CGViewer v-if="viewing !== null && cgs.length" :groups="cgs" :start="viewing" :title="cur.title" @close="viewing = null" />
  <Modal v-if="editing" :title="editing.id ? '编辑作品' : '新建作品'" @close="editing = null">
    <div class="grid">
      <div class="grid cols-3">
        <label class="field" style="grid-column: span 2">标题<input v-model="editing.title" /></label>
        <label class="field">类型<select v-model="editing.kind"><option v-for="(l, k) in LABELS.workKind" :key="k" :value="k">{{ l }}</option></select></label>
        <label class="field">年份<input v-model.number="editing.year" type="number" /></label>
        <label class="field">发行 / 作者<input v-model="editing.publisher" /></label>
        <label class="field">链接<input v-model="editing.url" /></label>
      </div>
      <label class="field">简介<textarea v-model="editing.description" /></label>
      <TagPicker v-model="editing.tag_ids" />
      <div class="row"><button v-if="editing.id" class="danger" @click="remove">删除</button><span class="spacer" /><button class="primary" @click="save">保存</button></div>
    </div>
  </Modal>
</template>
