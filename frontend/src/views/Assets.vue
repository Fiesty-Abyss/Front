<script setup>
import AssetThumb from '../components/AssetThumb.vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, Assets, fileUrl, FILE_KINDS, LABELS, Works, Worlds } from '../api'
import Modal from '../components/Modal.vue'
import TagPicker from '../components/TagPicker.vue'
import FilePreview from '../viewers/FilePreview.vue'
import { guard, toast } from '../toast'

const route = useRoute()
const router = useRouter()
const f = reactive({ q: '', kind: '', tag: [], year: '', month: '', work_id: route.query.work_id ?? '', world_id: '' })
if (route.query.month) { const [y, m] = String(route.query.month).split('-'); f.year = y; f.month = String(Number(m)) }
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 60
const loading = ref(false)
const loadError = ref('')
let loadSequence = 0
const works = ref([])
const worlds = ref([])
const editing = ref(null)
const uploading = ref(false)
const uploadForm = reactive({ kind: '', work_id: '', world_id: '', tag_ids: [], work_date: '' })
const fileInput = ref(null)

async function load() {
  const sequence = ++loadSequence
  loading.value = true; loadError.value = ''
  try {
    const r = await Assets.list({ ...f, limit: pageSize, offset: (page.value - 1) * pageSize })
    if (sequence !== loadSequence) return
    total.value = r.total
    const last = Math.max(1, Math.ceil(r.total / pageSize))
    if (page.value > last) { page.value = last; return load() }
    items.value = r.items
  } catch (e) { if (sequence === loadSequence) loadError.value = e.message }
  finally { if (sequence === loadSequence) loading.value = false }
}
function changePage(value) { page.value = value; load() }
onMounted(async () => {
  works.value = (await Works.list({ limit: 500 })).items
  worlds.value = (await Worlds.list({ limit: 500 })).items
  taggerOn.value = (await api.get('/api/ai/tagger/status')).enabled
  await load()
  if (route.query.open) { const a = await Assets.get(Number(route.query.open)).catch(() => null); if (a) open(a) }
})
const taggerOn = ref(false)
const aiTags = ref(null)
async function suggestTags() {
  aiTags.value = { loading: true, suggestions: [] }
  try { aiTags.value = await api.post(`/api/ai/tagger/assets/${editing.value.id}`) } catch (e) { aiTags.value = null; toast(e.message, true) }
}
function addTag(s) { if (s.tag && !editing.value.tag_ids.includes(s.tag.id)) editing.value.tag_ids = [...editing.value.tag_ids, s.tag.id] }
let timer
watch(f, () => { page.value = 1; clearTimeout(timer); timer = setTimeout(load, 200) }, { deep: true })
onBeforeUnmount(() => { clearTimeout(timer); loadSequence++ })

async function doUpload() {
  const files = fileInput.value?.files ?? []
  for (const file of files) {
    const form = new FormData()
    form.append('file', file)
    for (const k of ['kind', 'work_id', 'world_id', 'work_date']) if (uploadForm[k]) form.append(k, uploadForm[k])
    if (uploadForm.tag_ids.length) form.append('tag_ids', uploadForm.tag_ids.join(','))
    await guard(() => api.upload('/api/assets/upload', form), `已上传 ${file.name}`).catch(() => {})
  }
  uploading.value = false
  load()
}
function newText() {
  editing.value = { title: '', kind: 'novel', content: '', work_date: new Date().toISOString().slice(0, 10), tag_ids: [], meta: {} }
}
async function open(a) {
  aiTags.value = null
  a = await Assets.get(a.id) // All list items omit bodies; always load full detail before editing.
  editing.value = { ...a, tag_ids: a.tags.map((t) => t.id) }
}
function onUpdated(a) { Object.assign(editing.value, { meta: a.meta, kind: a.kind, content: a.content, updated_at: a.updated_at }); load() }
const isFile = computed(() => FILE_KINDS.includes(editing.value?.kind))
// 素材库顶部的类型分段：一组类型对应一个按钮
const GROUPS = [['', '全部'], ['drawing,ai_image,cg,material,reference', '图片'], ['model3d', '3D'], ['live2d', 'Live2D'], ['audio', '音频'], ['video', '视频'], ['pdf,document', '文档'], ['novel,code', '文本'], ['archive', '压缩包']]
async function save() {
  const e = editing.value
  const body = { title: e.title, kind: e.kind, description: e.description, content: e.content, source: e.source, work_date: e.work_date || null, work_id: e.work_id || null, world_id: e.world_id || null, tag_ids: e.tag_ids }
  await guard(() => (e.id ? Assets.update(e.id, body) : Assets.create(body)), '已保存')
  editing.value = null
  load()
}
async function remove() {
  if (!confirm('删除这个素材（以及它的文件）？')) return
  await guard(() => Assets.remove(editing.value.id), '已删除')
  editing.value = null
  load()
}
const SOURCES = { a1111: 'SD WebUI', comfyui: 'ComfyUI', 'comfyui-workflow': 'ComfyUI（界面工作流）' }
async function toPrompt() {
  const r = await guard(() => api.post(`/api/prompts/from-asset/${editing.value.id}`))
  toast(r.reused_prompt ? '已加入现有提示词的模型对比' : '已存入提示词库')
  router.push({ path: '/prompts', query: { id: r.prompt_id } })
}
const years = computed(() => { const y = new Date().getFullYear(); return Array.from({ length: 12 }, (_, i) => y - i) })
</script>

<template>
  <div class="with-filters">
    <aside class="filters card">
      <label class="field">关键词<input v-model="f.q" placeholder="标题 / 正文 / 提示词" /></label>
      <label class="field">类型<select v-model="f.kind"><option value="">全部</option><option v-for="[k, l] in GROUPS.slice(1).filter(([k]) => k.includes(','))" :key="k" :value="k">{{ l }}（全部）</option><option v-for="(l, k) in LABELS.assetKind" :key="k" :value="k">{{ l }}</option></select></label>
      <div class="row" style="flex-wrap:nowrap">
        <label class="field">年<select v-model="f.year"><option value="">全部</option><option v-for="y in years" :key="y">{{ y }}</option></select></label>
        <label class="field">月<select v-model="f.month"><option value="">全部</option><option v-for="m in 12" :key="m">{{ m }}</option></select></label>
      </div>
      <label class="field">作品<select v-model="f.work_id"><option value="">全部</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select></label>
      <label class="field">世界观<select v-model="f.world_id"><option value="">全部</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }}</option></select></label>
      <div class="field small muted">标签（同时满足）</div>
      <TagPicker v-model="f.tag" :allow-create="false" />
    </aside>
    <section>
      <div class="row" style="margin-bottom:14px">
        <div class="seg" role="tablist" aria-label="按类型筛选"><button v-for="[k, l] in GROUPS" :key="l" :class="{ on: f.kind === k }" @click="f.kind = k">{{ l }}</button></div>
        <span class="muted small">共 {{ total }} 项</span><span class="spacer" />
        <button @click="newText"><Ico g="＋" />文本 / 小说</button>
        <button class="primary" @click="uploading = true"><Ico g="⇪" />上传文件</button>
      </div>
      <p v-if="loading" role="status" class="small muted">正在加载素材…</p>
      <div v-if="loadError" role="alert" class="notice">{{ loadError }} <button @click="load">重试</button></div>
      <div v-if="!loading && !loadError && !items.length" class="empty card">没有符合条件的素材</div>
      <div v-reveal class="thumbgrid gallery">
        <div v-for="a in items" :key="a.id" class="tile" @click="open(a)">
          <AssetThumb :asset="a" />
          <div class="meta">
            <div class="title">{{ a.title }}</div>
            <div class="row small muted" style="gap:6px"><span class="badge">{{ LABELS.assetKind[a.kind] }}</span>{{ a.work_date }}</div>
          </div>
        </div>
      </div>
      <nav v-if="total > pageSize" class="row" aria-label="素材分页" style="margin-top:16px">
        <button :disabled="loading || page === 1" @click="changePage(page - 1)">上一页</button>
        <span class="small">第 {{ page }} / {{ Math.ceil(total / pageSize) }} 页 · 每页 {{ pageSize }} 项</span>
        <button :disabled="loading || page >= Math.ceil(total / pageSize)" @click="changePage(page + 1)">下一页</button>
        <button :disabled="loading || page >= Math.ceil(total / pageSize)" @click="changePage(Math.ceil(total / pageSize))">末页</button>
      </nav>
    </section>
  </div>

  <Modal v-if="uploading" title="上传素材" @close="uploading = false">
    <div class="grid">
      <input ref="fileInput" type="file" multiple />
      <p class="small muted">什么都可以放：图片会读取尺寸并识别 SD / ComfyUI 出图参数；3D 模型（glb / gltf / vrm / obj / fbx / pmx）、Live2D 模型包（zip）、音频、视频、PDF、Office 文档、压缩包、代码与脚本会自动识别类型、提取信息和封面；.txt / .md 作为小说导入。
        带贴图的模型（PMX、Live2D、glTF + bin）请把整个文件夹打包成 zip 上传，或者用“批量导入”选中文件夹。同一文件不会重复入库。</p>
      <div class="grid cols-3">
        <label class="field">类型（留空自动识别）<select v-model="uploadForm.kind"><option value="">自动</option><option v-for="(l, k) in LABELS.assetKind" :key="k" :value="k">{{ l }}</option></select></label>
        <label class="field">作品<select v-model="uploadForm.work_id"><option value="">无</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select></label>
        <label class="field">日期（默认今天）<input v-model="uploadForm.work_date" type="date" /></label>
      </div>
      <TagPicker v-model="uploadForm.tag_ids" />
      <div class="row"><span class="spacer" /><button class="primary" @click="doUpload">上传</button></div>
    </div>
  </Modal>

  <Modal v-if="editing" :title="editing.id ? (isFile ? LABELS.assetKind[editing.kind] : '编辑素材') : '新建文本'" :wide="isFile" @close="editing = null">
    <div class="grid">
      <FilePreview v-if="isFile && editing.id" :key="editing.id" :asset="editing" @updated="onUpdated" />
      <img v-if="editing.width" :src="fileUrl(editing.id)" style="max-width:100%;max-height:300px;object-fit:contain;border-radius:10px;background:var(--sunken)" />
      <div class="grid cols-3">
        <label class="field" style="grid-column: span 2">标题<input v-model="editing.title" /></label>
        <label class="field">类型<select v-model="editing.kind"><option v-for="(l, k) in LABELS.assetKind" :key="k" :value="k">{{ l }}</option></select></label>
        <label class="field">日期<input v-model="editing.work_date" type="date" /></label>
        <label class="field">作品<select v-model="editing.work_id"><option :value="null">无</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select></label>
        <label class="field">世界观<select v-model="editing.world_id"><option :value="null">无</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }}</option></select></label>
      </div>
      <label class="field">来源<input v-model="editing.source" placeholder="出处 / 链接" /></label>
      <label class="field">备注<textarea v-model="editing.description" /></label>
      <p v-if="editing.meta?.preview_note" role="status" class="notice">{{ editing.meta.preview_note }}；此处修改仅保存预览正文，不改写原文件。</p>
      <label v-if="!isFile && (editing.kind === 'novel' || editing.content)" class="field">正文<textarea v-model="editing.content" style="min-height:220px" /></label>
      <div v-if="editing.meta?.sd" class="card" style="background:var(--panel2)">
        <div class="row"><b>出图参数</b><span class="badge ai">{{ SOURCES[editing.meta.sd.source] ?? 'SD' }}</span><span v-if="editing.meta.sd.node_count" class="badge">{{ editing.meta.sd.node_count }} 个节点</span><span class="spacer" />
          <a v-if="editing.meta.sd.has_workflow || editing.meta.sd.source?.startsWith('comfyui')" class="btn" :href="`/api/assets/${editing.id}/workflow`"><Ico g="⇩" />下载工作流</a>
          <button @click="toPrompt"><Ico g="✎" />存入提示词库</button></div>
        <pre class="prompt">{{ editing.meta.sd.prompt }}</pre>
        <pre v-if="editing.meta.sd.negative_prompt" class="prompt">Negative: {{ editing.meta.sd.negative_prompt }}</pre>
        <div class="row small"><span v-for="(v, k) in editing.meta.sd.params" :key="k" class="badge">{{ k }}: {{ v }}</span></div>
        <div v-if="editing.meta.sd.loras?.length" class="row small" style="margin-top:6px">LoRA：<span v-for="l in editing.meta.sd.loras" :key="l.name" class="chip">{{ l.name }}{{ l.strength != null ? ` × ${l.strength}` : '' }}</span></div>
      </div>
      <p v-if="editing.id && !isFile" class="small muted">{{ editing.original_name }} · {{ editing.width ? `${editing.width}×${editing.height} · ` : '' }}{{ editing.size ? (editing.size / 1024).toFixed(1) + ' KB' : '' }} <span class="mono">{{ editing.sha256?.slice(0, 16) }}</span></p>
      <TagPicker v-model="editing.tag_ids" />
      <div v-if="editing.id && editing.width" class="card aitag">
        <div class="row"><b>AI 识别标签</b><span class="small muted">{{ taggerOn ? '结果按名称和别名对上已有标签，点击即可加上' : '未开启，可在设置页选择 WebUI Tagger 或视觉模型' }}</span><span class="spacer" />
          <button v-if="taggerOn" class="ghost small" :disabled="aiTags?.loading" @click="suggestTags">{{ aiTags?.loading ? '识别中…' : '识别' }}</button>
          <RouterLink v-else to="/settings" class="small">去设置 →</RouterLink></div>
        <div v-if="aiTags && !aiTags.loading" class="row small" style="gap:6px;margin-top:8px">
          <span v-for="s in aiTags.suggestions" :key="s.name" class="chip" :class="{ click: s.tag, on: s.tag && editing.tag_ids.includes(s.tag.id) }" :title="s.tag ? `对应标签：${s.tag.name}` : '没有对应的标签（可以把它加为某个标签的别名）'" @click="addTag(s)">
            {{ s.tag ? s.tag.name : s.name }}<span v-if="s.tag && s.tag.name !== s.name" class="muted">← {{ s.name }}</span><span class="muted mono">{{ Math.round(s.score * 100) }}%</span>
          </span>
          <span class="muted">（{{ aiTags.backend === 'webui' ? 'WebUI Tagger' : '视觉模型' }}，阈值 {{ aiTags.threshold }}）</span>
        </div>
      </div>
      <div class="row"><button v-if="editing.id" class="danger" @click="remove">删除</button><RouterLink v-if="editing.id && editing.content && !isFile" class="btn" :to="`/read/${editing.id}`">📖 阅读模式</RouterLink>
        <RouterLink v-if="editing.id && editing.kind === 'novel'" class="btn" :to="`/extract?asset=${editing.id}`"><Ico g="⌕" />抽取角色</RouterLink><span class="spacer" /><button class="primary" @click="save">保存</button></div>
    </div>
  </Modal>
</template>

<style scoped>
.aitag { background: var(--panel2); padding: 10px 12px; }
</style>
