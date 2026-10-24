<script setup>
import { computed, defineAsyncComponent, onMounted, reactive, ref, watch } from 'vue'
const ExtractionEvidence=defineAsyncComponent(()=>import('../components/ExtractionEvidence.vue'))
import { useRoute, useRouter } from 'vue-router'
import { api, Appearances, Assets, fileUrl, LABELS, thumb, Works } from '../api'
import Markdown from '../components/Markdown.vue'
import Modal from '../components/Modal.vue'
import QuickSearch from '../components/QuickSearch.vue'
import { guard } from '../toast'

const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)
const d = ref(null)
const works = ref([])
const appForm = reactive({ work_id: '', role: '' })
const picking = ref(false)
const pool = ref([])
const pq = ref('')
const chosen = ref([])
const viewing = ref(null)

async function load() {
  d.value = await api.get(`/api/characters/${id}/detail`)
  document.title = `${d.value.character.name} · 角色百科 · Front`
}
onMounted(async () => { await load(); works.value = (await Works.list({ limit: 500 })).items })
const c = computed(() => d.value?.character)
const tagsByCat = computed(() => {
  const g = {}
  for (const t of c.value?.tags ?? []) (g[t.category] ??= []).push(t)
  return g
})
const ENTRY_TITLES = { organization: '所属组织', event: '参与事件', location: '相关地点', item: '相关物品', concept: '相关概念' }

async function addAppearance() {
  if (!appForm.work_id) return
  await guard(() => Appearances.create({ character_id: id, work_id: Number(appForm.work_id), role: appForm.role || null }), '已添加出场作品')
  appForm.work_id = ''; appForm.role = ''
  load()
}
async function removeAppearance(a) { await guard(() => Appearances.remove(a.id)); load() }

async function loadPool() {
  const have = new Set(d.value.gallery.map((g) => g.id))
  pool.value = (await Assets.list({ q: pq.value, kind: 'drawing,ai_image,cg,reference,material', limit: 200 })).items.filter((a) => a.width && !have.has(a.id))
}
watch(pq, loadPool)
function openPicker() { chosen.value = []; picking.value = true; loadPool() }
async function addGallery() {
  await guard(() => api.post(`/api/characters/${id}/gallery`, { asset_ids: chosen.value }), `已加入 ${chosen.value.length} 张`)
  picking.value = false
  load()
}
async function removeGallery(a) { await guard(() => api.del(`/api/characters/${id}/gallery/${a.id}`)); load() }
async function setAvatar(a) { await guard(() => api.patch(`/api/characters/${id}`, { avatar_asset_id: a.id }), '已设为头像'); load() }
async function makeCard() {
  if (d.value.cards.length) return router.push({ path: '/cards', query: { id: d.value.cards[0].id } })
  const card = await guard(() => api.post(`/api/cards/from-character/${id}`), '已生成角色卡')
  router.push({ path: '/cards', query: { id: card.id } })
}
</script>

<template>
  <div v-if="d" class="grid">
    <div class="card row hero" style="flex-wrap:nowrap;align-items:flex-start;gap:22px">
      <div class="avatar" style="width:200px;height:260px;border-radius:14px" :style="c.avatar_asset_id ? { backgroundImage: `url(${thumb(c.avatar_asset_id)})` } : {}" />
      <div class="grid" style="flex:1;gap:10px">
        <div class="row" style="gap:10px"><h1 style="font-size:28px;margin:0">{{ c.name }}</h1><span v-if="c.alias" class="muted">{{ c.alias }}</span><span class="badge">{{ LABELS.gender[c.gender] }}</span></div>
        <div class="row small muted" style="gap:14px">
          <RouterLink v-if="d.world" :to="'/worlds?id=' + d.world.id">◍ {{ d.world.name }}</RouterLink>
          <span v-for="a in d.appearances.slice(0, 3)" :key="a.work.id">❖ {{ a.work.title }}<span v-if="a.role">（{{ a.role }}）</span></span>
        </div>
        <p style="margin:0;font-size:15px">{{ c.summary }}</p>
        <div class="grid" style="gap:6px">
          <div v-for="(list, cat) in tagsByCat" :key="cat" class="row small" style="gap:6px"><span class="muted" style="width:62px">{{ LABELS.tagCategory[cat] ?? cat }}</span><span v-for="t in list" :key="t.id" class="chip" :title="t.aliases?.length ? '别名：' + t.aliases.join('、') : ''">{{ t.name }}</span></div>
        </div>
        <div class="row" style="margin-top:6px">
          <RouterLink class="btn primary" :to="{ path: '/characters', query: { edit: c.id } }"><Ico g="✎" />编辑</RouterLink>
          <RouterLink v-if="d.world" class="btn" :to="{ path: '/graph', query: { world_id: d.world.id, focus: c.id } }"><Ico g="◈" />关系网</RouterLink>
          <button @click="makeCard"><Ico g="▤" />{{ d.cards.length ? '查看角色卡' : '生成角色卡' }}</button>
          <QuickSearch :q="c.name" kind="character" :alts="(c.alias || '').split(/[,，、/]/)" />
        </div>
      </div>
    </div>

    <div class="grid" style="grid-template-columns: 1.6fr 1fr; align-items:start">
      <div class="grid">
        <div class="card">
          <h2 style="margin-top:0">设定</h2>
          <Markdown v-if="c.profile" :source="c.profile" />
          <div v-else class="empty">还没有详细设定</div>
          <ExtractionEvidence kind="character" :entity-id="id"/>
        </div>
        <div class="card">
          <div class="row"><h2 style="margin:0">图集 · {{ d.gallery.length }}</h2><span class="spacer" /><button @click="openPicker"><Ico g="＋" />从素材库添加</button></div>
          <div v-if="!d.gallery.length" class="empty">还没有图片</div>
          <div v-reveal class="thumbgrid" style="margin-top:12px;grid-template-columns: repeat(auto-fill, minmax(150px, 1fr))">
            <div v-for="g in d.gallery" :key="g.id" class="tile">
              <div class="img" :style="{ backgroundImage: `url(${thumb(g.id)})` }" @click="viewing = g" />
              <div class="meta small row" style="gap:6px;flex-wrap:nowrap"><span class="title" style="flex:1">{{ g.title }}</span><a title="设为头像" @click="setAvatar(g)">☺</a><a title="移出图集" @click="removeGallery(g)"><Ico g="✕" /></a></div>
            </div>
          </div>
        </div>
      </div>
      <div class="grid">
        <div class="card">
          <h2 style="margin-top:0">关系 · {{ d.relations.length }}</h2>
          <RouterLink v-for="r in d.relations" :key="r.id" :to="`/characters/${r.other.id}`" class="row rel" style="flex-wrap:nowrap;padding:6px 0">
            <div class="avatar" style="width:36px;height:36px" :style="r.other.avatar_asset_id ? { backgroundImage: `url(${thumb(r.other.avatar_asset_id)})` } : {}" />
            <b style="white-space:nowrap">{{ r.other.name }}</b><span class="chip" style="white-space:nowrap">{{ r.kind }}</span><span v-if="!r.confirmed" class="badge ai" style="white-space:nowrap">AI 待确认</span>
            <span class="small muted" style="overflow:hidden;white-space:nowrap;text-overflow:ellipsis">{{ r.description }}</span>
          </RouterLink>
          <div v-if="!d.relations.length" class="muted small">暂无关系</div>
        </div>
        <div class="card">
          <h2 style="margin-top:0">出场作品</h2>
          <div v-for="a in d.appearances" :key="a.work.id + '-' + a.id" class="row" style="padding:4px 0">
            <RouterLink :to="{ path: '/works', query: { id: a.work.id } }"><b>{{ a.work.title }}</b></RouterLink><span class="badge">{{ LABELS.workKind[a.work.kind] }}</span><span v-if="a.role" class="chip">{{ a.role }}</span>
            <span class="spacer" /><a v-if="a.id" class="small muted" @click="removeAppearance(a)">移除</a>
          </div>
          <form class="row" style="margin-top:8px;flex-wrap:nowrap" @submit.prevent="addAppearance">
            <select v-model="appForm.work_id"><option value="">选择作品</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select>
            <input v-model="appForm.role" placeholder="身份：主角 / 配角…" style="width:140px" /><button type="submit">添加</button>
          </form>
        </div>
        <div v-for="(list, kind) in d.entries" :key="kind" class="card">
          <h2 style="margin-top:0">{{ ENTRY_TITLES[kind] ?? kind }}</h2>
          <RouterLink v-for="e in list" :key="e.id" :to="{ path: '/worlds', query: { id: d.world?.id, entry: e.id } }" class="grid" style="gap:2px;padding:6px 0;border-bottom:1px solid var(--line)">
            <div class="row" style="gap:8px"><b>{{ e.name }}</b><span v-if="e.role" class="chip">{{ e.role }}</span><span v-if="e.date_label" class="badge">{{ e.date_label }}</span></div>
            <span class="small muted">{{ e.summary }}</span>
          </RouterLink>
        </div>
      </div>
    </div>
  </div>

  <Modal v-if="picking" title="添加到图集" @close="picking = false">
    <input v-model="pq" placeholder="搜索素材" style="margin-bottom:10px" />
    <div class="thumbgrid" style="grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));max-height:56vh;overflow:auto">
      <div v-for="a in pool" :key="a.id" class="tile" :style="chosen.includes(a.id) ? { outline: '2px solid var(--accent)' } : {}" @click="chosen = chosen.includes(a.id) ? chosen.filter((x) => x !== a.id) : [...chosen, a.id]">
        <div class="img" :style="{ backgroundImage: `url(${thumb(a.id)})` }" /><div class="meta small"><div class="title">{{ a.title }}</div></div>
      </div>
    </div>
    <div class="row" style="margin-top:12px"><span class="muted">已选 {{ chosen.length }}</span><span class="spacer" /><button class="primary" :disabled="!chosen.length" @click="addGallery">加入图集</button></div>
  </Modal>
  <Modal v-if="viewing" :title="viewing.title" @close="viewing = null"><img :src="fileUrl(viewing.id)" style="width:100%;border-radius:10px" /></Modal>
</template>
