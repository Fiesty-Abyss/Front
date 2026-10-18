<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { toast } from '../toast'
import JobProgress from '../components/JobProgress.vue'

const models = ref([]), selected = ref(null), q = ref(''), offset = ref(0), total = ref(0)
const busy = ref(false), error = ref(''), job = ref(null), showImport = ref(false), hideList = ref(false), hideInfo = ref(false)
const form = reactive({ path: '', creator: '', source_url: '', license_notes: '' })
const labels = ref('')
let timer, disposed = false, selection = 0
onBeforeUnmount(() => { disposed = true; selection++; clearTimeout(timer) })
async function load() {
  try {
    const data = await api.get('/api/live2d/profiles', {q:q.value, offset:offset.value, limit:50})
    if (!disposed) { models.value = data.items; total.value = data.total }
  } catch (e) { if (!disposed) error.value = e.message }
}
async function choose(id) {
  const current = ++selection
  try {
    const data = await api.get(`/api/live2d/profiles/${id}`)
    if (!disposed && current === selection) { selected.value = data; labels.value = data.labels.join(', '); error.value = '' }
  } catch (e) { if (!disposed) error.value = e.message }
}
async function poll(id) {
  if (disposed) return
  try {
    const data = await api.get(`/api/jobs/${id}`)
    if (disposed) return
    job.value = data; busy.value = ['queued', 'running'].includes(data.status)
    if (busy.value) timer = setTimeout(() => poll(id), 600)
    else { await load(); if (data.result?.profile_ids?.length) await choose(data.result.profile_ids[0]) }
  } catch (e) { if (!disposed) { error.value = e.message; busy.value = false } }
}
async function scan() {
  busy.value = true; error.value = ''
  try { const data = await api.post('/api/live2d/scan', {...form}); await poll(data.id) }
  catch (e) { error.value = e.message; busy.value = false }
}
async function save() {
  const {scan, id, source_path, main, ...data} = selected.value
  data.labels = labels.value.split(/[,，]/).map(x => x.trim()).filter(Boolean)
  try { selected.value = await api.patch(`/api/live2d/profiles/${id}`, data); await load(); toast('已保存模型档案') }
  catch (e) { error.value = e.message }
}
async function rescan() {
  busy.value = true; error.value = ''
  try { const data = await api.post('/api/live2d/scan', {path:selected.value.source_path}); await poll(data.id) }
  catch (e) { error.value = e.message; busy.value = false }
}
async function remove() {
  if (!confirm('移除这个模型档案及其评分备注？原始模型文件会保留。')) return
  try { await api.del(`/api/live2d/profiles/${selected.value.id}`); selected.value = null; selection++; await load() }
  catch (e) { error.value = e.message }
}
async function search() { offset.value = 0; await load() }
async function page(delta) { offset.value += delta * 50; await load() }
onMounted(async () => {
  await load()
  const history = await api.get('/api/jobs?kind=live2d-scan').catch(() => [])
  if (!disposed && history.length && ['queued', 'running'].includes(history[0].status)) await poll(history[0].id)
})
const scanInfo = computed(() => selected.value?.scan)
const missing = computed(() => scanInfo.value?.dependencies.filter(d => !d.exists).length || 0)
</script>

<template>
  <div class="studio grid">
    <header class="row studio-tools">
      <span class="small muted">模型档案与资源诊断</span><span class="spacer" />
      <button :aria-pressed="!hideList" @click="hideList = !hideList">模型列表</button>
      <button :aria-pressed="!hideInfo" @click="hideInfo = !hideInfo">属性面板</button>
      <button class="primary" @click="showImport = !showImport">扫描本地模型</button>
    </header>
    <form v-if="showImport" class="card grid" @submit.prevent="scan">
      <p class="small muted" style="margin:0">只读扫描文件夹或 ZIP；Windows 也可扫描 RAR。仅保存档案，不复制模型。请按作者授权使用素材。</p>
      <label class="field">模型路径<input v-model="form.path" required placeholder="模型文件夹或压缩包的完整路径" /></label>
      <div class="grid cols-2">
        <label class="field">创作者<input v-model="form.creator" maxlength="300" /></label>
        <label class="field">来源链接<input v-model="form.source_url" maxlength="2000" /></label>
      </div>
      <label class="field">许可说明<textarea v-model="form.license_notes" placeholder="使用范围、禁止事项与署名要求；扫描不会自动判断授权" maxlength="20000" /></label>
      <div class="row"><span class="small muted">原模型文件保持不变</span><span class="spacer" /><button class="primary" :disabled="busy || !form.path">开始扫描</button></div>
    </form>
    <JobProgress :job="job" />
    <p v-if="error" role="alert" class="notice">{{ error }} <button @click="load">重新加载列表</button></p>
    <p v-for="(e, i) in job?.result?.errors || []" :key="i" class="notice">{{ e.source }}：{{ e.message }}</p>
    <div class="studio-grid" :class="{ 'no-list': hideList, 'no-info': hideInfo }">
      <aside v-if="!hideList" class="model-list card">
        <form class="grid" @submit.prevent="search"><label class="field">模型搜索<input v-model="q" placeholder="搜索档案名称" /></label><button>搜索</button></form>
        <div class="row small muted"><span>模型</span><span class="spacer" />{{ total }}</div>
        <button v-for="m in models" :key="m.id" class="model-entry" :class="{active:selected?.id === m.id}" @click="choose(m.id)">
          <span class="model-mark" aria-hidden="true">L2</span><span><b>{{ m.title }}</b><small>{{ m.creator || '未填写作者' }}</small></span><span v-if="m.favorite" aria-label="已收藏">★</span>
        </button>
        <p v-if="!models.length" class="small muted">还没有模型档案。扫描本地路径后，模型会分别出现在这里。</p>
        <div v-if="total > 50" class="row"><button :disabled="!offset" @click="page(-1)">上一页</button><span class="small">{{ offset / 50 + 1 }}</span><button :disabled="offset + 50 >= total" @click="page(1)">下一页</button></div>
      </aside>
      <section class="diagnostic-stage card">
        <template v-if="selected">
          <div class="row"><span class="eyebrow">MODEL / {{ selected.id }}</span><span class="spacer" /><span class="badge">{{ missing ? `缺失 ${missing} 项` : '引用检查完成' }}</span></div>
          <h2 class="model-title">{{ selected.title }}</h2>
          <p class="small muted mono">{{ selected.main }}</p>
          <div class="stage-placeholder"><span class="model-mark large" aria-hidden="true">L2</span><h3>实时预览尚未接入</h3><p>当前可检查模型文件与资料。渲染兼容性需通过 Cubism 运行时单独验证。</p></div>
          <div class="row small"><span class="badge">配置参数 {{ scanInfo.parameters.length }}</span><span class="badge">声明动作 {{ scanInfo.motions.length }}</span><span class="badge">声明表情 {{ scanInfo.expressions.length }}</span></div>
          <h3>资源诊断</h3>
          <ul class="diagnostics"><li v-for="(d, i) in scanInfo.diagnostics" :key="i"><span class="badge">{{ d.code }}</span><p>{{ d.message }}</p><small class="mono muted">{{ d.file }}</small></li></ul>
          <details><summary>依赖文件 · {{ scanInfo.dependencies.length }}</summary><ul class="resource-list"><li v-for="(d,i) in scanInfo.dependencies" :key="i"><span :class="{missing:!d.exists}">{{ d.exists ? '✓' : '缺失' }}</span> {{ d.kind }} <span class="mono">{{ d.path }}</span></li></ul></details>
          <details><summary>配置中发现的参数 · {{ scanInfo.parameters.length }}</summary><p class="small muted">{{ scanInfo.parameter_source }}</p><p class="mono">{{ scanInfo.parameters.join(' · ') }}</p></details>
          <details><summary>同目录其他配置 · {{ scanInfo.nearby_files.length }}</summary><p class="small muted">扫描到的邻近文件不等于模型已声明的动作或表情。</p><p v-for="file in scanInfo.nearby_files" :key="file" class="mono">{{ file }}</p></details>
        </template>
        <div v-else class="stage-placeholder empty"><span class="model-mark large" aria-hidden="true">L2</span><h2>建立你的模型档案</h2><p>从左侧选择模型，或扫描本地文件夹。模型文件、相对引用和原始目录保持不变。</p><button class="primary" @click="showImport = true">扫描本地模型</button></div>
      </section>
      <aside v-if="!hideInfo" class="inspector card">
        <form v-if="selected" class="grid" @submit.prevent="save">
          <h2 style="margin:0">模型属性</h2>
          <label class="field">名称<input v-model="selected.title" required maxlength="300" /></label>
          <label class="field">创作者<input v-model="selected.creator" maxlength="300" /></label>
          <label class="field">来源链接<input v-model="selected.source_url" maxlength="2000" /></label>
          <label class="field">许可说明<textarea v-model="selected.license_notes" maxlength="20000" /></label>
          <label class="field">模型版本<input v-model="selected.model_version" maxlength="100" /></label>
          <label class="row"><input v-model="selected.favorite" type="checkbox" style="width:auto" />收藏模型</label>
          <div class="grid cols-2"><label class="field">星级<select v-model.number="selected.stars"><option v-for="n in 6" :key="n" :value="n - 1">{{ n - 1 }} 星</option></select></label><label class="field">喜爱度<input v-model.number="selected.preference" type="number" min="0" max="100" /></label></div>
          <label class="field">标签（逗号分隔）<input v-model="labels" /></label>
          <label class="field">个人备注<textarea v-model="selected.notes" maxlength="20000" /></label>
          <details><summary>原始路径</summary><p class="mono muted">{{ selected.source_path }}</p></details>
          <button class="primary">保存档案</button>
          <div class="row"><button type="button" :disabled="busy" @click="rescan">重新检查原路径</button><button type="button" class="danger" @click="remove">移除档案</button></div>
        </form>
        <p v-else class="small muted">选择模型后编辑作者、许可、评分与备注。</p>
      </aside>
    </div>
    <footer class="row small muted"><span class="status-dot" />档案模式 · 未启动渲染器或摄像头<span class="spacer" />配置独立保存 · 原模型只读</footer>
  </div>
</template>

<style scoped>
.studio { gap: 12px; }
.studio-tools { gap: 8px; }
.studio-grid { display: grid; grid-template-columns: 210px minmax(260px, 1fr) 280px; gap: 12px; align-items: start; }
.studio-grid.no-list { grid-template-columns: minmax(260px, 1fr) 280px; }
.studio-grid.no-info { grid-template-columns: 210px minmax(260px, 1fr); }
.studio-grid.no-list.no-info { grid-template-columns: minmax(0, 1fr); }
.studio-grid > * { min-width: 0; padding: 16px; }
.model-list { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }
.model-list form, .model-list .field, .model-list input { min-width: 0; width: 100%; }
.model-entry { display: flex; align-items: center; gap: 10px; text-align: left; white-space: normal; width: 100%; padding: 10px; border-radius: 8px; }
.model-entry > span { min-width: 0; }
.model-entry > span:nth-child(2) { flex: 1; }
.model-entry.active { border-color: var(--accent); background: var(--accent-soft); }
.model-entry b, .model-entry small { display: block; overflow-wrap: anywhere; }
.model-entry small { color: var(--muted); font-size: 11px; }
.model-mark { display: grid; place-items: center; flex: 0 0 32px; width: 32px; height: 38px; border: 1px solid var(--line-strong); border-radius: 6px; color: var(--accent-hi); font-family: ui-monospace, monospace; font-weight: 600; }
.model-mark.large { width: 60px; height: 72px; font-size: 24px; margin: auto; }
.model-title { font-size: 24px; margin-bottom: 0; }
.stage-placeholder { text-align: center; display: grid; justify-items: center; align-content: center; min-height: 240px; padding: 24px; background: var(--sunken); border: 1px dashed var(--line-strong); border-radius: 8px; margin: 18px 0; }
.stage-placeholder p { max-width: 350px; font-size: 12px; color: var(--muted); }
.stage-placeholder.empty { min-height: 460px; margin: 0; }
.diagnostics { list-style: none; padding: 0; }
.diagnostics li { padding: 12px 0; border-bottom: 1px solid var(--line); }
.diagnostics p { margin: 8px 0 4px; font-size: 12px; }
details { border-top: 1px solid var(--line); padding: 12px 0; }
summary { cursor: pointer; font-size: 12px; color: var(--muted); }
.resource-list { list-style: none; padding: 0; font-size: 12px; }
.resource-list li { padding: 6px 0; overflow-wrap: anywhere; }
.missing { color: var(--danger); }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); }
@media (max-width: 1260px) { .studio-grid, .studio-grid.no-list, .studio-grid.no-info { grid-template-columns: minmax(0, 1fr); } .model-list { max-height: 320px; overflow: auto; } }
</style>
