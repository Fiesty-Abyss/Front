<script setup>
import { onMounted, ref } from 'vue'
import { Assets, Collections, fileUrl, LABELS, thumb, Works } from '../api'
import Modal from '../components/Modal.vue'
import TagChips from '../components/TagChips.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard } from '../toast'

const kind = ref('')
const items = ref([])
const cur = ref(null)
const cgs = ref([])
const assets = ref([])
const collections = ref([])
const editing = ref(null)
const viewing = ref(null)

async function load() { items.value = (await Works.list({ kind: kind.value, limit: 500 })).items }
onMounted(async () => { await load(); if (items.value.length) select(items.value.find((w) => w.kind === 'galgame') ?? items.value[0]) })
async function select(w) {
  cur.value = w
  cgs.value = (await Assets.list({ work_id: w.id, kind: 'cg', limit: 500 })).items
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
      <div class="row" style="flex-wrap:nowrap"><select v-model="kind" @change="load"><option value="">全部类型</option><option v-for="(l, k) in LABELS.workKind" :key="k" :value="k">{{ l }}</option></select><button class="primary" @click="edit(null)">＋</button></div>
      <div v-for="w in items" :key="w.id" class="card" style="cursor:pointer;padding:10px" :style="cur?.id === w.id ? { borderColor: 'var(--accent)' } : {}" @click="select(w)">
        <div class="row" style="gap:6px"><b>{{ w.title }}</b><span class="badge">{{ LABELS.workKind[w.kind] }}</span></div>
        <div class="small muted">{{ [w.year, w.publisher].filter(Boolean).join(' · ') }}</div>
      </div>
    </aside>
    <section v-if="cur" class="grid" style="align-content:start">
      <div class="card">
        <div class="row"><h2 style="margin:0">{{ cur.title }}</h2><span class="badge">{{ LABELS.workKind[cur.kind] }}</span><span class="spacer" /><button @click="edit(cur)">编辑</button></div>
        <p class="muted">{{ cur.description }}</p>
        <TagChips :tags="cur.tags" show-cat />
      </div>
      <div class="card">
        <div class="row"><h2 style="margin:0">CG 档案 · {{ cgs.length }} 张</h2><span class="spacer" /><RouterLink class="btn" :to="{ path: '/assets', query: { work_id: cur.id } }">到素材库上传 / 管理</RouterLink></div>
        <p class="small muted">上传时把“类型”选为 CG、“作品”选为本作，即会归档到这里。</p>
        <div class="thumbgrid" style="grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))">
          <div v-for="a in cgs" :key="a.id" class="tile" @click="viewing = a">
            <div class="img" style="aspect-ratio:16/9" :style="{ backgroundImage: `url(${thumb(a.id)})` }" />
            <div class="meta"><div class="title">{{ a.title }}</div></div>
          </div>
        </div>
        <div v-if="!cgs.length" class="empty">还没有 CG</div>
      </div>
      <div class="card">
        <div class="row"><h2 style="margin:0">收藏集</h2><span class="spacer" /><button @click="newCollection">＋ 新建收藏集</button></div>
        <div v-for="c in collections" :key="c.id" class="row" style="margin-top:8px"><b>{{ c.name }}</b><span class="small muted">{{ c.assets.length }} 项 · {{ c.description }}</span></div>
        <div v-if="assets.length" class="small muted" style="margin-top:10px">关联素材：{{ assets.map((a) => a.title).join('、') }}</div>
      </div>
    </section>
  </div>
  <Modal v-if="viewing" :title="viewing.title" @close="viewing = null"><img :src="fileUrl(viewing.id)" style="width:100%;border-radius:10px" /></Modal>
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
