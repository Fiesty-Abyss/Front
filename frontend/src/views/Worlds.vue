<script setup>
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
const WorldArchive=defineAsyncComponent(()=>import('../components/WorldArchive.vue'))
import { useRoute, useRouter } from 'vue-router'
import { api, Characters, LABELS, thumb, WorldEntries, Worlds } from '../api'
import EntryTree from '../components/EntryTree.vue'
import Markdown from '../components/Markdown.vue'
import Modal from '../components/Modal.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard, toast } from '../toast'

const route = useRoute()
const router = useRouter()
const items = ref([])
const cur = ref(null)
const chars = ref([])
const entries = ref([])
const timeline = ref([])
const busy = ref(false)
const tab = ref(route.query.tab ?? 'setting')
const editingEntry = ref(null)
const TABS = [['setting', '设定'], ['archive','项目档案'], ['location', '地点'], ['organization', '组织'], ['event', '时间线'], ['other', '物品 / 概念']]

async function load() { items.value = (await Worlds.list({ limit: 500 })).items }
onMounted(async () => {
  await load()
  let wantWorld = Number(route.query.id)
  if (!wantWorld && route.query.entry) wantWorld = (await WorldEntries.get(Number(route.query.entry)).catch(() => null))?.world_id
  const w = items.value.find((x) => x.id === wantWorld) ?? items.value[0]
  if (w) await select(w)
  if (route.query.entry) {
    const e = entries.value.find((x) => x.id === Number(route.query.entry))
    if (e) { tab.value = ['location', 'organization', 'event'].includes(e.kind) ? e.kind : 'other'; openEntry(e) }
  }
})
async function select(w) {
  cur.value = w ? { ...w, tag_ids: w.tags.map((t) => t.id) } : { name: '', summary: '', content: '', tag_ids: [] }
  if (!w) { tab.value = 'setting'; chars.value = []; entries.value = []; timeline.value = []; return }
  chars.value = (await Characters.list({ world_id: w.id, limit: 500 })).items
  await loadEntries()
}
async function loadEntries() {
  entries.value = (await WorldEntries.list({ world_id: cur.value.id, limit: 500 })).items
  timeline.value = await api.get(`/api/worlds/${cur.value.id}/timeline`)
}
const counts = computed(() => {
  const c = { location: 0, organization: 0, event: 0, other: 0 }
  for (const e of entries.value) c[['location', 'organization', 'event'].includes(e.kind) ? e.kind : 'other']++
  return c
})
const locationTree = computed(() => {
  const locs = entries.value.filter((e) => e.kind === 'location').map((e) => ({ ...e, children: [] }))
  const byId = Object.fromEntries(locs.map((l) => [l.id, l]))
  const roots = []
  for (const l of locs) (byId[l.parent_id] ? byId[l.parent_id].children : roots).push(l)
  return roots
})
const ofKind = (k) => entries.value.filter((e) => (k === 'other' ? ['item', 'concept'].includes(e.kind) : e.kind === k))
const charOf = (id) => chars.value.find((c) => c.id === id)
const entryName = (id) => entries.value.find((e) => e.id === id)?.name

async function save() {
  const w = cur.value
  const body = { name: w.name, summary: w.summary, content: w.content, tag_ids: w.tag_ids }
  const saved = await guard(() => (w.id ? Worlds.update(w.id, body) : Worlds.create(body)), '已保存')
  await load()
  select(saved)
}
async function remove() {
  if (!confirm(`删除世界观「${cur.value.name}」？其下的地点 / 组织 / 事件条目会一并删除，角色不会被删除。`)) return
  await guard(() => Worlds.remove(cur.value.id), '已删除')
  cur.value = null
  load()
}
async function aiSuggest() {
  busy.value = true
  try {
    const r = await api.post(`/api/ai/worlds/${cur.value.id}/suggest-relations`)
    toast(`AI 提出了 ${r.created.length} 条关系建议，请到关系网确认`)
    router.push({ path: '/graph', query: { world_id: cur.value.id } })
  } catch (e) { toast(e.message, true) } finally { busy.value = false }
}

function newEntry(kind) {
  editingEntry.value = { world_id: cur.value.id, kind, name: '', summary: '', content: '', parent_id: null, date_label: '', sort_key: null, tag_ids: [], characters: [] }
}
function openEntry(e) {
  editingEntry.value = { ...e, tag_ids: e.tags.map((t) => t.id), characters: e.links.map((l) => ({ ...l })) }
}
async function saveEntry() {
  const e = editingEntry.value
  const body = {
    world_id: e.world_id, kind: e.kind, name: e.name, summary: e.summary, content: e.content,
    parent_id: e.parent_id || null, date_label: e.date_label || null,
    sort_key: e.sort_key === '' || e.sort_key == null ? null : Number(e.sort_key),
    tag_ids: e.tag_ids, characters: e.characters.filter((c) => c.character_id).map((c) => ({ character_id: Number(c.character_id), role: c.role || null })),
  }
  await guard(() => (e.id ? WorldEntries.update(e.id, body) : WorldEntries.create(body)), '已保存')
  editingEntry.value = null
  loadEntries()
}
async function removeEntry() {
  if (!confirm(`删除条目「${editingEntry.value.name}」？`)) return
  await guard(() => WorldEntries.remove(editingEntry.value.id), '已删除')
  editingEntry.value = null
  loadEntries()
}
const parentOptions = computed(() => {
  const e = editingEntry.value
  if (!e) return []
  // 事件的“上级”是发生地点；其他条目的上级是同类或地点
  return entries.value.filter((x) => x.id !== e.id && (e.kind === 'event' ? x.kind === 'location' : ['location', e.kind].includes(x.kind)))
})
</script>
<template>
  <div class="grid world-layout">
    <aside class="card grid" style="align-content:start;gap:6px">
      <button class="primary" @click="select(null)"><Ico g="＋" />新建世界观</button>
      <div v-for="w in items" :key="w.id" class="card" style="cursor:pointer;padding:10px" :style="cur?.id === w.id ? { borderColor: 'var(--accent)' } : {}" @click="select(w)">
        <b>{{ w.name }}</b><div class="small muted">{{ w.summary?.slice(0, 40) }}</div>
      </div>
    </aside>
    <section v-if="cur" class="grid" style="align-content:start">
      <div v-if="cur.id" class="row">
        <span v-for="[k, l] in TABS" :key="k" class="chip click" :class="{ on: tab === k }" style="padding:5px 14px;font-size:13px" @click="tab = k">{{ l }}<template v-if="counts[k] != null"> · {{ counts[k] }}</template></span>
        <span class="spacer" />
        <a class="btn" :href="`/api/exports/encyclopedia?world_id=${cur.id}`" download title="只导出已保存的百科文字，不包含媒体文件，也不是整库备份">导出当前百科 · Markdown ZIP</a>
        <span class="small muted">角色 {{ chars.length }}</span>
      </div>

      <div v-if="tab === 'setting' || !cur.id" class="card grid">
        <label class="field">名称<input v-model="cur.name" /></label>
        <label class="field">概要<textarea v-model="cur.summary" /></label>
        <label class="field">设定正文（Markdown，AI 关系识别会阅读这里）<textarea v-model="cur.content" style="min-height:200px" /></label>
        <TagPicker v-model="cur.tag_ids" />
        <div v-if="cur.id">
          <div class="small muted" style="margin-bottom:6px">此世界观下的角色（{{ chars.length }}）</div>
          <div class="row"><RouterLink v-for="c in chars" :key="c.id" :to="`/characters/${c.id}`" class="chip">{{ c.name }}</RouterLink></div>
        </div>
        <div class="row">
          <button v-if="cur.id" class="danger" @click="remove">删除</button>
          <RouterLink v-if="cur.id" class="btn" :to="{ path: '/graph', query: { world_id: cur.id } }">查看关系网</RouterLink>
          <button v-if="cur.id" :disabled="busy" @click="aiSuggest">{{ busy ? 'AI 分析中…' : '✦ AI 识别角色关系' }}</button>
          <span class="spacer" /><button class="primary" @click="save">保存</button>
        </div>
      </div>

      <WorldArchive v-else-if="tab==='archive'" :key="cur.id" :world-id="cur.id"/>
      <div v-else-if="tab === 'location'" class="card">
        <div class="row" style="margin-bottom:8px"><h2 style="margin:0">地点</h2><span class="small muted">层级：城市 › 街区 › 建筑……</span><span class="spacer" /><button class="primary" @click="newEntry('location')"><Ico g="＋" />新地点</button></div>
        <EntryTree :nodes="locationTree" @open="openEntry" />
        <div v-if="!locationTree.length" class="empty">还没有地点</div>
      </div>

      <div v-else-if="tab === 'organization'" class="grid">
        <div class="row"><span class="spacer" /><button class="primary" @click="newEntry('organization')"><Ico g="＋" />新组织</button></div>
        <div class="grid cols-2">
          <div v-for="o in ofKind('organization')" :key="o.id" class="card" style="cursor:pointer" @click="openEntry(o)">
            <div class="row"><b style="font-size:15px">{{ o.name }}</b><span v-if="o.parent_id" class="small muted">@ {{ entryName(o.parent_id) }}</span></div>
            <p class="small muted">{{ o.summary }}</p>
            <div class="row" style="gap:8px">
              <span v-for="l in o.links" :key="l.character_id" class="row small" style="gap:5px">
                <span class="avatar" style="width:26px;height:26px;border-radius:50%" :style="charOf(l.character_id)?.avatar_asset_id ? { backgroundImage: `url(${thumb(charOf(l.character_id).avatar_asset_id)})` } : {}" />{{ charOf(l.character_id)?.name }}<span v-if="l.role" class="muted">· {{ l.role }}</span>
              </span>
            </div>
          </div>
        </div>
        <div v-if="!ofKind('organization').length" class="card empty">还没有组织</div>
      </div>

      <div v-else-if="tab === 'event'" class="card">
        <div class="row" style="margin-bottom:12px"><h2 style="margin:0">时间线</h2><span class="small muted">按“排序值”从早到晚，未填写的排在最后</span><span class="spacer" /><button class="primary" @click="newEntry('event')"><Ico g="＋" />新事件</button></div>
        <div class="timeline">
          <div v-for="e in timeline" :key="e.id" class="tl-item" @click="openEntry(entries.find((x) => x.id === e.id))">
            <div class="tl-date">{{ e.date_label || '时间未定' }}</div>
            <div class="tl-dot" />
            <div class="tl-body card">
              <div class="row"><b style="font-size:15px">{{ e.name }}</b><span v-if="e.place" class="small muted">📍 {{ e.place.name }}</span></div>
              <p class="small muted" style="margin:6px 0">{{ e.summary }}</p>
              <div class="row" style="gap:8px">
                <RouterLink v-for="c in e.characters" :key="c.id" :to="`/characters/${c.id}`" class="row small" style="gap:5px" @click.stop>
                  <span class="avatar" style="width:24px;height:24px;border-radius:50%" :style="c.avatar_asset_id ? { backgroundImage: `url(${thumb(c.avatar_asset_id)})` } : {}" />{{ c.name }}<span v-if="c.role" class="muted">· {{ c.role }}</span>
                </RouterLink>
              </div>
            </div>
          </div>
        </div>
        <div v-if="!timeline.length" class="empty">还没有事件</div>
      </div>

      <div v-else class="grid">
        <div class="row"><span class="spacer" /><button @click="newEntry('concept')"><Ico g="＋" />新概念</button><button class="primary" @click="newEntry('item')"><Ico g="＋" />新物品</button></div>
        <div class="grid cols-3">
          <div v-for="o in ofKind('other')" :key="o.id" class="card" style="cursor:pointer" @click="openEntry(o)">
            <div class="row"><b>{{ o.name }}</b><span class="badge">{{ LABELS.entryKind[o.kind] }}</span></div>
            <p class="small muted">{{ o.summary }}</p>
          </div>
        </div>
        <div v-if="!ofKind('other').length" class="card empty">还没有物品或概念</div>
      </div>
    </section>
  </div>

  <Modal v-if="editingEntry" :title="(editingEntry.id ? '编辑' : '新建') + LABELS.entryKind[editingEntry.kind]" @close="editingEntry = null">
    <div class="grid">
      <div class="grid cols-3">
        <label class="field" style="grid-column: span 2">名称<input v-model="editingEntry.name" /></label>
        <label class="field">类型<select v-model="editingEntry.kind"><option v-for="(l, k) in LABELS.entryKind" :key="k" :value="k">{{ l }}</option></select></label>
        <label class="field">{{ editingEntry.kind === 'event' ? '发生地点' : '上级' }}<select v-model="editingEntry.parent_id"><option :value="null">无</option><option v-for="p in parentOptions" :key="p.id" :value="p.id">{{ LABELS.entryKind[p.kind] }} · {{ p.name }}</option></select></label>
        <template v-if="editingEntry.kind === 'event'">
          <label class="field">时间（显示用）<input v-model="editingEntry.date_label" placeholder="灯塔历 302 年 · 秋" /></label>
          <label class="field">排序值（数字，越小越早）<input v-model="editingEntry.sort_key" type="number" step="any" /></label>
        </template>
      </div>
      <label class="field">简介<input v-model="editingEntry.summary" /></label>
      <div class="grid cols-2">
        <label class="field">正文（Markdown）<textarea v-model="editingEntry.content" class="mono" style="min-height:150px" /></label>
        <div class="field">预览<div class="card" style="background:var(--panel2);min-height:150px;max-height:240px;overflow:auto;padding:8px 12px"><Markdown :source="editingEntry.content || ''" /></div></div>
      </div>
      <div class="field">相关角色
        <div v-for="(l, i) in editingEntry.characters" :key="i" class="row" style="flex-wrap:nowrap;margin-bottom:6px">
          <select v-model="l.character_id"><option v-for="c in chars" :key="c.id" :value="c.id">{{ c.name }}</option></select>
          <input v-model="l.role" placeholder="身份 / 角色：会长、成员、目击者…" /><button class="ghost danger" @click="editingEntry.characters.splice(i, 1)"><Ico g="✕" /></button>
        </div>
        <button style="width:max-content" @click="editingEntry.characters.push({ character_id: chars[0]?.id, role: '' })"><Ico g="＋" />添加角色</button>
      </div>
      <TagPicker v-model="editingEntry.tag_ids" />
      <div class="row"><button v-if="editingEntry.id" class="danger" @click="removeEntry">删除</button><span class="spacer" /><button class="primary" @click="saveEntry">保存</button></div>
    </div>
  </Modal>
</template>

<style scoped>
.world-layout{grid-template-columns:220px minmax(0,1fr);align-items:start}
.world-layout>section{min-width:0}
@media(max-width:1100px){.world-layout{grid-template-columns:minmax(0,1fr)}}
</style>
<style scoped>
.timeline { position: relative; padding-left: 4px; }
.timeline::before { content: ''; position: absolute; left: 150px; top: 6px; bottom: 6px; width: 2px; background: linear-gradient(var(--accent), var(--accent2)); opacity: .6; }
.tl-item { display: grid; grid-template-columns: 138px 26px 1fr; align-items: start; margin-bottom: 14px; cursor: pointer; }
.tl-date { text-align: right; padding-top: 12px; font-size: 13px; color: var(--muted); }
.tl-dot { width: 14px; height: 14px; border-radius: 50%; background: var(--accent2); margin: 14px 0 0 6px; box-shadow: 0 0 0 4px var(--accent-soft); z-index: 1; }
.tl-body { padding: 12px 14px; }
.tl-item:hover .tl-body { border-color: var(--accent); }
</style>
