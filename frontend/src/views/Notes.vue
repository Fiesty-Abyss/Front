<script setup>
// 超级笔记本：左侧页面树，右侧块编辑器；笔记可以嵌入素材库里的任何文件，也可以互相链接。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Pin, PinOff, Trash2, ChevronRight, FilePlus2, Search, Clock, Link2, Paperclip, Tag } from 'lucide-vue-next'
import { api, LABELS, Notes, Works } from '../api'
import AssetPicker from '../components/AssetPicker.vue'
import AssetThumb from '../components/AssetThumb.vue'
import Modal from '../components/Modal.vue'
import NoteEditor from '../components/NoteEditor.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard, toast } from '../toast'

const editingTags = ref(false)

const route = useRoute()
const router = useRouter()
const tree = ref([])
const note = ref(null)
const refs = ref({ assets: [], backlinks: [] })
const works = ref([])
const filter = ref('')
const open = ref(new Set())
const saving = ref('')
const picking = ref(false)
const pickingNote = ref(false)
const iconPop = ref(false)
const editorRef = ref(null)
const ICONS = ['📝', '📓', '🗼', '🌊', '🌙', '⭐', '🎨', '🖌️', '🎧', '🎬', '🧊', '✨', '📚', '🗺️', '🏮', '🌸', '🔖', '💡', '🧩', '📌', '🎮', '🎼', '🪄', '🕯️']

async function loadTree() { tree.value = await api.get('/api/notes/tree') }
const byParent = computed(() => {
  const m = new Map()
  for (const n of tree.value) { const k = n.parent_id ?? 0; if (!m.has(k)) m.set(k, []); m.get(k).push(n) }
  return m
})
const flat = computed(() => {
  // 展开后的可见行（带缩进层级）；搜索时直接平铺匹配项
  if (filter.value.trim()) return tree.value.filter((n) => n.title.toLowerCase().includes(filter.value.trim().toLowerCase())).map((n) => ({ ...n, depth: 0 }))
  const out = []
  const walk = (pid, depth) => { for (const n of byParent.value.get(pid) || []) { out.push({ ...n, depth, kids: (byParent.value.get(n.id) || []).length }); if (open.value.has(n.id)) walk(n.id, depth + 1) } }
  walk(0, 0)
  return out
})
function toggle(id) { const s = new Set(open.value); s.has(id) ? s.delete(id) : s.add(id); open.value = s }
function expandTo(id) {
  const s = new Set(open.value); let n = tree.value.find((x) => x.id === id); s.add(id) // 打开的页面也展开它的子页面
  while (n?.parent_id) { s.add(n.parent_id); n = tree.value.find((x) => x.id === n.parent_id) }
  open.value = s
}

async function load(id) {
  if (!id) { note.value = null; return }
  const n = await Notes.get(id).catch(() => null)
  if (!n) { router.replace('/notes'); return }
  note.value = { ...n, tag_ids: n.tags.map((t) => t.id) }
  saving.value = ''
  expandTo(n.id)
  refs.value = await api.get(`/api/notes/${id}/refs`)
}
async function create(parent_id = null) {
  const n = await guard(() => Notes.create({ title: '无标题', icon: '📝', parent_id, content: '' }))
  await loadTree()
  if (parent_id) { const s = new Set(open.value); s.add(parent_id); open.value = s }
  router.push(`/notes/${n.id}`)
  await nextTick(); document.querySelector('.note-title')?.select()
}

let timer
watch(() => note.value && [note.value.title, note.value.icon, note.value.content, note.value.pinned, note.value.work_id, note.value.tag_ids.join(',')], (v, old) => {
  if (!old || !v || note.value?.id == null || v[0] === undefined) return
  if (old && route.params.id && Number(route.params.id) !== note.value.id) return
  saving.value = '保存中…'
  clearTimeout(timer)
  timer = setTimeout(save, 600)
})
async function save() {
  const n = note.value
  if (!n) return
  try {
    const r = await Notes.update(n.id, { title: n.title.trim() || '无标题', icon: n.icon, content: n.content, pinned: n.pinned, work_id: n.work_id || null, tag_ids: n.tag_ids })
    n.updated_at = r.updated_at
    n.tags = r.tags
    saving.value = '已保存'
    const t = tree.value.find((x) => x.id === n.id); if (t) Object.assign(t, { title: r.title, icon: r.icon, pinned: r.pinned })
    refs.value = await api.get(`/api/notes/${n.id}/refs`)
  } catch (e) { saving.value = '保存失败'; toast(e.message, true) }
}
async function remove() {
  const kids = (byParent.value.get(note.value.id) || []).length
  if (!confirm(kids ? `删除这页笔记和它的 ${kids} 个子页面？` : '删除这页笔记？')) return
  clearTimeout(timer)
  await guard(() => Notes.remove(note.value.id), '已删除')
  note.value = null
  await loadTree()
  router.push('/notes')
}
function pickAsset(a) { picking.value = false; editorRef.value?.insertAsset(a) }
function pickNote(n) { pickingNote.value = false; editorRef.value?.insertNoteLink(n) }
const crumbs = computed(() => {
  const out = []; let n = note.value && tree.value.find((x) => x.id === note.value.parent_id)
  while (n) { out.unshift(n); n = tree.value.find((x) => x.id === n.parent_id) }
  return out
})
const roots = computed(() => byParent.value.get(0) || [])
const when = (s) => (s ? new Date(s.endsWith('Z') || s.includes('+') ? s : s + 'Z').toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '')
const saveNow = (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); clearTimeout(timer); save() } }

onMounted(async () => {
  works.value = (await Works.list({ limit: 500 })).items
  await loadTree()
  await load(route.params.id ? Number(route.params.id) : null)
  window.addEventListener('keydown', saveNow)
})
onBeforeUnmount(() => { window.removeEventListener('keydown', saveNow); if (saving.value === '保存中…') { clearTimeout(timer); save() } })
watch(() => route.params.id, async (id) => {
  if (saving.value === '保存中…') { clearTimeout(timer); await save() }
  load(id ? Number(id) : null)
})
</script>

<template>
  <div class="nb">
    <aside class="nb-side card">
      <div class="row" style="flex-wrap:nowrap;gap:6px">
        <label class="nb-search"><Search :size="14" /><input v-model="filter" placeholder="筛选页面" /></label>
        <button class="primary iconbtn" title="新建笔记" @click="create()"><Plus :size="16" /></button>
      </div>
      <nav class="nb-tree">
        <div v-for="n in flat" :key="n.id" class="nb-row" :class="{ on: note?.id === n.id }" :style="{ paddingLeft: 6 + n.depth * 16 + 'px' }" @click="router.push(`/notes/${n.id}`)">
          <button class="nb-caret" :class="{ open: open.has(n.id), none: !n.kids }" :tabindex="n.kids ? 0 : -1" @click.stop="n.kids && toggle(n.id)"><ChevronRight :size="13" /></button>
          <span class="nb-ico">{{ n.icon || '📄' }}</span><span class="nb-name">{{ n.title }}</span>
          <Pin v-if="n.pinned" :size="11" class="faint" />
          <button class="nb-add ghost iconbtn" title="新建子页面" @click.stop="create(n.id)"><Plus :size="13" /></button>
        </div>
        <div v-if="!flat.length" class="small muted" style="padding:10px">{{ filter ? '没有匹配的页面' : '还没有笔记' }}</div>
      </nav>
    </aside>

    <section v-if="note" class="nb-main">
      <div class="nb-crumbs small faint">
        <RouterLink to="/notes">笔记本</RouterLink>
        <template v-for="c in crumbs" :key="c.id"><ChevronRight :size="12" /><RouterLink :to="`/notes/${c.id}`">{{ c.icon }} {{ c.title }}</RouterLink></template>
        <span class="spacer" /><span class="nb-save" :class="{ busy: saving === '保存中…' }">{{ saving || ' ' }}</span>
      </div>
      <article class="nb-page">
        <div class="nb-head">
          <div class="nb-iconwrap">
            <button class="nb-icon" title="更换图标" @click="iconPop = !iconPop">{{ note.icon || '📄' }}</button>
            <div v-if="iconPop" class="nb-iconpop" @mouseleave="iconPop = false">
              <button v-for="i in ICONS" :key="i" @click="note.icon = i; iconPop = false">{{ i }}</button>
            </div>
          </div>
          <input v-model="note.title" class="note-title" placeholder="无标题" aria-label="标题" @keydown.enter.prevent="editorRef?.focus()" />
          <div class="row small muted nb-props">
            <span class="row" style="gap:4px"><Clock :size="12" />{{ when(note.updated_at) }}</span>
            <select v-model="note.work_id" class="nb-select" aria-label="关联作品"><option :value="null">不关联作品</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select>
            <span class="spacer" />
            <button class="ghost small" @click="note.pinned = !note.pinned"><component :is="note.pinned ? PinOff : Pin" :size="13" />{{ note.pinned ? '取消置顶' : '置顶' }}</button>
            <button class="ghost small" @click="create(note.id)"><FilePlus2 :size="13" />子页面</button>
            <button class="ghost small danger" @click="remove"><Trash2 :size="13" />删除</button>
          </div>
          <div class="row nb-tagrow">
            <Tag :size="13" class="muted" />
            <span v-for="t in note.tags.filter((t) => note.tag_ids.includes(t.id))" :key="t.id" class="chip on">{{ t.name }}</span>
            <span v-if="!note.tag_ids.length" class="small faint">暂无标签</span>
            <button class="ghost small" @click="editingTags = !editingTags">{{ editingTags ? '收起' : '编辑标签' }}</button>
          </div>
          <TagPicker v-if="editingTags" v-model="note.tag_ids" class="nb-tags" />
        </div>
        <NoteEditor :key="note.id" ref="editorRef" v-model="note.content" @pick-asset="picking = true" @pick-note="pickingNote = true" />
      </article>
      <div v-if="refs.assets.length || refs.backlinks.length || (byParent.get(note.id) || []).length" class="nb-refs">
        <div v-if="(byParent.get(note.id) || []).length"><div class="eyebrow">子页面</div>
          <div class="row" style="gap:8px;margin-top:8px"><RouterLink v-for="c in byParent.get(note.id)" :key="c.id" :to="`/notes/${c.id}`" class="nb-chip">{{ c.icon || '📄' }} {{ c.title }}</RouterLink></div></div>
        <div v-if="refs.assets.length"><div class="eyebrow"><Paperclip :size="11" /> 这页用到的素材 · {{ refs.assets.length }}</div>
          <div class="nb-assets"><RouterLink v-for="a in refs.assets" :key="a.id" :to="`/assets?open=${a.id}`" class="nb-asset"><AssetThumb :asset="a" /><span class="small ellip">{{ a.title }}</span><span class="faint small">{{ LABELS.assetKind[a.kind] }}</span></RouterLink></div></div>
        <div v-if="refs.backlinks.length"><div class="eyebrow"><Link2 :size="11" /> 链接到这里的笔记</div>
          <div class="row" style="gap:8px;margin-top:8px"><RouterLink v-for="b in refs.backlinks" :key="b.id" :to="`/notes/${b.id}`" class="nb-chip">{{ b.icon || '📄' }} {{ b.title }}</RouterLink></div></div>
      </div>
    </section>

    <section v-else class="nb-main">
      <div class="nb-hero">
        <div class="eyebrow">NOTEBOOK</div>
        <h1>超级笔记本</h1>
        <p class="muted">设定、灵感、待办、读书笔记……什么都能记。输入 <span class="kbd">/</span> 插入标题、清单、表格；把图片、3D 模型、音乐、PDF 直接拖进页面，会自动存进素材库并嵌入。</p>
        <button class="primary" @click="create()"><Plus :size="15" />新建笔记</button>
      </div>
      <div v-reveal class="nb-cards">
        <RouterLink v-for="n in roots" :key="n.id" :to="`/notes/${n.id}`" class="card nb-card">
          <span class="nb-card-ico">{{ n.icon || '📄' }}</span><b>{{ n.title }}</b>
          <span class="small faint">{{ (byParent.get(n.id) || []).length ? `${byParent.get(n.id).length} 个子页面 · ` : '' }}{{ when(n.updated_at) }}</span>
        </RouterLink>
      </div>
    </section>

    <AssetPicker v-if="picking" @pick="pickAsset" @close="picking = false" />
    <Modal v-if="pickingNote" title="链接到笔记" @close="pickingNote = false">
      <div class="grid" style="gap:4px">
        <button v-for="n in tree.filter((x) => x.id !== note?.id)" :key="n.id" class="ghost" style="justify-content:flex-start" @click="pickNote(n)">{{ n.icon || '📄' }} {{ n.title }}</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.nb { display: grid; grid-template-columns: 252px minmax(0, 1fr); gap: 18px; align-items: start; }
.nb-side { position: sticky; top: 76px; padding: 10px; max-height: calc(100vh - 96px); display: flex; flex-direction: column; gap: 8px; }
.nb-search { display: flex; align-items: center; gap: 6px; flex: 1; padding: 0 10px; border-radius: 10px; background: var(--sunken); border: 1px solid var(--line); color: var(--faint); }
.nb-search input { border: 0; background: none; padding: 7px 0; box-shadow: none; }
.nb-tree { overflow: auto; display: grid; gap: 1px; margin: 0 -4px; }
.nb-row { display: flex; align-items: center; gap: 4px; padding: 4px 6px; border-radius: 8px; cursor: pointer; color: var(--muted); font-size: 13.5px; transition: background-color .12s var(--ease-out); }
.nb-row:hover { background: var(--panel2); color: var(--text); }
.nb-row.on { background: var(--accent-soft); color: var(--text); }
.nb-caret { width: 18px; height: 18px; padding: 0; border: 0; background: none; color: var(--faint); display: grid; place-items: center; transition: transform .15s var(--ease-out); flex: none; }
.nb-caret.open { transform: rotate(90deg); } .nb-caret.none { visibility: hidden; }
.nb-ico { width: 20px; text-align: center; flex: none; }
.nb-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nb-add { opacity: 0; width: 22px; height: 22px; padding: 0; } .nb-row:hover .nb-add { opacity: 1; }
.nb-main { min-width: 0; }
.nb-crumbs { display: flex; align-items: center; gap: 4px; margin: 2px 4px 10px; }
.nb-crumbs a { color: var(--faint); } .nb-crumbs a:hover { color: var(--text); }
.nb-save { font-size: 11.5px; transition: opacity .3s; } .nb-save.busy { color: var(--accent-hi); }
.nb-page { max-width: 860px; margin: 0 auto; padding: 34px 60px 10px; border-radius: var(--radius-lg); background: var(--panel); border: 1px solid var(--line); box-shadow: var(--shadow); }
.nb-head { margin-bottom: 18px; }
.nb-iconwrap { position: relative; display: inline-block; }
.nb-icon { font-size: 44px; line-height: 1; padding: 6px; border: 0; background: none; border-radius: 12px; }
.nb-icon:hover { background: var(--panel2); }
.nb-iconpop { position: absolute; z-index: 20; top: 100%; left: 0; display: grid; grid-template-columns: repeat(8, 34px); gap: 2px; padding: 8px; border-radius: 12px; background: var(--panel); border: 1px solid var(--line-strong); box-shadow: var(--shadow-pop); }
.nb-iconpop button { font-size: 19px; padding: 4px; border: 0; background: none; border-radius: 8px; } .nb-iconpop button:hover { background: var(--panel2); }
.note-title { width: 100%; font-size: 34px; font-weight: 700; letter-spacing: -.01em; border: 0; background: none; padding: 6px 0; box-shadow: none; color: var(--text); }
.note-title:focus { outline: none; box-shadow: none; }
.nb-props { gap: 10px; margin: 4px 0 8px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
.nb-select { width: auto; padding: 3px 8px; font-size: 12px; border-radius: 999px; }
.nb-tags :deep(.chip) { font-size: 11.5px; }
.nb-tagrow { gap: 6px; flex-wrap: wrap; margin-top: 2px; }
.nb-tagrow .chip { font-size: 11.5px; }
.nb-tagrow button { margin-left: 2px; }
.nb-refs { max-width: 860px; margin: 14px auto 0; display: grid; gap: 18px; padding: 18px 22px; border-radius: var(--radius-lg); background: var(--panel); border: 1px solid var(--line); }
.nb-assets { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px; margin-top: 8px; }
.nb-asset { display: grid; gap: 4px; color: var(--text); }
.nb-asset :deep(.img) { aspect-ratio: 1; border-radius: 10px; background-size: cover; background-position: center; overflow: hidden; box-shadow: 0 0 0 1px var(--line); display: flex; }
.nb-chip { padding: 5px 12px; border-radius: 999px; background: var(--panel2); border: 1px solid var(--line); color: var(--text); font-size: 13px; }
.nb-chip:hover { border-color: var(--accent); }
.nb-hero { padding: 26px 4px 22px; max-width: 640px; }
.nb-hero h1 { font-size: 34px; margin: 6px 0 8px; }
.nb-hero p { margin: 0 0 16px; line-height: 1.8; }
.kbd { font-family: ui-monospace, monospace; font-size: 12px; padding: 1px 6px; border-radius: 6px; border: 1px solid var(--line-strong); background: var(--panel2); }
.nb-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.nb-card { display: grid; gap: 4px; padding: 18px; color: var(--text); transition: border-color .15s var(--ease-out), transform .15s var(--ease-out); }
.nb-card:hover { border-color: color-mix(in oklab, var(--accent) 55%, transparent); transform: translateY(-1px); }
.nb-card-ico { font-size: 28px; margin-bottom: 6px; }
.ellip { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.danger { color: var(--danger); }
</style>
