<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, Cards, Lorebooks, streamPost, thumb } from '../api'
import Modal from '../components/Modal.vue'
import { guard, toast } from '../toast'

const route = useRoute()
const status = ref(null)
const sessions = ref([])
const cards = ref([])
const books = ref([])
const cur = ref(null)
const ctx = ref(null)
const input = ref('')
const box = ref(null)
const streaming = ref(null) // { token, text, parentId, lore }
const editing = ref(null) // { msg, text }
const showCtx = ref(false)
const showBooks = ref(false)

async function loadSessions() { sessions.value = await api.get('/api/ai/sessions') }
onMounted(async () => {
  status.value = await api.get('/api/ai/status')
  cards.value = (await Cards.list({ limit: 500 })).items
  books.value = (await Lorebooks.list()).items
  await loadSessions()
  const id = route.query.session ?? sessions.value[0]?.id
  if (id) open(id)
})
const card = computed(() => cards.value.find((c) => c.id === cur.value?.card_id))
const lastMsg = computed(() => cur.value?.messages.at(-1))
async function refreshCtx() { if (cur.value) ctx.value = await api.get(`/api/ai/sessions/${cur.value.id}/context`) }
async function open(id) { cur.value = await api.get(`/api/ai/sessions/${id}`); refreshCtx(); scroll() }
function scroll() { nextTick(() => box.value && (box.value.scrollTop = box.value.scrollHeight)) }
function setSession(s) { cur.value = s; refreshCtx(); loadSessions(); scroll() }

async function generate(body) {
  if (streaming.value) return
  streaming.value = { token: null, text: '', lore: [] }
  if (body.content && !body.edit_id) {
    cur.value.messages.push({ id: 'pending', role: 'user', content: body.content, sibling_ids: [], meta: {} })
  }
  scroll()
  try {
    await streamPost(`/api/ai/sessions/${cur.value.id}/generate`, body, (ev, data) => {
      if (ev === 'start') Object.assign(streaming.value, { token: data.token, lore: data.lore })
      else if (ev === 'delta') { streaming.value.text += data.text; scroll() }
      else if (ev === 'done') setSession(data.session)
      else if (ev === 'error') { toast(data.detail, true); if (data.session) setSession(data.session); else open(cur.value.id) }
    })
  } catch (e) { toast(e.message, true); open(cur.value.id) } finally { streaming.value = null }
}
function send() {
  const text = input.value.trim()
  if (!text) return
  input.value = ''
  generate({ content: text })
}
async function stop() {
  if (streaming.value?.token) await api.post(`/api/ai/generations/${streaming.value.token}/stop`).catch(() => {})
}
async function swipe(msg, dir) {
  const i = msg.sibling_ids.indexOf(msg.id) + dir
  if (i < 0 || i >= msg.sibling_ids.length) return
  setSession(await api.post(`/api/ai/sessions/${cur.value.id}/select`, { message_id: msg.sibling_ids[i] }))
}
const regenerate = (msg) => generate({ regenerate_id: msg.id })
async function saveEdit(branch) {
  const { msg, text } = editing.value
  editing.value = null
  if (branch) return generate({ edit_id: msg.id, content: text })
  setSession(await guard(() => api.patch(`/api/ai/messages/${msg.id}`, { content: text }), '已修改'))
}
async function removeMsg(msg) {
  if (!confirm('删除这条消息以及它之后的全部分支？')) return
  setSession(await guard(() => api.del(`/api/ai/messages/${msg.id}`)))
}
async function newSession(cardId) {
  const c = cards.value.find((x) => x.id === Number(cardId))
  const s = await guard(() => api.post('/api/ai/sessions', { card_id: c.id, title: `与 ${c.name} 的对话`, user_name: status.value?.user_name || 'User' }))
  await loadSessions(); open(s.id)
}
async function rename() {
  const t = prompt('对话标题', cur.value.title)
  if (t) setSession(await api.patch(`/api/ai/sessions/${cur.value.id}`, { title: t }))
}
async function toggleBook(id) {
  const ids = cur.value.lorebook_ids.includes(id) ? cur.value.lorebook_ids.filter((x) => x !== id) : [...cur.value.lorebook_ids, id]
  setSession(await api.patch(`/api/ai/sessions/${cur.value.id}`, { lorebook_ids: ids }))
}
async function remove() {
  if (!confirm('删除这个对话？')) return
  await guard(() => api.del(`/api/ai/sessions/${cur.value.id}`), '已删除'); cur.value = null; loadSessions()
}
/** 把（动作）和 *动作* 渲染成斜体灰字 */
function rich(text) {
  const esc = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))
  return esc(text).replace(/（[^（）]*）|\*[^*\n]+\*/g, (m) => `<i class="act">${m.replace(/^\*|\*$/g, '')}</i>`).replace(/【模拟回复】/g, '<span class="mockbadge">模拟回复</span>')
}
</script>
<template>
  <div v-if="status && !status.available" class="notice" style="margin-bottom:14px">
    AI 服务尚未配置：在 <RouterLink to="/settings">设置</RouterLink> 里添加一个 OpenAI 兼容服务（Ollama、LM Studio、OpenAI、DeepSeek……）并设为对话服务，或设置环境变量
    <span class="mono">FRONT_AI_BASE_URL</span> / <span class="mono">FRONT_AI_MODEL</span>。会话、开场白与历史分支可以照常查看和切换。
  </div>
  <div v-else-if="status" class="small muted" style="margin-bottom:10px">已连接：{{ status.label }} · <span class="mono">{{ status.model }}</span>（流式输出）</div>
  <div class="grid" style="grid-template-columns: 250px 1fr; align-items:start">
    <aside class="card grid" style="align-content:start;gap:8px">
      <select @change="newSession($event.target.value); $event.target.value = ''"><option value="">＋ 选择角色卡开始新对话</option><option v-for="c in cards" :key="c.id" :value="c.id">{{ c.name }}</option></select>
      <div v-for="s in sessions" :key="s.id" class="card sess" :class="{ on: cur?.id === s.id }" @click="open(s.id)">
        <b>{{ s.title }}</b>
        <div class="small muted ell">{{ s.last }}</div>
        <div class="small muted">{{ s.messages }} 条<template v-if="s.total_messages > s.messages"> · 共 {{ s.total_messages }} 条（含分支）</template></div>
      </div>
    </aside>
    <section v-if="cur" class="card" style="display:flex;flex-direction:column;height:calc(100vh - 170px);min-height:560px">
      <div class="row" style="margin-bottom:8px">
        <div class="avatar" style="width:34px;height:34px" :style="card?.avatar_asset_id ? { backgroundImage: `url(${thumb(card.avatar_asset_id)})` } : {}" />
        <b style="cursor:pointer" title="点击改名" @click="rename">{{ cur.title }}</b>
        <span class="small muted">{{ cur.messages.length }} 条 · 共 {{ cur.total_messages }} 条（含分支）</span>
        <span class="spacer" />
        <span v-for="b in ctx?.lorebooks || []" :key="b.id" class="chip" :title="b.world_id ? '世界观自动关联' : ''"><Ico g="❧" />{{ b.name }}</span>
        <button class="ghost small" title="为这个对话额外启用世界书" @click="showBooks = !showBooks"><Ico g="＋" />世界书</button>
        <button class="ghost small" @click="refreshCtx(); showCtx = true">查看上下文</button>
        <button class="ghost small danger" @click="remove">删除</button>
      </div>
      <div v-if="showBooks" class="row small" style="gap:6px;margin-bottom:8px">
        <span class="muted">为这个对话额外启用：</span>
        <span v-for="b in books" :key="b.id" class="chip click" :class="{ on: cur.lorebook_ids.includes(b.id) }" @click="toggleBook(b.id)">{{ b.name }}</span>
        <RouterLink to="/lorebooks" class="small">管理世界书 →</RouterLink>
      </div>
      <div ref="box" class="msgs">
        <div v-for="m in cur.messages" :key="m.id" class="msg" :class="m.role">
          <div v-if="m.role !== 'user'" class="avatar" style="width:38px;height:38px;flex:none" :style="card?.avatar_asset_id ? { backgroundImage: `url(${thumb(card.avatar_asset_id)})` } : {}" />
          <div class="col">
            <div class="bubble" v-html="rich(m.content)" />
            <div class="tools small">
              <span v-if="m.sibling_ids.length > 1" class="swipe">
                <button class="ghost" :disabled="m.sibling_ids[0] === m.id || streaming" @click="swipe(m, -1)">‹</button>
                {{ m.sibling_ids.indexOf(m.id) + 1 }} / {{ m.sibling_ids.length }}
                <button class="ghost" :disabled="m.sibling_ids.at(-1) === m.id || streaming" @click="swipe(m, 1)">›</button>
              </span>
              <span v-if="m.meta?.greeting !== undefined" class="muted">开场白</span>
              <span v-if="m.meta?.lore?.length" class="lore" :title="m.meta.lore.map((l) => `${l.title}（${l.reason}）`).join('\n')"><Ico g="❧" />世界书 {{ m.meta.lore.length }} 条</span>
              <span v-if="m.meta?.interrupted" class="muted">已停止</span>
              <span v-if="m.meta?.edited" class="muted">已修改</span>
              <span v-if="m.meta?.error" style="color:#fca5a5">中断：{{ m.meta.error }}</span>
              <template v-if="m.id !== 'pending' && !streaming">
                <button v-if="m.role === 'assistant' && m.meta?.greeting === undefined" class="ghost" title="重新生成（保留原回复，左右切换）" @click="regenerate(m)"><Ico g="↻" />重新生成</button>
                <button class="ghost" @click="editing = { msg: m, text: m.content }"><Ico g="✎" />编辑</button>
                <button class="ghost" @click="removeMsg(m)">删除</button>
              </template>
            </div>
          </div>
        </div>
        <div v-if="streaming" class="msg assistant">
          <div class="avatar" style="width:38px;height:38px;flex:none" :style="card?.avatar_asset_id ? { backgroundImage: `url(${thumb(card.avatar_asset_id)})` } : {}" />
          <div class="col">
            <div class="bubble"><span v-html="rich(streaming.text)" /><span class="caret">▍</span></div>
            <div class="tools small"><span v-if="streaming.lore?.length" class="lore">❧ 世界书 {{ streaming.lore.length }} 条：{{ streaming.lore.map((l) => l.title).join('、') }}</span><span class="muted">正在生成…</span></div>
          </div>
        </div>
      </div>
      <div v-if="lastMsg?.role === 'user' && !streaming" class="row small" style="margin-top:6px"><span class="muted">最后一条是你的消息，AI 还没有回复。</span><button class="ghost small" @click="generate({})">让 AI 回复</button></div>
      <form class="row" style="margin-top:10px;flex-wrap:nowrap" @submit.prevent="send">
        <textarea v-model="input" placeholder="输入消息…（Ctrl+Enter 发送；用（括号）写动作）" style="min-height:48px" @keydown.ctrl.enter.prevent="send" />
        <button v-if="streaming" type="button" class="danger" @click="stop">■ 停止</button>
        <button v-else class="primary" :disabled="!status?.available">发送</button>
      </form>
    </section>
    <section v-else class="card empty">选择左侧的对话，或用角色卡开始一个新对话</section>
  </div>

  <Modal v-if="editing" :title="editing.msg.role === 'user' ? '编辑消息' : '编辑回复'" @close="editing = null">
    <div class="grid" style="gap:10px">
      <textarea v-model="editing.text" style="min-height:140px" />
      <div class="row">
        <span class="small muted">{{ editing.msg.role === 'user' ? '“另开分支”会保留原消息，在新分支里重新生成回复。' : '直接替换这条回复的文字。' }}</span>
        <span class="spacer" />
        <button class="ghost" @click="saveEdit(false)">直接修改</button>
        <button v-if="editing.msg.role === 'user'" class="primary" :disabled="!status?.available" @click="saveEdit(true)">另开分支并发送</button>
      </div>
    </div>
  </Modal>
  <Modal v-if="showCtx && ctx" title="下一次发送给模型的上下文" @close="showCtx = false">
    <div class="grid" style="gap:10px;max-height:70vh;overflow:auto">
      <div class="small">激活的世界书条目（约 {{ ctx.lore.tokens }} token）：
        <span v-for="l in ctx.lore.active" :key="l.entry_id" class="chip" :title="l.content">{{ l.title }} · {{ l.reason }}</span>
        <span v-if="!ctx.lore.active.length" class="muted">无</span>
        <template v-if="ctx.lore.skipped.length"> · 超出预算被跳过：<span v-for="l in ctx.lore.skipped" :key="l.entry_id" class="chip">{{ l.title }}</span></template>
      </div>
      <div v-for="(m, i) in ctx.messages" :key="i" class="card" style="background:var(--panel2);padding:8px 12px">
        <div class="small muted mono">{{ m.role }}</div><div class="small" style="white-space:pre-wrap">{{ m.content }}</div>
      </div>
    </div>
  </Modal>
</template>
<style scoped>
.sess { cursor: pointer; padding: 10px; overflow: hidden; min-width: 0; }
.sess.on { border-color: var(--accent); }
.ell { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.msgs { flex: 1; overflow: auto; display: grid; gap: 14px; align-content: start; padding-right: 4px; }
.msg { display: flex; gap: 10px; align-items: flex-start; }
.msg.user { flex-direction: row-reverse; }
.col { display: grid; gap: 4px; max-width: 72%; }
.msg.user .col { justify-items: end; }
.bubble { padding: 10px 14px; border-radius: 14px; white-space: pre-wrap; line-height: 1.65; background: var(--panel2); border: 1px solid #ffffff10; }
.msg.user .bubble { background: var(--accent-soft); }
.bubble :deep(.act) { color: #a5a9c8; }
.bubble :deep(.mockbadge) { font-size: 10px; padding: 1px 6px; margin-right: 6px; border-radius: 99px; background: #f472b633; color: #f9a8d4; vertical-align: 2px; }
.tools { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; opacity: .9; }
.tools button { padding: 0 6px; font-size: 12px; }
.swipe { display: inline-flex; align-items: center; gap: 2px; color: #d7d1ff; }
.lore { color: #fcd34d; cursor: help; }
.caret { animation: blink 1s steps(2) infinite; color: var(--accent); }
@keyframes blink { 50% { opacity: 0; } }
</style>
