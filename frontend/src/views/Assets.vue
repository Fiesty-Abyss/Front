<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, Assets, fileUrl, LABELS, thumb, Works, Worlds } from '../api'
import Modal from '../components/Modal.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard, toast } from '../toast'

const route = useRoute()
const router = useRouter()
const f = reactive({ q: '', kind: '', tag: [], year: '', month: '', work_id: route.query.work_id ?? '', world_id: '' })
if (route.query.month) { const [y, m] = String(route.query.month).split('-'); f.year = y; f.month = String(Number(m)) }
const items = ref([])
const total = ref(0)
const works = ref([])
const worlds = ref([])
const editing = ref(null)
const uploading = ref(false)
const uploadForm = reactive({ kind: '', work_id: '', world_id: '', tag_ids: [], work_date: '' })
const fileInput = ref(null)

async function load() {
  const r = await Assets.list({ ...f, limit: 200 })
  items.value = r.items
  total.value = r.total
}
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
watch(f, () => { clearTimeout(timer); timer = setTimeout(load, 200) }, { deep: true })

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
function open(a) { aiTags.value = null; editing.value = { ...a, tag_ids: a.tags.map((t) => t.id) } }
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
      <label class="field">类型<select v-model="f.kind"><option value="">全部</option><option v-for="(l, k) in LABELS.assetKind" :key="k" :value="k">{{ l }}</option></select></label>
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
      <div class="row" style="margin-bottom:12px">
        <span class="muted">共 {{ total }} 项</span><span class="spacer" />
        <button @click="newText"><Ico g="＋" />文本 / 小说</button>
        <button class="primary" @click="uploading = true"><Ico g="⇪" />上传文件</button>
      </div>
      <div v-if="!items.length" class="empty card">没有符合条件的素材</div>
      <div v-reveal class="thumbgrid gallery">
        <div v-for="a in items" :key="a.id" class="tile" :class="{ textual: !a.width }" @click="open(a)">
          <div class="img" :style="a.width ? { backgroundImage: `url(${thumb(a.id)})` } : {}">{{ a.width ? '' : (a.kind === 'novel' ? '📖' : '▢') }}</div>
          <div class="meta">
            <div class="title">{{ a.title }}</div>
            <div class="row small muted" style="gap:6px"><span class="badge">{{ LABELS.assetKind[a.kind] }}</span>{{ a.work_date }}</div>
          </div>
        </div>
      </div>
    </section>
  </div>

  <Modal v-if="uploading" title="上传素材" @close="uploading = false">
    <div class="grid">
      <input ref="fileInput" type="file" multiple />
      <p class="small muted">图片会自动读取尺寸并生成缩略图；带 SD WebUI 出图参数的 PNG 会自动识别为“AI 生成”并提取提示词；.txt/.md 会作为小说导入正文。同一文件不会重复入库。</p>
      <div class="grid cols-3">
        <label class="field">类型（留空自动识别）<select v-model="uploadForm.kind"><option value="">自动</option><option v-for="(l, k) in LABELS.assetKind" :key="k" :value="k">{{ l }}</option></select></label>
        <label class="field">作品<select v-model="uploadForm.work_id"><option value="">无</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select></label>
        <label class="field">日期（默认今天）<input v-model="uploadForm.work_date" type="date" /></label>
      </div>
      <TagPicker v-model="uploadForm.tag_ids" />
      <div class="row"><span class="spacer" /><button class="primary" @click="doUpload">上传</button></div>
    </div>
  </Modal>

  <Modal v-if="editing" :title="editing.id ? '编辑素材' : '新建文本'" @close="editing = null">
    <div class="grid">
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
      <label v-if="editing.kind === 'novel' || editing.content" class="field">正文<textarea v-model="editing.content" style="min-height:220px" /></label>
      <div v-if="editing.meta?.sd" class="card" style="background:var(--panel2)">
        <div class="row"><b>出图参数</b><span class="badge ai">{{ SOURCES[editing.meta.sd.source] ?? 'SD' }}</span><span v-if="editing.meta.sd.node_count" class="badge">{{ editing.meta.sd.node_count }} 个节点</span><span class="spacer" />
          <a v-if="editing.meta.sd.has_workflow || editing.meta.sd.source?.startsWith('comfyui')" class="btn" :href="`/api/assets/${editing.id}/workflow`"><Ico g="⇩" />下载工作流</a>
          <button @click="toPrompt"><Ico g="✎" />存入提示词库</button></div>
        <pre class="prompt">{{ editing.meta.sd.prompt }}</pre>
        <pre v-if="editing.meta.sd.negative_prompt" class="prompt">Negative: {{ editing.meta.sd.negative_prompt }}</pre>
        <div class="row small"><span v-for="(v, k) in editing.meta.sd.params" :key="k" class="badge">{{ k }}: {{ v }}</span></div>
        <div v-if="editing.meta.sd.loras?.length" class="row small" style="margin-top:6px">LoRA：<span v-for="l in editing.meta.sd.loras" :key="l.name" class="chip">{{ l.name }}{{ l.strength != null ? ` × ${l.strength}` : '' }}</span></div>
      </div>
      <p v-if="editing.id" class="small muted">{{ editing.original_name }} · {{ editing.width ? `${editing.width}×${editing.height} · ` : '' }}{{ editing.size ? (editing.size / 1024).toFixed(1) + ' KB' : '' }} <span class="mono">{{ editing.sha256?.slice(0, 16) }}</span></p>
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
      <div class="row"><button v-if="editing.id" class="danger" @click="remove">删除</button><RouterLink v-if="editing.id && editing.content" class="btn" :to="`/read/${editing.id}`">📖 阅读模式</RouterLink>
        <RouterLink v-if="editing.id && editing.kind === 'novel'" class="btn" :to="`/extract?asset=${editing.id}`"><Ico g="⌕" />抽取角色</RouterLink><span class="spacer" /><button class="primary" @click="save">保存</button></div>
    </div>
  </Modal>
</template>

<style scoped>
.aitag { background: var(--panel2); padding: 10px 12px; }
</style>
