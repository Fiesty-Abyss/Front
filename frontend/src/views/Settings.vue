<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, waitJob } from '../api'
import JobProgress from '../components/JobProgress.vue'
import Modal from '../components/Modal.vue'
import QuickSites from '../components/QuickSites.vue'
import GalSettings from '../components/GalSettings.vue'
import { guard, toast } from '../toast'

const data = ref({ items: [], presets: [], env: null })
const settings = ref(null)
const semantic = ref(null)
const tagger = ref(null)
const editing = ref(null)
const tests = reactive({})
const models = reactive({})
const job = ref(null)

async function load() {
  data.value = await api.get('/api/ai/providers')
  settings.value = await api.get('/api/settings')
  semantic.value = await api.get('/api/search/semantic/status')
}
onMounted(load)
const byId = (id) => data.value.items.find((p) => p.id === id)
const embedders = computed(() => data.value.items.filter((p) => p.embedding_model))
const visions = computed(() => data.value.items.filter((p) => p.vision_model))

function blank(preset) {
  return { name: preset?.name ?? '', base_url: preset?.base_url ?? '', api_key: '', chat_model: preset?.chat_model ?? '', embedding_model: preset?.embedding_model ?? '',
    vision_model: preset?.vision_model ?? '', temperature: 0.8, max_tokens: null, timeout: 120, notes: '', needs_key: preset?.needs_key, use_for_chat: !settings.value.chat_provider_id }
}
function edit(p) { editing.value = { ...p, api_key: '' } }
async function save() {
  const e = editing.value
  const body = { name: e.name, base_url: e.base_url, chat_model: e.chat_model, embedding_model: e.embedding_model, vision_model: e.vision_model,
    temperature: Number(e.temperature), max_tokens: e.max_tokens ? Number(e.max_tokens) : null, timeout: Number(e.timeout), notes: e.notes || null }
  if (e.api_key) body.api_key = e.api_key
  const saved = e.id ? await guard(() => api.patch(`/api/ai/providers/${e.id}`, body), '已保存')
    : await guard(() => api.post('/api/ai/providers', body), '已添加')
  if (!e.id && e.use_for_chat && saved.chat_model) await api.patch('/api/settings', { chat_provider_id: saved.id })
  editing.value = null
  await load()
}
async function clearKey() { await guard(() => api.patch(`/api/ai/providers/${editing.value.id}`, { api_key: '' }), '已清除 API Key'); editing.value = null; load() }
async function remove(p) {
  if (!confirm(`删除「${p.name}」？`)) return
  await guard(() => api.del(`/api/ai/providers/${p.id}`), '已删除'); load()
}
async function test(p) {
  tests[p.id] = { running: true }
  tests[p.id] = await api.post(`/api/ai/providers/${p.id}/test`)
}
async function loadModels(p) {
  try { models[p.id] = (await api.get(`/api/ai/providers/${p.id}/models`)).models } catch (e) { toast(e.message, true) }
}
async function setting(patch) {
  settings.value = await guard(() => api.patch('/api/settings', patch))
  semantic.value = await api.get('/api/search/semantic/status')
}
async function reindex() {
  const j = await guard(() => api.post('/api/search/semantic/index'))
  job.value = j
  await waitJob(j.id, (x) => (job.value = x))
  semantic.value = await api.get('/api/search/semantic/status')
}
async function testTagger() {
  tagger.value = await api.get('/api/ai/tagger/status')
  const j = await guard(() => api.post('/api/ai/tagger/run', { only_untagged: true, apply: true, min_score: 0.6, limit: 50 }))
  job.value = j
  await waitJob(j.id, (x) => (job.value = x))
}
const role = (p) => [settings.value?.chat_provider_id === p.id && '对话', settings.value?.embedding_backend === 'provider' && settings.value?.embedding_provider_id === p.id && '语义检索',
  settings.value?.tagger_backend === 'vision' && settings.value?.vision_provider_id === p.id && '看图打标签'].filter(Boolean)
</script>
<template>
  <section class="card grid" style="margin-bottom:14px">
    <h2 style="margin:0">数据导出</h2>
    <p class="small muted" style="margin:0">将全部世界观、角色、地点、组织、事件、物品、概念与关系说明导出为 Markdown ZIP，解压后打开 README.md 阅读。只导出已保存内容；图片、模型、笔记、角色卡和 API Key 不包含在内。这不是可还原的整库备份。</p>
    <a class="btn" href="/api/exports/encyclopedia" download style="width:max-content">导出全部百科 · Markdown ZIP</a>
  </section>
  <div class="notice" style="margin-bottom:14px">
    AI 服务的 API Key 只保存在本机数据目录的数据库里，接口不会返回原文（只显示末尾几位）；请不要把 Front 暴露到公网。
    所有 AI 功能都是可选的：不配置时其余功能完全可用。
  </div>
  <div class="grid" style="grid-template-columns: 1.25fr 1fr; align-items:start">
    <section class="card grid" style="gap:12px">
      <div class="row"><h2 style="margin:0">AI 服务</h2><span class="small muted">任何 OpenAI 兼容接口</span><span class="spacer" />
        <select style="width:auto" @change="editing = blank(data.presets[$event.target.value]); $event.target.value = ''">
          <option value="">＋ 添加服务…</option><option v-for="(p, i) in data.presets" :key="p.name" :value="i">{{ p.name }}</option><option :value="-1">自定义</option>
        </select>
      </div>
      <div v-if="data.env" class="card small" style="background:var(--panel2)">
        环境变量：<span class="mono">{{ data.env.model }} @ {{ data.env.base_url }}</span>（没有在下面选择对话服务时使用）
      </div>
      <div v-if="!data.items.length" class="empty">还没有添加 AI 服务</div>
      <div v-for="p in data.items" :key="p.id" class="card grid" style="gap:8px;background:var(--panel2)">
        <div class="row">
          <b>{{ p.name }}</b><span v-for="r in role(p)" :key="r" class="chip on">{{ r }}</span>
          <span class="spacer" />
          <button class="ghost small" @click="test(p)">{{ tests[p.id]?.running ? '测试中…' : '测试连接' }}</button>
          <button class="ghost small" @click="edit(p)">编辑</button>
          <button class="ghost small danger" @click="remove(p)">删除</button>
        </div>
        <div class="small mono muted">{{ p.base_url }} · Key：{{ p.api_key_hint || '未设置' }}</div>
        <div class="row small" style="gap:6px">
          <span class="chip">对话 <b class="mono">{{ p.chat_model || '—' }}</b></span>
          <span class="chip">嵌入 <b class="mono">{{ p.embedding_model || '—' }}</b></span>
          <span class="chip">视觉 <b class="mono">{{ p.vision_model || '—' }}</b></span>
          <span class="chip">温度 {{ p.temperature }}</span>
        </div>
        <div v-if="p.notes" class="small muted">{{ p.notes }}</div>
        <div v-if="tests[p.id] && !tests[p.id].running" class="small grid" style="gap:4px">
          <div v-for="k in ['models', 'chat', 'embedding']" v-show="tests[p.id][k]" :key="k" :style="{ color: tests[p.id][k]?.ok ? '#86efac' : '#fca5a5' }">
            {{ { models: '模型列表', chat: '对话', embedding: '嵌入' }[k] }}：{{ tests[p.id][k]?.ok ? '✓' : '✗' }}
            <span class="mono">{{ tests[p.id][k]?.ok ? (k === 'models' ? tests[p.id][k].result.slice(0, 6).join('、') : k === 'embedding' ? `维度 ${tests[p.id][k].result.dim}` : tests[p.id][k].result) : tests[p.id][k]?.error }}</span>
            <span class="muted"> · {{ tests[p.id][k]?.ms }} ms</span>
          </div>
        </div>
      </div>
    </section>

    <div class="grid" style="gap:14px">
      <section v-if="settings" class="card grid" style="gap:10px">
        <h2 style="margin:0">对话 · 抽取角色</h2>
        <label class="small">使用的服务
          <select :value="settings.chat_provider_id ?? ''" @change="setting({ chat_provider_id: $event.target.value ? Number($event.target.value) : null })">
            <option value="">{{ data.env ? '环境变量' : '未配置' }}</option>
            <option v-for="p in data.items.filter((x) => x.chat_model)" :key="p.id" :value="p.id">{{ p.name }} · {{ p.chat_model }}</option>
          </select></label>
        <label class="small">对话里的“我”（默认用户名）<input :value="settings.user_name" @change="setting({ user_name: $event.target.value || 'User' })" /></label>
      </section>

      <section v-if="settings" class="card grid" style="gap:10px">
        <h2 style="margin:0">语义检索</h2>
        <div class="row" style="gap:6px">
          <span class="chip click" :class="{ on: settings.embedding_backend === 'local' }" @click="setting({ embedding_backend: 'local' })">本地 n-gram（离线、近似）</span>
          <span class="chip click" :class="{ on: settings.embedding_backend === 'provider' }" @click="setting({ embedding_backend: 'provider' })">嵌入模型（推荐）</span>
        </div>
        <label v-if="settings.embedding_backend === 'provider'" class="small">嵌入服务
          <select :value="settings.embedding_provider_id ?? ''" @change="setting({ embedding_provider_id: $event.target.value ? Number($event.target.value) : null })">
            <option value="">请选择</option><option v-for="p in embedders" :key="p.id" :value="p.id">{{ p.name }} · {{ p.embedding_model }}</option>
          </select></label>
        <div v-if="semantic" class="small muted">
          当前向量：<span class="mono">{{ semantic.model || '—' }}</span>，已索引 {{ semantic.indexed }} / {{ semantic.total }} 条
          <div v-if="semantic.error" style="color:#fca5a5">{{ semantic.error }}</div>
        </div>
        <div class="row"><button class="ghost" @click="reindex">更新语义索引</button><span class="small muted">只处理新增和改动过的条目</span></div>
      </section>

      <section v-if="settings" class="card grid" style="gap:10px">
        <h2 style="margin:0">自动打标签 <span class="small muted">可选</span></h2>
        <div class="row" style="gap:6px">
          <span v-for="[k, label] in [['off', '关闭'], ['webui', 'WebUI WD14 Tagger（本机）'], ['vision', '视觉模型']]" :key="k" class="chip click" :class="{ on: settings.tagger_backend === k }" @click="setting({ tagger_backend: k })">{{ label }}</span>
        </div>
        <div v-if="settings.tagger_backend === 'webui'" class="small muted">需要 SD WebUI 安装 wd14-tagger 扩展并以 <span class="mono">--api</span> 启动，地址取自 <span class="mono">FRONT_SD_WEBUI_URL</span>。
          <label class="small">Tagger 模型<input :value="settings.tagger_model" @change="setting({ tagger_model: $event.target.value })" /></label></div>
        <label v-if="settings.tagger_backend === 'vision'" class="small">视觉服务
          <select :value="settings.vision_provider_id ?? ''" @change="setting({ vision_provider_id: $event.target.value ? Number($event.target.value) : null })">
            <option value="">请选择</option><option v-for="p in visions" :key="p.id" :value="p.id">{{ p.name }} · {{ p.vision_model }}</option>
          </select></label>
        <label v-if="settings.tagger_backend !== 'off'" class="small">最低把握度 {{ settings.tagger_threshold }}
          <input type="range" min="0.1" max="0.9" step="0.05" :value="settings.tagger_threshold" @change="setting({ tagger_threshold: Number($event.target.value) })" /></label>
        <div class="small muted">识别结果按标签名和<b>别名</b>对上已有标签——给标签加 danbooru 风格的别名（如给「场景」加 scenery），识别结果就会自动归到你的标签体系。</div>
        <div v-if="settings.tagger_backend !== 'off'" class="row"><button class="ghost" @click="testTagger">给没有标签的图片打标签</button><span class="small muted">把握度 ≥ 0.6 且能对上已有标签的才会打上</span></div>
      </section>
      <JobProgress :job="job" />
    </div>
  </div>

  <QuickSites id="quick-search" style="margin-top:14px" />
  <GalSettings style="margin-top:14px" />

  <Modal v-if="editing" :title="editing.id ? '编辑 AI 服务' : '添加 AI 服务'" @close="editing = null">
    <form class="grid" style="gap:10px" @submit.prevent="save">
      <div class="grid cols-2">
        <label>名称<input v-model="editing.name" required /></label>
        <label>接口地址（到 /v1）<input v-model="editing.base_url" required placeholder="http://127.0.0.1:11434/v1" /></label>
      </div>
      <label>API Key <span class="small muted">{{ editing.id ? (editing.api_key_hint ? `已设置（${editing.api_key_hint}），留空不修改` : '未设置') : (editing.needs_key ? '必填' : '本机服务通常不需要') }}</span>
        <input v-model="editing.api_key" type="password" autocomplete="off" placeholder="sk-…" /></label>
      <div class="grid" style="grid-template-columns: repeat(3, 1fr)">
        <label>对话模型<input v-model="editing.chat_model" :list="`m${editing.id}`" /></label>
        <label>嵌入模型<input v-model="editing.embedding_model" :list="`m${editing.id}`" placeholder="可选" /></label>
        <label>视觉模型<input v-model="editing.vision_model" :list="`m${editing.id}`" placeholder="可选" /></label>
      </div>
      <datalist :id="`m${editing.id}`"><option v-for="x in models[editing.id] || []" :key="x" :value="x" /></datalist>
      <div v-if="editing.id" class="small"><a href="#" @click.prevent="loadModels(editing)">从服务读取模型列表</a> <span v-if="models[editing.id]" class="muted">（{{ models[editing.id].length }} 个，输入时可选）</span></div>
      <div class="grid" style="grid-template-columns: repeat(3, 1fr)">
        <label>温度 {{ editing.temperature }}<input v-model="editing.temperature" type="range" min="0" max="2" step="0.05" /></label>
        <label>最大输出 token<input v-model="editing.max_tokens" type="number" min="1" placeholder="不限" /></label>
        <label>超时（秒）<input v-model="editing.timeout" type="number" min="1" /></label>
      </div>
      <label>备注<input v-model="editing.notes" /></label>
      <label v-if="!editing.id" class="row small"><input v-model="editing.use_for_chat" type="checkbox" style="width:auto" />添加后设为对话服务</label>
      <div class="row"><button v-if="editing.id && editing.api_key_set" type="button" class="ghost danger" @click="clearKey">清除 API Key</button><span class="spacer" /><button class="primary">保存</button></div>
    </form>
  </Modal>
</template>
