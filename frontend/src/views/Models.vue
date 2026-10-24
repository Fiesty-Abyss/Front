<script setup>
import QuickSearch from '../components/QuickSearch.vue'
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, LABELS, SDModels, thumb, waitJob } from '../api'
import JobProgress from '../components/JobProgress.vue'
import Modal from '../components/Modal.vue'
import TagChips from '../components/TagChips.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard, toast } from '../toast'

const f = reactive({ q: '', kind: '', base_model: '' })
const route=useRoute()
const items = ref([])
const editing = ref(null)
const busy = ref('')
const job = ref(null)
const ModelProfile=defineAsyncComponent(()=>import('../components/ModelProfile.vue'))
const page=ref(0), total=ref(0), reportId=ref(''), scanPage=ref(0)
const lifecycle=new AbortController()
onBeforeUnmount(()=>{clearTimeout(t);lifecycle.abort()})
async function load() { const r=await SDModels.list({ ...f, limit: 50,offset:page.value*50 });items.value=r.items;total.value=r.total }
watch(page,load)
onMounted(async()=>{await load();if(route.query.id)await guard(async()=>edit(await SDModels.get(Number(route.query.id))))})
let t
watch(f, () => { clearTimeout(t); t = setTimeout(()=>{if(page.value)page.value=0;else load()}, 200) }, { deep: true })

function edit(m) { editing.value = m ? { ...m, tag_ids: m.tags.map((x) => x.id) } : { name: '', kind: 'checkpoint', tag_ids: [], hashes: {}, civitai: {} } }
async function inspect(hash) {
  busy.value = hash ? 'hash' : 'inspect'
  try {
    const r = await guard(() => api.post('/api/sd-models/inspect', { path: editing.value.local_path, compute_hash: hash }))
    const e = editing.value
    Object.assign(e, { file_name: r.file_name, size: r.size, kind: e.id ? e.kind : r.kind, ...(r.sha256 ? { sha256: r.sha256 } : {}), ...(r.base_model && !e.base_model ? { base_model: r.base_model } : {}) })
    if (r.hashes?.SHA256) e.hashes = r.hashes
    if (r.trigger_words && !e.trigger_words) e.trigger_words = r.trigger_words
    if (!e.name) e.name = r.civitai?.model_name || r.file_name.replace(/\.[^.]+$/, '')
  } finally { busy.value = '' }
}
async function save() {
  const { id, created_at, updated_at, tags, hashes, civitai, ...body } = editing.value
  await guard(() => (id ? SDModels.update(id, body) : SDModels.create(body)), '已保存')
  editing.value = null; load()
}
async function remove() {
  if (!confirm('删除这条模型登记？（不会删除你电脑上的模型文件）')) return
  await guard(() => SDModels.remove(editing.value.id), '已删除'); editing.value = null; load()
}
async function hashOne() {
  busy.value = 'hash'
  try {const id=editing.value.id;await runJob(`/api/model-assets/${id}/hash`);const r=await SDModels.get(id);if(editing.value?.id===id)Object.assign(editing.value,{sha256:r.sha256,hashes:r.hashes,size:r.size})} finally { busy.value = '' }
}
const civ = reactive({ overwrite: false, download_preview: true })
async function civitaiOne() {
  busy.value = 'civitai'
  try {
    const r = await guard(() => api.post(`/api/sd-models/${editing.value.id}/civitai`, { apply: true, ...civ }))
    toast(r.found ? `已匹配 Civitai：${r.civitai.model_name}${r.changed.length ? `（更新了 ${r.changed.length} 项）` : ''}` : 'Civitai 上没有找到这个哈希')
    editing.value = { ...r.model, tag_ids: r.model.tags.map((x) => x.id) }
    load()
  } finally { busy.value = '' }
}
async function runJob(url, body) {
  const j = await guard(() => api.post(url, body))
  job.value = j
  await waitJob(j.id, (x) => (job.value = x))
  load()
}
const fmt = (n) => (n ? (n / 1024 ** 3 >= 1 ? (n / 1024 ** 3).toFixed(2) + ' GB' : n / 1024 ** 2 >= 1 ? (n / 1024 ** 2).toFixed(1) + ' MB' : (n / 1024).toFixed(0) + ' KB') : '')

// ---------- 扫描模型目录 ----------
const scan = ref(null)
const scanForm = reactive({ path: localStorage.getItem('front.modelDir') || '', recursive: true, compute_hash: false, import_previews: true })
const scanResult = ref(null)
const picked = ref(new Set())
function openScan() { scan.value = true; scanResult.value = null }
async function doScan() {
  localStorage.setItem('front.modelDir', scanForm.path)
  busy.value = 'scan'
  try {
    const task=await guard(() => api.post('/api/model-assets/scan', { path: scanForm.path, recursive: scanForm.recursive }))
    job.value=task
    await waitJob(task.id,x=>job.value=x,800,lifecycle.signal)
    if(job.value.status!=='done')return
    reportId.value=job.value.result.report_id;scanPage.value=0;picked.value=new Set()
    await loadScan()
  } finally { busy.value = '' }
}
async function loadScan(){scanResult.value=await api.get(`/api/model-assets/reports/${reportId.value}`,{offset:scanPage.value*50,limit:50})}
async function scanNext(delta){scanPage.value+=delta;await guard(loadScan)}
function pickPage(){picked.value=new Set([...picked.value,...scanResult.value.items.filter(x=>!x.existing_id).map(x=>x.local_path)])}
function toggle(p) { const s = new Set(picked.value); s.has(p) ? s.delete(p) : s.add(p); picked.value = s }
async function register() {
  const files = [...picked.value]
  scan.value = null
  await runJob('/api/sd-models/scan/run', { ...scanForm, files })
  toast(`登记完成：新增 ${job.value.result.created?.length ?? 0}，跳过 ${job.value.result.skipped ?? 0}`)
}
const kindSummary = computed(() => Object.entries(scanResult.value?.kinds || {}).map(([k, n]) => `${LABELS.modelKind[k] ?? k} ${n}`).join(' · '))
const missingHash = computed(() => items.value.filter((m) => m.local_path && !m.sha256).length)
</script>
<template>
  <div class="notice" style="margin-bottom:14px">模型文件只登记路径、哈希与元数据，文件本身留在你的硬盘上，永远不会被上传或提交到仓库。Civitai 匹配只在你点击时联网（设置 <code>FRONT_CIVITAI=off</code> 可完全关闭）。</div>
  <div class="row" style="margin-bottom:12px">
    <input v-model="f.q" placeholder="搜索名称 / 触发词 / 备注" style="max-width:260px" />
    <select v-model="f.kind" style="width:150px"><option value="">全部类型</option><option v-for="(l, k) in LABELS.modelKind" :key="k" :value="k">{{ l }}</option></select>
    <select v-model="f.base_model" style="width:130px"><option value="">全部底模</option><option v-for="b in ['SD1.5', 'SD2', 'SDXL', 'Pony', 'Illustrious', 'SD3', 'Flux']" :key="b">{{ b }}</option></select>
    <span class="spacer" />
    <button :disabled="!missingHash" @click="runJob('/api/sd-models/hash-all', { only_missing: true })"># 计算缺失哈希<template v-if="missingHash"> · {{ missingHash }}</template></button>
    <button @click="runJob('/api/sd-models/civitai-all', { apply: true })"><Ico g="☁" />全部匹配 Civitai</button>
    <button @click="openScan"><Ico g="⌕" />扫描模型目录</button>
    <button class="primary" @click="edit(null)"><Ico g="＋" />登记模型</button>
  </div>
  <JobProgress v-if="job" :job="job" style="margin-bottom:12px" />
  <div class="card model-table" style="padding:0">
    <table>
      <thead><tr><th style="width:56px" /><th>名称</th><th>类型</th><th>底模</th><th>触发词</th><th>哈希（AutoV2）</th><th>本地路径</th><th>大小</th><th>标签</th></tr></thead>
      <tbody>
        <tr v-for="m in items" :key="m.id" style="cursor:pointer" @click="edit(m)">
          <td><div class="avatar" style="width:40px;height:52px;border-radius:6px" :style="m.preview_asset_id ? { backgroundImage: `url(${thumb(m.preview_asset_id)})` } : {}" /></td>
          <td><b>{{ m.name }}</b><span v-if="m.version" class="small muted"> · {{ m.version }}</span>
            <div class="row small" style="gap:6px"><span v-if="m.civitai?.model_name" class="badge" style="color:#7dd3fc">Civitai ✓</span><span v-else-if="m.civitai?.not_found" class="badge">Civitai 未收录</span><span class="muted">{{ m.notes?.slice(0, 40) }}</span></div></td>
          <td><span class="badge">{{ LABELS.modelKind[m.kind] }}</span></td><td>{{ m.base_model }}</td>
          <td class="mono small">{{ m.trigger_words }}</td>
          <td class="mono small">{{ m.hashes?.AutoV2 || (m.sha256 ? m.sha256.slice(0, 10).toUpperCase() : '—') }}</td>
          <td class="mono muted small" style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="m.local_path">{{ m.local_path }}</td><td class="small">{{ fmt(m.size) }}</td>
          <td><TagChips :tags="m.tags" /></td>
        </tr>
      </tbody>
    </table>
    <div v-if="!items.length" class="empty">还没有登记模型，试试「扫描模型目录」</div>
  </div>
  <div class="row" style="margin-top:10px"><span>共 {{total}} 项</span><button :disabled="!page" @click="page--">上一页</button><span>{{page+1}}</span><button :disabled="(page+1)*50>=total" @click="page++">下一页</button><RouterLink to="/oc">OC Studio</RouterLink><RouterLink to="/generate">图像生成</RouterLink></div>

  <Modal v-if="scan" title="扫描模型目录" @close="scan = null">
    <div class="grid">
      <label class="field">模型目录（运行 Front 的这台电脑上，例如 SD WebUI 或 ComfyUI 的 models 文件夹）
        <div class="row" style="flex-wrap:nowrap"><input v-model="scanForm.path" class="mono" placeholder="D:/sd-webui/models" @keyup.enter="doScan" /><button class="primary" :disabled="!scanForm.path || busy === 'scan'" @click="doScan">扫描预览</button></div></label>
      <div class="row small">
        <label class="row" style="gap:4px"><input v-model="scanForm.recursive" type="checkbox" style="width:auto" />包含子文件夹</label>
        <label class="row" style="gap:4px"><input v-model="scanForm.compute_hash" type="checkbox" style="width:auto" />登记时计算哈希（SHA256 / AutoV1-3，大模型较慢，后台进行）</label>
        <label class="row" style="gap:4px"><input v-model="scanForm.import_previews" type="checkbox" style="width:auto" />导入同名预览图</label>
      </div>
      <template v-if="scanResult">
        <div class="row"><b>找到 {{ scanResult.total }} 个模型文件</b><span class="badge">新 {{ scanResult.new }}</span><span class="small muted">{{ kindSummary }} · 共 {{ fmt(scanResult.total_size) }}</span></div>
        <div style="max-height:46vh;overflow:auto">
          <table>
            <thead><tr><th /><th>文件</th><th>类型</th><th>底模</th><th>说明文件</th><th>大小</th><th>状态</th></tr></thead>
            <tbody>
              <tr v-for="it in scanResult.items" :key="it.local_path">
                <td><input type="checkbox" style="width:auto" :checked="picked.has(it.local_path)" :disabled="!!it.existing_id" @change="toggle(it.local_path)" /></td>
                <td><span class="mono small">{{ it.relative }}</span><div v-if="it.civitai?.model_name" class="small" style="color:#7dd3fc">{{ it.civitai.model_name }} · {{ it.civitai.version_name }}</div><div v-else-if="it.trigger_words" class="small muted mono">{{ it.trigger_words }}</div></td>
                <td><span class="badge">{{ LABELS.modelKind[it.kind] ?? it.kind }}</span></td>
                <td class="small">{{ it.base_model }}</td>
                <td class="small muted">{{it.diagnostics?.join('；')}}<div>{{ [it.preview && '预览图', it.notes && '说明'].filter(Boolean).join(' · ') }}</div></td>
                <td class="small">{{ fmt(it.size) }}</td>
                <td class="small"><span v-if="it.existing_id" class="muted">已登记</span><span v-else style="color:var(--accent2)">新</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="row"><button :disabled="!scanPage" @click="scanNext(-1)">上一页</button><span>{{scanPage+1}}</span><button :disabled="(scanPage+1)*50>=scanResult.total" @click="scanNext(1)">下一页</button><button @click="pickPage">勾选本页新模型</button></div>
        <div class="row"><span class="small muted">勾选 {{ picked.size }} 个；扫描不代表引擎兼容。大文件Hash在有限后台队列执行。</span><span class="spacer" /><button class="primary" :disabled="!picked.size" @click="register">登记 {{ picked.size }} 个模型</button></div>
      </template>
    </div>
  </Modal>

  <Modal v-if="editing" :title="editing.id ? '编辑模型' : '登记模型'" @close="editing = null">
    <div class="grid">
      <label class="field">本地路径（运行 Front 的这台电脑上）<div class="row" style="flex-wrap:nowrap"><input v-model="editing.local_path" class="mono" placeholder="D:/sd-webui/models/Lora/xxx.safetensors" /><button :disabled="!!busy" @click="inspect(false)">读取信息</button><button :disabled="!!busy" @click="editing.id ? hashOne() : inspect(true)">{{ busy === 'hash' ? '计算中…' : '计算哈希' }}</button></div></label>
      <div class="grid cols-3">
        <label class="field">名称<input v-model="editing.name" /></label>
        <label class="field">类型<select v-model="editing.kind"><option v-for="(l, k) in LABELS.modelKind" :key="k" :value="k">{{ l }}</option></select></label>
        <label class="field">底模<input v-model="editing.base_model" placeholder="SDXL / SD1.5 / Flux…" /></label>
        <label class="field">版本<input v-model="editing.version" /></label>
        <label class="field">文件名<input v-model="editing.file_name" /></label>
        <label class="field">来源链接<input v-model="editing.source_url" /></label>
      </div>
      <label class="field">触发词<input v-model="editing.trigger_words" class="mono" /></label>
      <div v-if="editing.hashes?.SHA256 || editing.sha256" class="card hashes">
        <div v-for="k in ['SHA256', 'AutoV1', 'AutoV2', 'AutoV3']" :key="k" class="row small" style="flex-wrap:nowrap"><b style="width:64px">{{ k }}</b><span class="mono" style="word-break:break-all">{{ editing.hashes?.[k] || (k === 'SHA256' ? editing.sha256?.toUpperCase() : '—') }}</span></div>
      </div>
      <div v-if="editing.id" class="card civ">
        <div class="row"><b>Civitai</b>
          <span v-if="editing.civitai?.model_name" class="small">{{ editing.civitai.model_name }} · {{ editing.civitai.version_name }} · {{ editing.civitai.base_model }}</span>
          <span v-else-if="editing.civitai?.not_found" class="small muted">上次查询未找到</span>
          <span v-else class="small muted">尚未匹配</span>
          <span class="spacer" />
          <a v-if="editing.civitai?.url" class="small" :href="editing.civitai.url" target="_blank" rel="noopener">打开页面 ↗</a>
        </div>
        <div v-if="editing.civitai?.trained_words?.length" class="row small" style="gap:6px"><span class="muted">训练词</span><span v-for="w in editing.civitai.trained_words" :key="w" class="chip mono">{{ w }}</span></div>
        <div class="row small">
          <label class="row" style="gap:4px"><input v-model="civ.overwrite" type="checkbox" style="width:auto" />覆盖已有字段</label>
          <label class="row" style="gap:4px"><input v-model="civ.download_preview" type="checkbox" style="width:auto" />下载预览图</label>
          <span class="spacer" /><QuickSearch :q="editing.civitai?.model_name || editing.name" kind="model" :alts="[editing.name]" /><button :disabled="!!busy" @click="civitaiOne">{{ busy === 'civitai' ? '查询中…' : '☁ 按哈希匹配 Civitai' }}</button>
        </div>
        <div v-if="editing.civitai?.fetched_at" class="small muted">更新于 {{ new Date(editing.civitai.fetched_at).toLocaleString('zh-CN') }}</div>
      </div>
      <label class="field">备注<textarea v-model="editing.notes" /></label>
      <TagPicker v-model="editing.tag_ids" />
      <ModelProfile v-if="editing.id" :key="editing.id" :model-id="editing.id"/>
      <div class="row"><button v-if="editing.id" class="danger" @click="remove">删除登记</button><span class="spacer" /><button class="primary" @click="save">保存</button></div>
    </div>
  </Modal>
</template>
<style scoped>
.hashes, .civ { background: var(--panel2); padding: 10px 12px; display: grid; gap: 6px; }
.model-table {max-width:100%;overflow-x:auto;min-width:0}
</style>
