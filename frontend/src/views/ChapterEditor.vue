<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { toast } from '../toast'

const id = Number(useRoute().params.id)
const info = ref(null), draft = ref([]), error = ref(''), busy = ref(false), page = ref(0)
const selected = ref(0), cut = ref(0), excerpt = ref(''), note = ref(''), compatible = ref(true)
const clone = value => JSON.parse(JSON.stringify(value))
let disposed = false, previewSequence = 0
onBeforeUnmount(() => { disposed = true; previewSequence++ })
async function load() {
  busy.value = true; error.value = ''
  try { info.value = await api.get(`/api/assets/${id}/chapter-plan`); draft.value = clone(info.value.chapters); compatible.value = true; selected.value = 0; page.value = 0; await inspect(0) }
  catch (e) { error.value = e.message } finally { busy.value = false }
}
async function inspect(index) {
  const sequence = ++previewSequence
  selected.value = index
  const chapter = draft.value[index]
  if (!chapter) return
  cut.value = chapter.end
  try { const data = await api.get(`/api/assets/${id}/chapter-plan/excerpt`,{start:chapter.start}); if (!disposed && sequence === previewSequence) excerpt.value = data.text }
  catch (e) { if (!disposed && sequence === previewSequence) error.value = e.message }
}
const current = computed(() => draft.value[selected.value])
const rows = computed(() => draft.value.slice(page.value * 50, page.value * 50 + 50))
const shape = c => [c.title, c.start, c.end, c.body_start ?? c.start]
const changed = computed(() => draft.value.reduce((n,c,i) => n + (JSON.stringify(shape(c)) !== JSON.stringify(info.value?.chapters[i] ? shape(info.value.chapters[i]) : null)),0) + Math.max(0,(info.value?.chapters.length || 0) - draft.value.length))
function reidentify() { draft.value = clone(info.value.detected); compatible.value = true; note.value = '重新识别后确认'; page.value = 0; inspect(0) }
function split() {
  const c = current.value, position = Number(cut.value)
  if (!(c.start < position && position < c.end && (c.body_start ?? c.start) <= position)) return error.value = '拆分位置须在本章正文内部（字符偏移）'
  const tail = {...c,title:'新章节',start:position,body_start:position}
  c.end = position; draft.value.splice(selected.value + 1,0,tail); error.value = ''
}
function merge() {
  const c = current.value, next = draft.value[selected.value + 1]
  if (!next || c.end !== next.start) return error.value = '只能合并原文中连续且顺序相邻的章节'
  c.end = next.end; draft.value.splice(selected.value + 1,1); error.value = ''
}
function boundary() {
  const c = current.value, next = draft.value[selected.value + 1], position = Number(cut.value)
  if (!next || c.end !== next.start || !(c.start < position && position < next.end && (c.body_start ?? c.start) <= position)) return error.value = '分界须在这两个原文连续章节的正文范围内'
  c.end = position; next.start = position; next.body_start = position; error.value = ''
}
function move(delta) {
  const target = selected.value + delta
  if (target < 0 || target >= draft.value.length) return
  const [c] = draft.value.splice(selected.value,1); draft.value.splice(target,0,c); selected.value = target; page.value = Math.floor(target / 50)
}
async function history(item) {
  try { const data = await api.get(`/api/assets/${id}/chapter-plan/history/${item.id}`); draft.value = clone(data.chapters); compatible.value = data.text_hash === info.value.text_hash; note.value = `恢复目录版本 ${item.id}`; selected.value = 0; page.value = 0; await inspect(0) }
  catch (e) { error.value = e.message }
}
async function save() {
  busy.value = true; error.value = ''
  try { await api.put(`/api/assets/${id}/chapter-plan`,{text_hash:info.value.text_hash,base_revision:info.value.base_revision,chapters:draft.value,note:note.value}); await load(); toast('已确认目录并保存新版本') }
  catch (e) { error.value = e.message } finally { busy.value = false }
}
onMounted(load)
</script>
<template>
  <div class="grid">
    <div class="row"><h2 style="margin:0">{{ info?.title || '章节整理' }}</h2><span class="spacer" /><RouterLink class="btn" :to="`/read/${id}`">返回阅读</RouterLink><button :disabled="busy" @click="load">重新加载</button></div>
    <p v-if="error" role="alert" class="notice">{{ error }}</p>
    <template v-if="info">
      <p class="small muted">{{ info.source }} · {{ info.length.toLocaleString() }} 字符 · 当前目录版本 {{ info.base_revision }}。边界采用 Unicode 字符偏移（从 0 开始，含标题和换行）。只修改目录，不改写正文或原文件。</p>
      <p v-if="info.stale" role="alert" class="notice">正文已变化，旧目录未自动套用。下方为重新识别预览，请确认后保存。</p>
      <p v-if="!compatible" role="alert" class="notice">正在查看其他正文版本的目录，只读；请重新加载或重新识别。</p>
      <div class="row"><span class="badge">{{ draft.length }} 章</span><span class="badge">与已保存/初始目录相比 {{ changed }} 项位置或内容变化</span><span class="spacer" /><button @click="reidentify">重新识别为草稿</button></div>
      <div class="editor-layout">
        <section class="card grid">
          <div class="table-scroll"><table><thead><tr><th>章节</th><th>原文范围</th><th>字数</th></tr></thead><tbody><tr v-for="(c,i) in rows" :key="page * 50 + i"><td><button :aria-pressed="selected === page * 50 + i" @click="inspect(page * 50 + i)">{{ page * 50 + i + 1 }} · {{ c.title }}</button></td><td class="mono">{{ c.start }}–{{ c.end }}</td><td>{{ c.words }}</td></tr></tbody></table></div>
          <nav class="row" aria-label="章节列表分页"><button :disabled="page === 0" @click="page--">上一页</button><span class="small">{{ page + 1 }} / {{ Math.max(1, Math.ceil(draft.length / 50)) }}</span><button :disabled="(page + 1) * 50 >= draft.length" @click="page++">下一页</button></nav>
        </section>
        <section v-if="current" class="card grid">
          <h2 style="margin:0">章节与边界</h2>
          <label class="field">章节标题<input v-model="current.title" maxlength="300" /></label>
          <div class="row"><button @click="move(-1)">上移</button><button @click="move(1)">下移</button><button @click="merge">与下一章合并</button></div>
          <label class="field">拆分 / 与下一章调整分界的字符位置<input v-model.number="cut" type="number" min="0" :max="info.length" /></label>
          <div class="row"><button @click="split">在此拆分</button><button @click="boundary">调整相邻分界</button></div>
          <p class="small muted">源范围 {{ current.start }}–{{ current.end }}；正文从 {{ current.body_start ?? current.start }} 开始。字数在保存时重新计算。合并保留原文中的后续标题。</p>
          <h3>原文只读预览（从章节起点起最多 2000 字符）</h3><pre>{{ excerpt }}</pre>
        </section>
      </div>
      <div class="card grid"><label class="field">本次修改说明<input v-model="note" maxlength="500" /></label><div class="row"><span class="small muted">确认后阅读器使用此目录；历史记录继续保留。</span><span class="spacer" /><button class="primary" :disabled="busy || !compatible" @click="save">确认目录并保存新版本</button></div></div>
      <details class="card"><summary>目录历史（最近 100 次）</summary><div v-for="item in info.history" :key="item.id" class="row"><span class="small">#{{ item.id }} · {{ item.note || '未填写说明' }} · {{ item.created_at }}</span><span class="spacer" /><button @click="history(item)">{{ item.compatible ? '载入为恢复草稿' : '查看旧目录（正文已变化）' }}</button></div></details>
    </template>
  </div>
</template>
<style scoped>
.editor-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; align-items: start; }
.editor-layout > * { min-width: 0; }
.table-scroll { overflow: auto; max-height: 600px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 320px; overflow: auto; font-size: 12px; }
@media (max-width: 1000px) { .editor-layout { grid-template-columns: minmax(0, 1fr); } }
</style>
