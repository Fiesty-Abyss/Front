<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { api } from '../api'
import { linkKinds, memoryKinds, reviewNames, scopeNames, sourceLink, sourcePayload } from '../soulDisplay'

const VersionPanel = defineAsyncComponent(() => import('../components/VersionPanel.vue'))
const base = '/api/souls'
const page = ref({ items: [], total: 0 }), offset = ref(0), filter = ref(''), inactive = ref(false)
const cur = ref(null), worlds = ref([]), busy = ref(false), error = ref(''), notice = ref('')
const newOpen = ref(false), newName = ref(''), newWorld = ref(''), newNotes = ref('')
const linkKind = ref('card'), linkQuery = ref(''), linkOptions = ref([]), linkId = ref('')
const memories = ref({ items: [], total: 0 }), memOffset = ref(0), memQuery = ref(''), memKind = ref(''), memReview = ref('')
const selected = ref(null), edited = ref(''), conflictNote = ref(''), showHistory = ref(false)
const draft = ref({ kind: 'suggestion', content: '', scope: 'character', session_id: '', branch_head_id: '', source: 'manual', message_id: '', note: '', importance: 50 })
const sourceRows = ref([]), recalled = ref(null), recallQuery = ref(''), recallSession = ref(''), recallHead = ref(''), budget = ref(4000)
const exportPage = ref(null)
const savedSoul = ref('')
const pendingOpen = ref(null)
let disposed = false, opening = 0
const validLinks = computed(() => (cur.value?.links || []).filter(x => x.active && !x.diagnostic))
const chats = computed(() => validLinks.value.filter(x => x.kind === 'chat'))
const entitySources = computed(() => validLinks.value.filter(x => x.kind !== 'chat'))
const soulText = () => cur.value ? JSON.stringify([cur.value.name, cur.value.notes]) : ''
const memoryDirty = computed(() => !!selected.value && (edited.value !== selected.value.content || conflictNote.value !== selected.value.conflict_note))
const dirty = computed(() => !!draft.value.content || memoryDirty.value || soulText() !== savedSoul.value)
onBeforeRouteLeave(() => !dirty.value || window.confirm('有未保存的记忆草稿，确定离开？'))
function leaving(e) { if (dirty.value) { e.preventDefault(); e.returnValue = '' } }
onBeforeUnmount(() => { disposed = true; opening++; window.removeEventListener('beforeunload', leaving) })
async function run(fn) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await fn() } catch (e) { if (!disposed) error.value = e.message }
  finally { if (!disposed) busy.value = false }
}
async function load() {
  if (disposed) return
  const data = await api.get(base, { q: filter.value, offset: offset.value, limit: 25, include_inactive: inactive.value })
  if (!disposed) page.value = data
}
async function loadMemories() {
  const id = cur.value.id
  const data = await api.get(`${base}/${id}/memories`, { q: memQuery.value, kind: memKind.value, review: memReview.value, offset: memOffset.value, include_inactive: true })
  if (!disposed && cur.value?.id === id) memories.value = data
}
async function open(id, force = false) {
  if (!force && dirty.value) { pendingOpen.value = id; return }
  pendingOpen.value = null
  const seq = ++opening
  const data = await api.get(`${base}/${id}`)
  if (disposed || seq !== opening) return
  cur.value = data; savedSoul.value = soulText(); selected.value = null; edited.value = ''; recalled.value = null; exportPage.value = null; memOffset.value = 0
  draft.value.content = ''; draft.value.session_id = ''; draft.value.branch_head_id = ''; draft.value.source = 'manual'; sourceRows.value = []
  linkOptions.value = []; linkId.value = ''; recallSession.value = ''; recallHead.value = ''; await loadMemories()
}
async function create() {
  const row = await api.post(base, { name: newName.value, world_id: newWorld.value ? Number(newWorld.value) : null, notes: newNotes.value })
  if (disposed) return
  newName.value = ''; newNotes.value = ''; newOpen.value = false; offset.value = 0; await load(); await open(row.id)
}
async function saveSoul(active = cur.value.active) {
  const row = await api.patch(`${base}/${cur.value.id}`, { expected_revision: cur.value.revision, name: cur.value.name, notes: cur.value.notes, active })
  if (disposed) return
  Object.assign(cur.value, row); savedSoul.value = soulText(); await load()
}
async function candidates() {
  const data = await api.get(`${base}/${cur.value.id}/candidates`, { kind: linkKind.value, q: linkQuery.value })
  if (!disposed) { linkOptions.value = data.items; linkId.value = '' }
}
async function addLink() {
  await api.post(`${base}/${cur.value.id}/links`, { kind: linkKind.value, target_id: Number(linkId.value) })
  const data = await api.get(`${base}/${cur.value.id}`)
  if (!disposed) { cur.value.links = data.links; notice.value = '已显式关联；原资料保持不变。' }
}
async function toggleLink(link) {
  await api.patch(`${base}/${cur.value.id}/links/${link.id}`, { expected_revision: link.revision, active: !link.active })
  const data = await api.get(`${base}/${cur.value.id}`)
  if (!disposed) cur.value.links = data.links
}
async function messages() {
  const data = await api.get(`${base}/${cur.value.id}/source-messages`, { session_id: Number(draft.value.session_id), head_id: draft.value.branch_head_id ? Number(draft.value.branch_head_id) : undefined })
  if (!disposed) { sourceRows.value = data.items; if (!draft.value.branch_head_id && data.head_id) draft.value.branch_head_id = data.head_id }
}
async function createMemory() {
  const d = draft.value
  await api.post(`${base}/${cur.value.id}/memories`, { kind: d.kind, content: d.content, scope: d.scope,
    session_id: d.scope !== 'character' ? Number(d.session_id) : null,
    branch_head_id: d.scope === 'branch' && d.branch_head_id ? Number(d.branch_head_id) : null,
    source: sourcePayload(d.source, d.message_id, d.note), importance: d.importance })
  if (disposed) return
  d.content = ''; memOffset.value = 0; await loadMemories(); notice.value = '已保存为待审记忆；尚未允许上下文引用。'
}
function inspect(row, force = false) {
  if (!force && memoryDirty.value && !window.confirm('有未保存的记忆修改，确定切换？')) return
  selected.value = row; edited.value = row.content; conflictNote.value = row.conflict_note; showHistory.value = false
}
async function inspectRecall(id) {
  const row = await api.get(`${base}/${cur.value.id}/memories/${id}`)
  if (!disposed) inspect(row)
}
async function changeMemory(patch) {
  const row = await api.patch(`${base}/${cur.value.id}/memories/${selected.value.id}`, { expected_revision: selected.value.revision, ...patch })
  if (disposed) return
  inspect(row, true); recalled.value = null; await loadMemories()
}
async function afterRestore() {
  const id = selected.value.id; await loadMemories()
  if (!disposed) { const row = memories.value.items.find(x => x.id === id); if (row) inspect(row, true); else selected.value = null }
}
async function recall() {
  const data = await api.post(`${base}/${cur.value.id}/recall`, { query: recallQuery.value, session_id: recallSession.value ? Number(recallSession.value) : null,
    branch_head_id: recallHead.value ? Number(recallHead.value) : null, max_chars: Number(budget.value) })
  if (!disposed) recalled.value = data
}
async function exportNext(reset = false) {
  const data = await api.get(`${base}/${cur.value.id}/export`, { after_id: reset ? 0 : exportPage.value?.next_after_id || 0 })
  if (!disposed) exportPage.value = data
}
function downloadExport() {
  if (!exportPage.value) return
  const url = URL.createObjectURL(new Blob([JSON.stringify(exportPage.value, null, 2)], { type: 'application/json' }))
  const a = document.createElement('a'); a.href = url; a.download = `soul-${cur.value.uid}-page.json`; a.click(); URL.revokeObjectURL(url)
}
onMounted(() => run(async () => {
  window.addEventListener('beforeunload', leaving)
  const data = await api.get('/api/worlds', { limit: 100 })
  if (!disposed) worlds.value = data.items
  await load()
}))
</script>

<template>
  <div class="soul-workspace grid">
    <p class="notice">Character Soul · 身份关联与可审核记忆。默认不提取私人聊天；召回仅在本地预览，尚不自动发送给 AI。</p>
    <p v-if="error" role="alert" class="notice">{{ error }} <button :disabled="busy || !cur" @click="run(() => open(cur.id))">刷新当前档案</button></p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <div v-if="pendingOpen !== null" class="notice grid" role="alert"><p>加载档案会放弃未保存草稿。已保存的资料不会被删除。</p><div class="row"><button :disabled="busy" @click="run(() => open(pendingOpen, true))">确认放弃草稿并加载</button><button :disabled="busy" @click="pendingOpen = null">保留未保存草稿</button></div></div>
    <div class="soul-columns">
      <aside class="card grid soul-sidebar" aria-label="角色身份列表">
        <button class="primary" :disabled="busy" @click="newOpen = !newOpen">新建角色身份</button>
        <form v-if="newOpen" class="grid" @submit.prevent="run(create)">
          <label>身份名称<input v-model="newName" required maxlength="200" /></label>
          <label>世界观<select v-model="newWorld"><option value="">独立角色</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }} #{{ w.id }}</option></select></label>
          <label>身份备注<textarea v-model="newNotes" maxlength="10000" /></label><button :disabled="busy" type="submit">创建身份</button>
        </form>
        <form class="grid" @submit.prevent="offset = 0; run(load)"><label>搜索身份<input v-model="filter" maxlength="200" /></label><label class="row"><input v-model="inactive" type="checkbox" />包含停用身份</label><button :disabled="busy">搜索</button></form>
        <button v-for="row in page.items" :key="row.uid" :disabled="busy" :aria-pressed="cur?.id === row.id" class="identity" @click="run(() => open(row.id))"><b>{{ row.name }}</b><small>{{ row.world_ref.id ? `世界观 #${row.world_ref.id}` : '独立角色' }} · {{ row.active ? '启用' : '停用' }}</small></button>
        <p v-if="!page.items.length" class="muted">暂无身份。可以从独立角色开始，再关联已有档案。</p>
        <div class="row"><button :disabled="busy || !offset" @click="offset -= 25; run(load)">上一页</button><span>{{ page.total }} 个</span><button :disabled="busy || offset + 25 >= page.total" @click="offset += 25; run(load)">下一页</button></div>
      </aside>
      <fieldset v-if="cur" :disabled="busy" class="grid soul-detail" aria-label="角色记忆档案">
        <section class="card grid">
          <form class="grid" @submit.prevent="run(() => saveSoul())"><label>角色身份名称<input v-model="cur.name" required maxlength="200" /></label><code>{{ cur.uid }}</code><p v-if="cur.diagnostic" class="notice">{{ cur.diagnostic }}</p><label>档案备注<textarea v-model="cur.notes" maxlength="10000" /></label><div class="row"><button :disabled="busy">保存档案</button><button type="button" :disabled="busy" @click="run(() => saveSoul(!cur.active))">{{ cur.active ? '停用身份' : '重新启用身份' }}</button></div></form>
          <p class="small muted">世界观范围创建后固定；不根据名字合并人物。停用保留历史，不等于清除历史版本或已有备份。</p>
          <details><summary>关联百科、角色卡、声线与模型</summary>
            <form class="grid" @submit.prevent="run(candidates)"><label>关联类型<select v-model="linkKind" @change="linkOptions = []; linkId = ''"><option v-for="(name, key) in linkKinds" :key="key" :value="key">{{ name }}</option></select></label><label>搜索已有资料<input v-model="linkQuery" maxlength="200" /></label><button :disabled="busy">查找候选</button></form>
            <div v-if="linkOptions.length" class="row"><label class="grow">选择关联资料<select v-model="linkId"><option value="">请选择</option><option v-for="x in linkOptions" :key="x.id" :value="x.id">{{ x.title }} #{{ x.id }}</option></select></label><button :disabled="busy || !linkId" @click="run(addLink)">确认关联</button></div>
            <div v-for="x in cur.links" :key="x.id" class="link-row"><span>{{ linkKinds[x.kind] }} #{{ x.target_id }} · {{ x.diagnostic || '身份与范围有效' }}</span><button :disabled="busy" @click="run(() => toggleLink(x))">{{ x.active ? '停用关联' : '恢复关联' }}</button></div>
          </details>
        </section>
        <section class="card grid" aria-label="记录待审核记忆">
          <h2>记录记忆</h2>
          <form class="grid" @submit.prevent="run(createMemory)">
            <div class="form-columns"><label>记忆类型<select v-model="draft.kind"><option v-for="(name, key) in memoryKinds" :key="key" :value="key">{{ name }}</option></select></label><label>适用范围<select v-model="draft.scope"><option v-for="(name, key) in scopeNames" :key="key" :value="key">{{ name }}</option></select></label></div>
            <label>记忆内容<textarea v-model="draft.content" required maxlength="12000" rows="4" /></label>
            <div v-if="draft.scope !== 'character' || draft.source === 'message'" class="form-columns"><label>已关联会话<select v-model="draft.session_id"><option value="">请选择</option><option v-for="x in chats" :key="x.id" :value="x.target_id">会话 #{{ x.target_id }}</option></select></label><label v-if="draft.scope === 'branch'">分支节点 ID（留空使用当前节点）<input v-model="draft.branch_head_id" type="number" min="1" /></label></div>
            <div class="form-columns"><label>来源<select v-model="draft.source"><option value="manual">人工记录</option><option value="message">聊天消息证据</option><option v-for="x in entitySources" :key="x.id" :value="`${x.kind}:${x.target_id}`">{{ linkKinds[x.kind] }} #{{ x.target_id }}</option></select></label><label>重要度 0–100<input v-model.number="draft.importance" type="number" min="0" max="100" /></label></div>
            <template v-if="draft.source === 'message'"><button type="button" :disabled="busy || !draft.session_id" @click="run(messages)">查看所选分支原文证据</button><label>来源消息<select v-model="draft.message_id"><option value="">请选择消息</option><option v-for="x in sourceRows" :key="x.id" :value="x.id">#{{ x.id }} {{ x.role }} · {{ x.excerpt }}</option></select></label></template>
            <label>来源说明<input v-model="draft.note" maxlength="1000" /></label><small class="muted">聊天情节、摘要和情绪必须使用分支范围。核心设定需关联正式角色来源；世界观记忆需关联世界书条目。AI 建议须人工审核。</small><button :disabled="busy || !cur.active" class="primary">保存待审记忆</button>
          </form>
        </section>
        <section class="card grid" aria-label="记忆审核与历史">
          <h2>审核与历史</h2>
          <form class="grid" @submit.prevent="memOffset = 0; run(loadMemories)"><label>搜索记忆<input v-model="memQuery" maxlength="200" /></label><div class="form-columns"><label>类型筛选<select v-model="memKind"><option value="">全部类型</option><option v-for="(name, key) in memoryKinds" :key="key" :value="key">{{ name }}</option></select></label><label>审核筛选<select v-model="memReview"><option value="">全部状态</option><option v-for="(name, key) in reviewNames" :key="key" :value="key">{{ name }}</option></select></label></div><button :disabled="busy">筛选记忆</button></form>
          <button v-for="x in memories.items" :key="x.uid" class="memory-row" :disabled="busy" :aria-pressed="selected?.id === x.id" @click="inspect(x)"><b>{{ memoryKinds[x.kind] }} · {{ reviewNames[x.review] }}{{ x.conflict ? ' · 有冲突' : '' }}{{ !x.active ? ' · 已停用' : '' }}</b><span>{{ x.content.slice(0, 160) }}</span><small>{{ scopeNames[x.scope] }} · {{ x.diagnostic || `版本 ${x.revision}` }}</small></button>
          <p v-if="!memories.items.length" class="muted">暂无匹配记忆。所有新记忆先进入待审状态。</p>
          <div class="row"><button :disabled="busy || !memOffset" @click="memOffset -= 30; run(loadMemories)">上一页记忆</button><span>{{ memories.total }} 条</span><button :disabled="busy || memOffset + 30 >= memories.total" @click="memOffset += 30; run(loadMemories)">下一页记忆</button></div>
          <div v-if="selected" class="grid memory-editor">
            <code>{{ selected.uid }}</code><p v-if="selected.diagnostic" class="notice">{{ selected.diagnostic }}</p>
            <label>编辑记忆内容<textarea v-model="edited" maxlength="12000" rows="4" /></label><button :disabled="busy || !edited.trim()" @click="run(() => changeMemory({content: edited}))">保存修改并重新待审</button>
            <div class="row"><button :disabled="busy || !!selected.diagnostic || !selected.active || selected.conflict || edited !== selected.content" @click="run(() => changeMemory({review: 'approved', allow_injection: true}))">确认并允许引用</button><button :disabled="busy" @click="run(() => changeMemory({review: 'rejected'}))">拒绝建议</button><button :disabled="busy" @click="run(() => changeMemory({allow_injection: false}))">撤销引用许可</button><button :disabled="busy" @click="run(() => changeMemory({pinned: !selected.pinned}))">{{ selected.pinned ? '取消固定' : '固定记忆' }}</button></div>
            <label>冲突说明<input v-model="conflictNote" maxlength="1000" /></label><div class="row"><button :disabled="busy" @click="run(() => changeMemory({conflict: !selected.conflict, conflict_note: conflictNote}))">{{ selected.conflict ? '人工确认冲突已解决' : '标记冲突并停止引用' }}</button><button :disabled="busy" @click="run(() => changeMemory({active: !selected.active}))">{{ selected.active ? '停用记忆（保留历史）' : '恢复记忆为可审核状态' }}</button></div>
            <section class="card grid" aria-label="记忆来源证据"><b>{{ selected.source.kind === 'manual' ? '人工记录' : selected.source.kind === 'message' ? `来源消息 #${selected.source.ref.id} · 会话 #${selected.source.session.id} · 分支 #${selected.source.branch.id}` : `${linkKinds[selected.source.kind]} #${selected.source.ref.id}` }}</b><blockquote v-if="selected.source.excerpt" class="content">{{ selected.source.excerpt }}</blockquote><p v-if="selected.source.note">{{ selected.source.note }}</p><small>{{ scopeNames[selected.scope] }} · {{ selected.allow_injection ? '已允许上下文引用' : '未允许上下文引用' }}</small><RouterLink v-if="sourceLink(selected.source)" :to="sourceLink(selected.source)">查看来源工作区</RouterLink><details><summary>来源与范围指纹</summary><pre>{{ JSON.stringify({source: selected.source, scope: selected.scope_ref}, null, 2) }}</pre></details></section>
            <button @click="showHistory = !showHistory">{{ showHistory ? '收起' : '查看' }}版本历史与恢复</button><VersionPanel v-if="showHistory" :key="selected.id" kind="soul_memory" :entity-id="selected.id" @restored="run(afterRestore)" />
          </div>
        </section>
        <section class="card grid" aria-label="本地记忆召回预览">
          <h2>本地召回预览</h2><p class="small muted">只选取有效、已确认、无冲突且明确允许引用的记忆。固定记忆也受范围、来源和预算约束；不调用 AI。</p>
          <form class="grid" @submit.prevent="run(recall)"><label>回忆关键词<input v-model="recallQuery" maxlength="200" /></label><div class="form-columns"><label>召回会话<select v-model="recallSession"><option value="">仅角色共享记忆</option><option v-for="x in chats" :key="x.id" :value="x.target_id">会话 #{{ x.target_id }}</option></select></label><label>目标分支节点（可选）<input v-model="recallHead" type="number" min="1" /></label><label>最大注入字数（含引用）<input v-model.number="budget" type="number" min="64" max="12000" /></label></div><button :disabled="busy">预览相关记忆</button></form>
          <template v-if="recalled"><p role="status">{{ recalled.notice }} {{ recalled.chars }} / {{ recalled.max_chars }} 字</p><div v-for="x in recalled.items" :key="x.uid" class="card"><b>{{ x.citation }} · {{ x.reason }}</b><p class="content">{{ x.content }}</p><small>{{ scopeNames[x.scope] }} · 版本 {{ x.revision }}</small><button :disabled="busy" @click="run(() => inspectRecall(x.id))">查看记忆</button></div><p v-if="!recalled.items.length" class="muted">没有满足范围、审核及字数条件的记忆。</p></template>
        </section>
        <section class="card grid"><h2>个人记忆导出</h2><p class="small muted">每页最多 100 条当前记录。完整历史请使用“备份与恢复”。停用不会删除历史或既有备份；本轮不提供不可逆清除。</p><div class="row"><button :disabled="busy" @click="run(() => exportNext(true))">准备第一页</button><button :disabled="busy || !exportPage?.next_after_id" @click="run(() => exportNext())">准备下一页</button><button :disabled="!exportPage" @click="downloadExport">下载当前页 JSON</button><RouterLink to="/backups">完整备份与恢复</RouterLink></div><small v-if="exportPage">本页 {{ exportPage.memories.length }} 条 · {{ exportPage.next_after_id ? '还有下一页' : '已到末页' }}</small></section>
      </fieldset>
      <section v-else class="card"><h2>让角色档案与经历保持可追溯</h2><p>创建或选择身份后，关联已有资料、记录待审记忆，再预览它在指定会话和分支中的召回结果。无需配置模型。</p></section>
    </div>
  </div>
</template>

<style scoped>
fieldset.soul-detail{border:0;padding:0;margin:0;min-width:0}
.soul-workspace label.row{display:flex;align-items:center;gap:8px}
.soul-workspace{gap:14px;min-width:0}.soul-columns{display:grid;grid-template-columns:260px minmax(0,1fr);gap:16px;align-items:start}.soul-sidebar{position:sticky;top:16px;gap:10px;max-height:calc(100vh - 140px);overflow:auto}.soul-detail{gap:16px;min-width:0}.soul-detail>.card{gap:12px}.grid{gap:10px}label{display:grid;gap:5px;font-size:13px;min-width:0}.row label.row{display:flex}input[type=checkbox]{width:auto}textarea,select,input{max-width:100%;min-width:0}textarea{resize:vertical}.form-columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.identity,.memory-row{text-align:left;display:grid;gap:5px;width:100%;overflow-wrap:anywhere}.identity[aria-pressed=true],.memory-row[aria-pressed=true]{border-color:var(--accent)}.memory-row span{white-space:pre-wrap}.link-row{display:flex;align-items:center;justify-content:space-between;gap:8px;border-bottom:1px solid var(--line);padding:8px 0}.link-row span{overflow-wrap:anywhere}.memory-editor{border-top:1px solid var(--line);padding-top:14px}code,pre{overflow-wrap:anywhere;white-space:pre-wrap;font-size:12px}pre{max-height:300px;overflow:auto}.content{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer;padding:8px 0}h2{font-size:17px;margin:0}.grow{flex:1;min-width:0}.row{flex-wrap:wrap}@media(max-width:850px){.soul-columns{grid-template-columns:minmax(0,1fr)}.soul-sidebar{position:static;max-height:none}.link-row{align-items:flex-start;flex-wrap:wrap}}
</style>
