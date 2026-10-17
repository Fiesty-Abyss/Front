<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, LABELS, Works, Worlds } from '../api'
import TagPicker from '../components/TagPicker.vue'
import { guard, toast } from '../toast'

const mode = ref('local')
const form = reactive({ path: '', recursive: true, cg_mode: false, kind: '', work_id: '', new_work_title: '', world_id: '', tag_ids: [], use_mtime: true })
const preview = ref(null)
const result = ref(null)
const busy = ref(false)
const works = ref([])
const worlds = ref([])
onMounted(async () => {
  works.value = (await Works.list({ limit: 500 })).items
  worlds.value = (await Worlds.list({ limit: 500 })).items
})
const fmtSize = (n) => (n > 1024 ** 3 ? (n / 1024 ** 3).toFixed(2) + ' GB' : (n / 1024 ** 2).toFixed(1) + ' MB')

async function scan() {
  busy.value = true; result.value = null
  try {
    preview.value = await api.post('/api/import/scan', { path: form.path, recursive: form.recursive, cg_mode: form.cg_mode })
    if (form.cg_mode && !form.work_id && !form.new_work_title) form.new_work_title = preview.value.folder_name
  } catch (e) { toast(e.message, true) } finally { busy.value = false }
}
function payload() {
  return {
    ...form, kind: form.kind || null, work_id: form.work_id || null, world_id: form.world_id || null,
    new_work_title: form.work_id ? null : form.new_work_title || null,
  }
}
async function run() {
  busy.value = true
  try { result.value = await api.post('/api/import/run', payload()); toast(`导入完成：新增 ${result.value.created} 个`) }
  catch (e) { toast(e.message, true) } finally { busy.value = false }
}

// ---- 浏览器选择文件夹（文件从浏览器上传） ----
const picked = ref([])
const progress = reactive({ done: 0, created: 0, dup: 0, failed: 0 })
const ACCEPT = /\.(png|jpe?g|webp|gif|bmp|txt|md)$/i
function onPick(e) { picked.value = [...e.target.files].filter((f) => ACCEPT.test(f.name)); Object.assign(progress, { done: 0, created: 0, dup: 0, failed: 0 }) }
async function ensureWork() {
  if (form.work_id) return form.work_id
  if (!form.new_work_title) return null
  const w = await Works.create({ title: form.new_work_title, kind: form.cg_mode ? 'galgame' : 'other' })
  works.value.unshift(w); form.work_id = w.id
  return w.id
}
async function uploadPicked() {
  if (form.cg_mode && !form.work_id && !form.new_work_title) return toast('CG 模式需要选择作品或填写新作品名', true)
  busy.value = true
  const workId = await ensureWork()
  for (const f of picked.value) {
    const fd = new FormData()
    fd.append('file', f)
    if (form.cg_mode) fd.append('kind', 'cg'); else if (form.kind) fd.append('kind', form.kind)
    if (workId) fd.append('work_id', workId)
    if (form.world_id) fd.append('world_id', form.world_id)
    if (form.tag_ids.length) fd.append('tag_ids', form.tag_ids.join(','))
    if (form.use_mtime) fd.append('work_date', new Date(f.lastModified).toISOString().slice(0, 10))
    try { await api.upload('/api/assets/upload', fd); progress.created++ }
    catch (e) { e.status === 409 ? progress.dup++ : progress.failed++ }
    progress.done++
  }
  if (form.cg_mode && workId) await api.post(`/api/works/${workId}/cg/regroup`)
  busy.value = false
  result.value = { created: progress.created, duplicates: Array(progress.dup), errors: Array(progress.failed), work_id: workId }
}
const pct = computed(() => (picked.value.length ? Math.round((progress.done / picked.value.length) * 100) : 0))
</script>

<template>
  <div class="grid" style="grid-template-columns: 420px 1fr; align-items:start">
    <div class="card grid">
      <div class="row"><span class="chip click" :class="{ on: mode === 'local' }" @click="mode = 'local'">本机文件夹路径</span><span class="chip click" :class="{ on: mode === 'browser' }" @click="mode = 'browser'">从浏览器选择文件夹</span></div>
      <template v-if="mode === 'local'">
        <label class="field">文件夹路径（运行 Front 的这台电脑）<input v-model="form.path" class="mono" placeholder="D:\Games\樱色回廊\CG" @keydown.enter="scan" /></label>
        <p class="small muted" style="margin:0">文件会被复制进数据目录，原文件不会被修改或删除。</p>
      </template>
      <template v-else>
        <input type="file" webkitdirectory multiple @change="onPick" />
        <p class="small muted" style="margin:0">适合 Front 运行在另一台电脑上时使用。已选 {{ picked.length }} 个可导入文件。</p>
      </template>
      <label class="row small"><input v-model="form.recursive" type="checkbox" style="width:auto" />包含子文件夹</label>
      <label class="row small"><input v-model="form.use_mtime" type="checkbox" style="width:auto" />用文件修改时间作为素材日期</label>
      <label class="row small"><input v-model="form.cg_mode" type="checkbox" style="width:auto" /><b>galgame CG 模式</b>：识别差分并按作品归档</label>
      <div class="grid cols-2">
        <label v-if="!form.cg_mode" class="field">类型<select v-model="form.kind"><option value="">自动识别</option><option v-for="(l, k) in LABELS.assetKind" :key="k" :value="k">{{ l }}</option></select></label>
        <label class="field">作品<select v-model="form.work_id"><option value="">{{ form.cg_mode ? '新建作品' : '无' }}</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select></label>
        <label v-if="!form.work_id" class="field">新作品名<input v-model="form.new_work_title" placeholder="默认用文件夹名" /></label>
        <label class="field">世界观<select v-model="form.world_id"><option value="">无</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }}</option></select></label>
      </div>
      <div class="field small muted">统一添加标签</div>
      <TagPicker v-model="form.tag_ids" />
      <div v-if="mode === 'local'" class="row"><button :disabled="busy || !form.path" @click="scan">① 扫描预览</button><span class="spacer" /><button class="primary" :disabled="busy || !preview" @click="run">② 开始导入</button></div>
      <div v-else class="row"><span class="muted small">{{ progress.done }} / {{ picked.length }}（{{ pct }}%）</span><span class="spacer" /><button class="primary" :disabled="busy || !picked.length" @click="uploadPicked">开始上传</button></div>
      <div v-if="mode === 'browser' && busy" style="height:6px;background:var(--panel2);border-radius:3px"><div :style="{ width: pct + '%', height: '100%', background: 'var(--accent)', borderRadius: '3px' }" /></div>
    </div>

    <div class="grid">
      <div v-if="result" class="card">
        <h2 style="margin-top:0">导入结果</h2>
        <div class="row"><span class="badge">新增 {{ result.created }}</span><span class="badge">重复跳过 {{ result.duplicates.length }}</span><span class="badge">失败 {{ result.errors.length }}</span><span v-if="result.cg_groups" class="badge">CG 分组 {{ result.cg_groups }}</span>
          <span class="spacer" /><RouterLink v-if="result.work_id" class="btn primary" :to="{ path: '/works', query: { id: result.work_id } }">查看作品 / CG 档案 →</RouterLink><RouterLink v-else class="btn" to="/assets">到素材库 →</RouterLink></div>
        <div v-for="e in result.errors.filter(Boolean)" :key="e.file" class="small" style="color:var(--danger)">{{ e.file }}：{{ e.error }}</div>
      </div>
      <div v-if="preview" class="card">
        <div class="row"><h2 style="margin:0">扫描预览 · {{ preview.folder_name }}</h2><span class="spacer" /><span class="badge">{{ preview.total }} 个文件</span><span class="badge">{{ fmtSize(preview.total_size) }}</span><span v-for="(n, e) in preview.by_ext" :key="e" class="badge">{{ e }} × {{ n }}</span><span v-if="preview.unsupported" class="badge">跳过不支持 {{ preview.unsupported }}</span></div>
        <template v-if="preview.cg_groups">
          <p class="small muted">识别出 {{ preview.cg_groups.length }} 组 CG（同组 = 同一张 CG 的差分，要求文件名规则一致且分辨率相同）：</p>
          <table>
            <thead><tr><th>CG 组</th><th>分辨率</th><th>差分</th><th>文件</th></tr></thead>
            <tr v-for="g in preview.cg_groups" :key="g.key"><td><b>{{ g.key }}</b></td><td class="muted">{{ g.size }}</td><td><span class="badge">× {{ g.count }}</span></td><td class="mono small">{{ g.items.map((i) => i.name).join('  ') }}</td></tr>
          </table>
        </template>
        <div v-else class="mono small muted" style="max-height:420px;overflow:auto;white-space:pre-line">{{ preview.files.join('\n') }}</div>
      </div>
      <div v-if="!preview && !result" class="card empty">
        填写文件夹路径后点“扫描预览”。<br />支持图片（png / jpg / webp / gif / bmp）与文本（txt / md，自动识别 UTF-8 / GBK / Shift-JIS）。<br />带 SD WebUI 或 ComfyUI 出图信息的 PNG 会自动识别为 AI 图。
      </div>
    </div>
  </div>
</template>
