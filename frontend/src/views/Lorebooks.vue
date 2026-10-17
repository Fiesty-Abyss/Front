<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, Lorebooks, Worlds } from '../api'
import { guard } from '../toast'

const route = useRoute()
const books = ref([])
const worlds = ref([])
const cur = ref(null)
const testText = ref('')
const testRes = ref(null)
const filter = ref('')
const fileInput = ref(null)

async function load() { books.value = (await Lorebooks.list()).items }
onMounted(async () => {
  worlds.value = (await Worlds.list({ limit: 500 })).items
  await load()
  const id = Number(route.query.id) || books.value[0]?.id
  if (id) open(id)
})
async function open(id) { cur.value = await Lorebooks.get(id); testRes.value = null; if (testText.value) runTest() }
const worldName = (id) => worlds.value.find((w) => w.id === id)?.name
const activeIds = computed(() => new Set((testRes.value?.active || []).map((r) => r.entry_id)))
const skippedIds = computed(() => new Set((testRes.value?.skipped || []).map((r) => r.entry_id)))
const reasonOf = (id) => testRes.value?.active.find((r) => r.entry_id === id)?.reason
const entries = computed(() => (cur.value?.entries || []).filter((e) => !filter.value || [e.title, e.content, ...e.keys].join(' ').includes(filter.value)))

async function create() {
  const name = prompt('世界书名称')
  if (!name) return
  const b = await guard(() => Lorebooks.create({ name }), '已创建'); await load(); open(b.id)
}
async function fromWorld(wid) {
  if (!wid) return
  const b = await guard(() => api.post(`/api/lorebooks/from-world/${wid}`), '已从世界观生成'); await load(); open(b.id)
}
async function importFile(ev) {
  const f = ev.target.files[0]
  if (!f) return
  const form = new FormData(); form.append('file', f)
  const b = await guard(() => api.upload('/api/lorebooks/import', form), '已导入'); ev.target.value = ''; await load(); open(b.id)
}
async function saveBook(patch) { cur.value = await guard(() => Lorebooks.update(cur.value.id, patch)); load() }
async function removeBook() {
  if (!confirm(`删除世界书「${cur.value.name}」？`)) return
  await guard(() => Lorebooks.remove(cur.value.id), '已删除'); cur.value = null; await load(); if (books.value[0]) open(books.value[0].id)
}
const splitKeys = (s) => s.split(/[,，、\n]/).map((x) => x.trim()).filter(Boolean)
async function saveEntry(e, patch) {
  const r = await guard(() => api.patch(`/api/lore-entries/${e.id}`, patch))
  Object.assign(e, r)
  if (testText.value) runTest()
}
async function addEntry() {
  const r = await guard(() => api.post(`/api/lorebooks/${cur.value.id}/entries`, { title: '新条目', keys: [], content: '', insertion_order: (cur.value.entries.at(-1)?.insertion_order ?? 0) + 10 }))
  cur.value.entries.push(r); load()
}
async function removeEntry(e) {
  if (!confirm(`删除条目「${e.title || e.keys.join('、')}」？`)) return
  await guard(() => api.del(`/api/lore-entries/${e.id}`)); cur.value.entries = cur.value.entries.filter((x) => x.id !== e.id); load()
}
let timer
async function runTest() { testRes.value = testText.value.trim() ? await api.post(`/api/lorebooks/${cur.value.id}/test`, { text: testText.value }) : null }
watch(testText, () => { clearTimeout(timer); timer = setTimeout(runTest, 300) })
function exportBook(fmt) { window.location.href = `/api/lorebooks/${cur.value.id}/export?format=${fmt}` }
</script>
<template>
  <div class="grid" style="grid-template-columns: 260px 1fr; align-items:start">
    <aside class="card grid" style="gap:8px;align-content:start">
      <div class="row"><button class="primary" @click="create">＋ 新建</button><button class="ghost" @click="fileInput.click()">导入</button>
        <input ref="fileInput" type="file" accept=".json,.png" hidden @change="importFile" /></div>
      <select @change="fromWorld($event.target.value); $event.target.value = ''"><option value="">从世界观生成…</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }}</option></select>
      <div class="small muted">导入支持 SillyTavern 世界书 JSON、Character Card V2 的 character_book、带世界书的角色卡（JSON / PNG）。</div>
      <div v-for="b in books" :key="b.id" class="card book" :class="{ on: cur?.id === b.id }" @click="open(b.id)">
        <b>{{ b.name }}</b>
        <div class="small muted">{{ b.enabled }} / {{ b.entries }} 条启用<template v-if="b.world_id"> · ◍ {{ worldName(b.world_id) }}</template><template v-if="b.cards"> · ▤ {{ b.cards }} 张角色卡</template></div>
      </div>
    </aside>

    <div v-if="cur" class="grid" style="gap:14px">
      <section class="card grid" style="gap:10px">
        <div class="row"><input :value="cur.name" style="font-size:18px;font-weight:600;max-width:420px" @change="saveBook({ name: $event.target.value })" />
          <span class="spacer" /><button class="ghost small" @click="exportBook('v2')">导出 V2</button><button class="ghost small" @click="exportBook('st')">导出 SillyTavern</button>
          <button class="ghost small danger" @click="removeBook">删除</button></div>
        <input :value="cur.description" placeholder="说明（可选）" @change="saveBook({ description: $event.target.value || null })" />
        <div class="grid" style="grid-template-columns: 1.4fr 1fr 1fr auto; align-items:end">
          <label class="small">关联世界观 <span class="muted">（该世界观角色的对话自动启用）</span>
            <select :value="cur.world_id ?? ''" @change="saveBook({ world_id: $event.target.value ? Number($event.target.value) : null })">
              <option value="">不关联</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }}</option></select></label>
          <label class="small">扫描最近几条消息<input type="number" min="0" :value="cur.scan_depth" @change="saveBook({ scan_depth: Number($event.target.value) })" /></label>
          <label class="small">token 预算<input type="number" min="0" :value="cur.token_budget" @change="saveBook({ token_budget: Number($event.target.value) })" /></label>
          <label class="row small" style="padding-bottom:8px"><input type="checkbox" style="width:auto" :checked="cur.recursive" @change="saveBook({ recursive: $event.target.checked })" />递归激活</label>
        </div>
      </section>

      <section class="card grid" style="gap:8px">
        <div class="row"><b>命中测试</b><span class="small muted">输入一段对话，看看会激活哪些条目（不会发送给 AI）</span>
          <span v-if="testRes" class="spacer" /><span v-if="testRes" class="small">激活 <b>{{ testRes.active.length }}</b> 条 · 约 {{ testRes.tokens }} token<template v-if="testRes.skipped.length"> · <span style="color:#fca5a5">{{ testRes.skipped.length }} 条超出预算</span></template></span></div>
        <textarea v-model="testText" placeholder="例如：明天就是灯塔节了，我们去旧书店看看吧" style="min-height:54px" />
      </section>

      <section class="grid" style="gap:10px">
        <div class="row"><b>条目（{{ cur.entries.length }}）</b><input v-model="filter" placeholder="筛选" style="max-width:220px" /><span class="spacer" /><button class="ghost" @click="addEntry">＋ 添加条目</button></div>
        <div v-for="e in entries" :key="e.id" class="card entry" :class="{ hit: activeIds.has(e.id), skip: skippedIds.has(e.id), off: !e.enabled }">
          <div class="row" style="gap:8px">
            <label class="row small" style="gap:4px"><input type="checkbox" style="width:auto" :checked="e.enabled" @change="saveEntry(e, { enabled: $event.target.checked })" />启用</label>
            <input :value="e.title" placeholder="标题" style="max-width:240px;font-weight:600" @change="saveEntry(e, { title: $event.target.value })" />
            <span v-if="activeIds.has(e.id)" class="chip on">命中 · {{ reasonOf(e.id) }}</span>
            <span v-else-if="skippedIds.has(e.id)" class="chip" style="color:#fca5a5">命中但超出预算</span>
            <span class="spacer" />
            <div class="opts small">
              <label><input type="checkbox" :checked="e.constant" @change="saveEntry(e, { constant: $event.target.checked })" />常驻</label>
              <label><input type="checkbox" :checked="e.selective" @change="saveEntry(e, { selective: $event.target.checked })" />需要次关键词</label>
              <select :value="e.position" @change="saveEntry(e, { position: $event.target.value })"><option value="before_char">角色设定之前</option><option value="after_char">角色设定之后</option></select>
              <label>顺序<input type="number" :value="e.insertion_order" @change="saveEntry(e, { insertion_order: Number($event.target.value) })" /></label>
              <label>优先级<input type="number" :value="e.priority" @change="saveEntry(e, { priority: Number($event.target.value) })" /></label>
            </div>
            <button class="ghost small danger" title="删除条目" @click="removeEntry(e)">✕</button>
          </div>
          <div class="grid" style="grid-template-columns: 300px 1fr; gap:10px">
            <div class="grid" style="gap:6px;align-content:start">
              <label class="small">关键词 <span class="muted">逗号分隔，可写 /正则/</span><input class="mono" :value="e.keys.join(', ')" @change="saveEntry(e, { keys: splitKeys($event.target.value) })" /></label>
              <label v-if="e.selective" class="small">次关键词 <span class="muted">还需命中其一</span><input class="mono" :value="e.secondary_keys.join(', ')" @change="saveEntry(e, { secondary_keys: splitKeys($event.target.value) })" /></label>
            </div>
            <textarea :value="e.content" placeholder="命中时注入给 AI 的内容" style="min-height:58px" @change="saveEntry(e, { content: $event.target.value })" />
          </div>
        </div>
      </section>
    </div>
    <section v-else class="card empty">还没有世界书。新建一本、导入，或从世界观百科一键生成。</section>
  </div>
</template>
<style scoped>
.book { cursor: pointer; padding: 10px; }
.book.on { border-color: var(--accent); }
.entry { display: grid; gap: 8px; padding: 12px 14px; transition: border-color .2s, box-shadow .2s; }
.entry.hit { border-color: #fbbf24; box-shadow: 0 0 0 1px #fbbf2455 inset; }
.entry.skip { border-color: #f8717188; }
.entry.off { opacity: .55; }
.opts { display: flex; gap: 10px; align-items: center; flex-wrap: nowrap; }
.opts label { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.opts input[type=checkbox] { width: auto; }
.opts input[type=number] { width: 58px; padding: 4px 6px; }
.opts select { width: auto; padding: 4px 6px; }
</style>
