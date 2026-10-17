<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, Collections, LABELS, Prompts, SDModels, Snippets, thumb, waitJob } from '../api'
import JobProgress from '../components/JobProgress.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard } from '../toast'

const route = useRoute()
const status = ref({})
const prompts = ref([])
const models = ref([])
const snippets = ref([])
const collections = ref([])
const job = ref(null)
const running = ref(false)
const showWorkflow = ref(false)
const AXES = ['model', 'cfg', 'steps', 'sampler', 'scheduler', 'seed', 'size', 'clip_skip', 'prompt_sr', 'lora_weight']

const saved = JSON.parse(localStorage.getItem('front.generateForm') || '{}')
const form = reactive({
  backend: 'webui', prompt_id: '', title: '', positive: '', negative: '', steps: 24, cfg: 7, sampler: '', scheduler: '', seed: -1,
  width: 512, height: 768, clip_skip: '', count: 1, model_ids: [], loras: [], tag_ids: [], collection: 'none', collection_name: '',
  collection_id: '', workflowText: '', ...saved,
})
const ax = reactive({ x: { param: '', text: '', models: [] }, y: { param: '', text: '', models: [] } })

onMounted(async () => {
  ;[status.value, prompts.value, models.value, snippets.value, collections.value] = await Promise.all([
    api.get('/api/generate/status'), Prompts.list({ limit: 500 }).then((r) => r.items), SDModels.list({ limit: 500 }).then((r) => r.items),
    Snippets.list({ limit: 500 }).then((r) => r.items), Collections.list({ limit: 500 }).then((r) => r.items),
  ])
  if (route.query.prompt_id) pickPrompt(Number(route.query.prompt_id))
  if (route.query.draft) {
    const d = JSON.parse(sessionStorage.getItem('front.generateDraft') || '{}')
    Object.assign(form, { prompt_id: '', positive: d.positive || '', negative: d.negative || '' })
  }
  if (!status.value[form.backend]?.ok && status.value[form.backend === 'webui' ? 'comfyui' : 'webui']?.ok) form.backend = form.backend === 'webui' ? 'comfyui' : 'webui'
})
watch(form, (v) => { const { positive, negative, prompt_id, title, ...rest } = v; localStorage.setItem('front.generateForm', JSON.stringify(rest)) }, { deep: true })

function pickPrompt(id) {
  form.prompt_id = id || ''
  const p = prompts.value.find((x) => x.id === Number(id))
  if (!p) return
  form.positive = p.positive; form.negative = p.negative || ''
  const pr = p.params || {}
  if (pr.steps) form.steps = Number(pr.steps)
  if (pr.cfg) form.cfg = Number(pr.cfg)
  if (pr.sampler) form.sampler = pr.sampler
  if (pr.size && /^\d+x\d+$/.test(pr.size)) [form.width, form.height] = pr.size.split('x').map(Number)
}
const st = computed(() => status.value[form.backend] || {})
const opts = computed(() => st.value.options || {})
const checkpoints = computed(() => models.value.filter((m) => m.kind === 'checkpoint'))
const loraModels = computed(() => models.value.filter((m) => ['lora', 'lycoris'].includes(m.kind)))
const nameOf = (id) => models.value.find((m) => m.id === id)?.name
function toggleIn(list, id) { const i = list.indexOf(id); i >= 0 ? list.splice(i, 1) : list.push(id) }
function addLora(id) { if (id && !form.loras.some((l) => l.model_id === id)) form.loras.push({ model_id: id, weight: 0.8 }) }
function insertSnippet(id) {
  const s = snippets.value.find((x) => x.id === Number(id))
  if (!s) return
  if (s.positive) form.positive = [form.positive.trim().replace(/,$/, ''), s.positive].filter(Boolean).join(', ')
  if (s.negative) form.negative = [form.negative.trim().replace(/,$/, ''), s.negative].filter(Boolean).join(', ')
}
function parseValues(a) {
  if (a.param === 'model') return a.models
  return a.text.split(/[,，]/).map((v) => v.trim()).filter(Boolean).map((v) => (['sampler', 'scheduler', 'size', 'prompt_sr'].includes(a.param) ? v : Number(v)))
}
const axisOut = (a) => (a.param && parseValues(a).length ? { param: a.param, values: parseValues(a) } : null)
const implicitModelAxis = computed(() => !axisOut(ax.x) && form.model_ids.length > 1)
const total = computed(() => {
  const xs = axisOut(ax.x)?.values.length || (implicitModelAxis.value ? form.model_ids.length : 1)
  const ys = axisOut(ax.y)?.values.length || 1
  return xs * ys * form.count
})
const PLACEHOLDER = { cfg: '5, 7, 9', steps: '20, 28, 36', sampler: 'Euler a, DPM++ 2M', scheduler: 'Karras, Exponential', seed: '1, 2, 3', size: '512x768, 768x512', clip_skip: '1, 2', prompt_sr: 'night, dawn, sunset（第一个词会被依次替换）', lora_weight: '0.4, 0.7, 1.0' }

async function submit() {
  let workflow = null
  if (form.backend === 'comfyui' && form.workflowText.trim()) {
    try { workflow = JSON.parse(form.workflowText) } catch { return guard(() => Promise.reject(new Error('自定义工作流需要是 API 格式的 JSON'))) }
  }
  const body = {
    backend: form.backend, prompt_id: form.prompt_id || null, title: form.title || null, positive: form.positive, negative: form.negative,
    steps: form.steps, cfg: form.cfg, sampler: form.sampler || null, scheduler: form.scheduler || null, seed: Number(form.seed),
    width: form.width, height: form.height, clip_skip: form.clip_skip ? Number(form.clip_skip) : null, count: form.count,
    model_ids: form.model_ids, loras: form.loras, x: axisOut(ax.x), y: axisOut(ax.y), tag_ids: form.tag_ids, workflow,
    collection_name: form.collection === 'new' ? form.collection_name || null : null,
    collection_id: form.collection === 'existing' ? form.collection_id || null : null,
  }
  running.value = true
  try {
    const j = await guard(() => api.post('/api/generate', body))
    job.value = j
    await waitJob(j.id, (x) => (job.value = { ...x, batch: j.batch, prompt_id: j.prompt_id }), 700)
    prompts.value = (await Prompts.list({ limit: 500 })).items
  } finally { running.value = false }
}
</script>
<template>
  <div class="grid" style="grid-template-columns: 1fr 380px; align-items:start">
    <section class="grid" style="align-content:start">
      <div class="card grid">
        <div class="row">
          <span v-for="b in ['webui', 'comfyui']" :key="b" class="chip click" :class="{ on: form.backend === b }" style="padding:5px 14px;font-size:13px" @click="form.backend = b">
            {{ b === 'webui' ? 'SD WebUI / Forge' : 'ComfyUI' }}
            <span :style="{ color: status[b]?.ok ? '#34d399' : status[b]?.configured ? '#f87171' : '#94a3b8' }">●</span>
          </span>
          <span class="small muted">{{ st.ok ? `已连接 ${st.url}` + (opts.current_model ? ` · 当前模型 ${opts.current_model}` : '') : st.error }}</span>
        </div>
        <div v-if="!st.configured" class="notice small">在启动 Front 前设置环境变量 <code>FRONT_SD_WEBUI_URL=http://127.0.0.1:7860</code>（WebUI 需加 <code>--api</code> 启动）或 <code>FRONT_COMFYUI_URL=http://127.0.0.1:8188</code>。没有显卡想先试试流程，可以运行 <code>python -m front_api.mock_sd</code> 启动模拟接口。</div>
        <div class="grid cols-2">
          <label class="field">从提示词库选择<select :value="form.prompt_id" @change="pickPrompt($event.target.value)"><option value="">（新提示词）</option><option v-for="p in prompts" :key="p.id" :value="p.id">{{ p.title }}</option></select></label>
          <label class="field">插入片段<select value="" @change="insertSnippet($event.target.value); $event.target.value = ''"><option value="">选择一个片段追加到提示词…</option><option v-for="s in snippets" :key="s.id" :value="s.id">{{ LABELS.snippetCategory[s.category] }} · {{ s.title }}</option></select></label>
        </div>
        <label v-if="!form.prompt_id" class="field">新提示词标题（出图后自动存入提示词库）<input v-model="form.title" placeholder="留空则取提示词开头" /></label>
        <label class="field">正向提示词<textarea v-model="form.positive" class="mono" style="min-height:90px" /></label>
        <label class="field">反向提示词<textarea v-model="form.negative" class="mono" style="min-height:50px" /></label>
        <div class="grid cols-4">
          <label class="field">步数<input v-model.number="form.steps" type="number" min="1" max="150" /></label>
          <label class="field">CFG<input v-model.number="form.cfg" type="number" step="0.5" min="0" max="30" /></label>
          <label class="field">采样器<input v-model="form.sampler" list="samplers" placeholder="后端默认" /></label>
          <label class="field">调度器<input v-model="form.scheduler" list="schedulers" placeholder="后端默认" /></label>
          <label class="field">种子（-1 随机）<input v-model.number="form.seed" type="number" /></label>
          <label class="field">宽<input v-model.number="form.width" type="number" step="64" /></label>
          <label class="field">高<input v-model.number="form.height" type="number" step="64" /></label>
          <label class="field">每格张数<input v-model.number="form.count" type="number" min="1" max="8" /></label>
        </div>
        <datalist id="samplers"><option v-for="s in opts.samplers" :key="s" :value="s" /></datalist>
        <datalist id="schedulers"><option v-for="s in opts.schedulers" :key="s" :value="s" /></datalist>
      </div>

      <div class="card grid">
        <div class="row"><h2 style="margin:0">模型</h2><span class="small muted">选多个模型且没设 X 轴时，自动按模型横向对比（同一种子）</span></div>
        <div class="row" style="gap:6px">
          <span v-for="m in checkpoints" :key="m.id" class="chip click" :class="{ on: form.model_ids.includes(m.id) }" @click="toggleIn(form.model_ids, m.id)">{{ m.name }}<span v-if="m.base_model" class="cat"> · {{ m.base_model }}</span></span>
          <span v-if="!checkpoints.length" class="small muted">还没有登记 Checkpoint，将使用后端当前加载的模型</span>
        </div>
        <div class="row" style="gap:8px">
          <select style="width:220px" value="" @change="addLora(Number($event.target.value)); $event.target.value = ''"><option value="">＋ 加 LoRA…</option><option v-for="m in loraModels" :key="m.id" :value="m.id">{{ m.name }}</option></select>
          <span v-for="(l, i) in form.loras" :key="l.model_id" class="pick row" style="flex-wrap:nowrap;gap:6px">
            <b class="small">{{ nameOf(l.model_id) }}</b><input v-model.number="l.weight" type="number" step="0.05" style="width:70px" /><a class="small" @click="form.loras.splice(i, 1)">✕</a>
          </span>
        </div>
      </div>

      <div class="card grid">
        <div class="row"><h2 style="margin:0">XY 网格</h2><span class="small muted">每个轴选一个参数和若干取值，出图后在提示词库里按网格对比</span></div>
        <div v-for="k in ['x', 'y']" :key="k" class="row" style="flex-wrap:nowrap;align-items:flex-start">
          <b style="width:44px;padding-top:8px">{{ k.toUpperCase() }} 轴</b>
          <select v-model="ax[k].param" style="width:150px"><option value="">不使用</option><option v-for="p in AXES" :key="p" :value="p">{{ LABELS.param[p] }}</option></select>
          <div v-if="ax[k].param === 'model'" class="row" style="gap:6px;flex:1">
            <span v-for="m in checkpoints" :key="m.id" class="chip click" :class="{ on: ax[k].models.includes(m.id) }" @click="toggleIn(ax[k].models, m.id)">{{ m.name }}</span>
          </div>
          <input v-else-if="ax[k].param" v-model="ax[k].text" class="mono" :placeholder="'逗号分隔，如 ' + PLACEHOLDER[ax[k].param]" />
        </div>
        <div class="small muted">共 <b style="color:var(--text)">{{ total }}</b> 张{{ implicitModelAxis ? '（X 轴 = 所选模型）' : '' }}；一次最多 100 张。</div>
      </div>

      <div v-if="form.backend === 'comfyui'" class="card grid">
        <div class="row"><h2 style="margin:0">ComfyUI 工作流</h2><span class="small muted">默认用内置文生图模板</span><span class="spacer" /><a class="small" @click="showWorkflow = !showWorkflow">{{ showWorkflow ? '收起' : '使用自定义工作流' }}</a></div>
        <template v-if="showWorkflow">
          <div class="small muted">粘贴 ComfyUI「保存（API 格式）」导出的 JSON，用占位符代替参数：<code v-pre>{{positive}} {{negative}} {{seed}} {{steps}} {{cfg}} {{width}} {{height}} {{sampler}} {{scheduler}} {{model}}</code></div>
          <textarea v-model="form.workflowText" class="mono" style="min-height:140px" placeholder='{"3": {"class_type": "KSampler", "inputs": {"seed": "{{seed}}", ...}}}' />
        </template>
      </div>
    </section>

    <aside class="grid" style="align-content:start;position:sticky;top:14px">
      <div class="card grid">
        <h2 style="margin:0">入库</h2>
        <div class="small muted">每张图都会存进素材库（AI 生成），出图参数写进 PNG，并记录到提示词的对比视图。</div>
        <TagPicker v-model="form.tag_ids" />
        <label class="field">收藏集<select v-model="form.collection"><option value="none">不加入</option><option value="new">新建收藏集</option><option value="existing">加入已有收藏集</option></select></label>
        <input v-if="form.collection === 'new'" v-model="form.collection_name" placeholder="收藏集名称" />
        <select v-if="form.collection === 'existing'" v-model="form.collection_id"><option v-for="c in collections" :key="c.id" :value="c.id">{{ c.name }}</option></select>
        <button class="primary" :disabled="running || !form.positive.trim() || !st.configured" style="justify-content:center;padding:10px" @click="submit">{{ running ? '出图中…' : `✦ 开始出图（${total} 张）` }}</button>
      </div>
      <JobProgress v-if="job" :job="job" />
      <div v-if="job?.result?.items?.length" class="card grid">
        <div class="row"><b>本次出图</b><span class="spacer" />
          <RouterLink v-if="job.status === 'done' && job.prompt_id" class="btn small" :to="{ path: '/prompts', query: { id: job.prompt_id, batch: job.batch } }">查看 XY 网格 →</RouterLink></div>
        <div class="grid" style="grid-template-columns: repeat(3, 1fr); gap:6px">
          <div v-for="it in job.result.items" :key="it.generation_id" class="thumb" :title="it.title" :style="{ backgroundImage: `url(${thumb(it.asset_id)})` }">
            <span v-if="Object.keys(it.xy).length" class="small">{{ Object.values(it.xy).map((a) => a.label).join(' · ') }}</span>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>
<style scoped>
.pick { padding: 4px 8px; border-radius: 8px; background: var(--panel2); }
.thumb { aspect-ratio: 4/5; border-radius: 8px; background: #0b0c18 center/cover; position: relative; }
.thumb span { position: absolute; left: 0; right: 0; bottom: 0; padding: 3px 6px; background: #000a; border-radius: 0 0 8px 8px; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
