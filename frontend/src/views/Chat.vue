<script setup>
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, Cards, Lorebooks, streamPost, thumb } from '../api'
import Modal from '../components/Modal.vue'
import { guard, toast } from '../toast'

const ChatModelPicker=defineAsyncComponent(()=>import('../components/ChatModelPicker.vue'))
const modelState=ref(null), showModel=ref(false)
let streamController=null, openSerial=0, contextSerial=0, disposed=false
const route = useRoute()
const status = ref(null)
const sessions = ref([])
const sessionSearch=ref(''),sessionFilter=ref(''),sessionNext=ref(null),sessionBusy=ref(false),sessionCursors=ref([null])
let sessionSerial=0
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

async function loadSessions(reset=true, cursor=null, trail=[null]) {
  if(disposed)return
  const serial=++sessionSerial;sessionBusy.value=true
  try {
    const data=await api.get('/api/ai/sessions/page',{q:sessionFilter.value,limit:50,cursor:reset?null:cursor})
    if(disposed || serial!==sessionSerial)return
    sessions.value=data.items;sessionNext.value=data.next_cursor;sessionCursors.value=reset?[null]:trail
  } catch(e) {if(!disposed && serial===sessionSerial)toast(e.message,true)}
  finally{if(!disposed && serial===sessionSerial)sessionBusy.value=false}
}
function searchSessions(){sessionFilter.value=sessionSearch.value;loadSessions()}
function nextSessionPage(){if(sessionBusy.value || !sessionNext.value)return;const c=sessionNext.value;loadSessions(false,c,[...sessionCursors.value,c])}
function previousSessionPage(){if(sessionBusy.value || sessionCursors.value.length<2)return;const trail=sessionCursors.value.slice(0,-1);loadSessions(false,trail.at(-1),trail)}
onMounted(async () => {
  status.value = await api.get('/api/ai/status')
  cards.value = (await Cards.list({ limit: 500 })).items
  books.value = (await Lorebooks.list()).items
  await loadSessions()
  const id = route.query.session ?? sessions.value[0]?.id
  if (id) open(id)
})
const card = computed(() => cards.value.find((c) => c.id === cur.value?.card_id))
const canGenerate=computed(()=>Boolean(modelState.value?.selection || status.value?.available))
const lastMsg = computed(() => cur.value?.messages.at(-1))
async function refreshCtx(omittedOffset=0) { if (cur.value) {const id=cur.value.id, serial=++contextSerial;ctx.value=null;try{const value=await api.get(`/api/ai/sessions/${id}/context`,{omitted_offset:omittedOffset});if(!disposed && cur.value?.id===id && serial===contextSerial)ctx.value=value}catch(e){if(!disposed && serial===contextSerial)toast(e.message,true)}} }
async function open(id) { if(disposed || streaming.value)return;const serial=++openSerial;const [chat,model]=await Promise.all([api.get(`/api/ai/sessions/${id}`),api.get(`/api/ai/sessions/${id}/model-state`)]);if(disposed || serial!==openSerial)return;cur.value=chat;modelState.value=model;ctx.value=null;showModel.value=false;refreshCtx();scroll() }
function scroll() { nextTick(() => box.value && (box.value.scrollTop = box.value.scrollHeight)) }
function setSession(s) { if(disposed)return;cur.value = s; refreshCtx(); loadSessions(); scroll() }

async function generate(body) {
  if (streaming.value) return false
  const sessionId=cur.value.id
  ++openSerial
  let completed=false, needsReload=false
  streamController=new AbortController()
  streaming.value = { token: null, text: '', lore: [] }
  if (body.content && !body.edit_id) {
    cur.value.messages.push({ id: 'pending', role: 'user', content: body.content, sibling_ids: [], meta: {} })
  }
  scroll()
  try {
    await streamPost(`/api/ai/sessions/${cur.value.id}/generate`, body, (ev, data) => {
      if(disposed || !streaming.value || cur.value?.id!==sessionId)return
      if (ev === 'start') Object.assign(streaming.value, { token: data.token, lore: data.lore })
      else if (ev === 'delta') { streaming.value.text += data.text; scroll() }
      else if (ev === 'done') {completed=true;setSession(data.session)}
      else if (ev === 'error') { toast(data.detail, true); if (data.session) setSession(data.session); else needsReload=true }
    }, streamController.signal)
  } catch (e) { if(!disposed)toast(streamController?.signal.aborted?'已停止本次接收；外部服务可能仍在处理':e.message, !streamController?.signal.aborted);needsReload=true } finally {
    streaming.value = null;streamController=null
    if(needsReload && !disposed && cur.value?.id===sessionId){try{await open(sessionId)}catch(e){toast(e.message,true)}}
  }
  return completed
}
async function send() {
  const text = input.value.trim()
  if (!text) return
  const sent=await generate({ content: text })
  if(sent && input.value.trim()===text)input.value=''
}
async function stop() {
  if (streaming.value?.token) api.post(`/api/ai/generations/${streaming.value.token}/stop`).catch(() => {})
  streamController?.abort()
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
  if(streaming.value)return
  const t = prompt('对话标题', cur.value.title)
  if (t) setSession(await api.patch(`/api/ai/sessions/${cur.value.id}`, { title: t }))
}
async function toggleBook(id) {
  if(streaming.value)return
  const ids = cur.value.lorebook_ids.includes(id) ? cur.value.lorebook_ids.filter((x) => x !== id) : [...cur.value.lorebook_ids, id]
  setSession(await api.patch(`/api/ai/sessions/${cur.value.id}`, { lorebook_ids: ids }))
}
async function remove() {
  if (!confirm('删除这个对话？')) return
  await guard(() => api.del(`/api/ai/sessions/${cur.value.id}`), '已删除'); cur.value = null; loadSessions()
}
function stopReceiving(){if(streaming.value?.token)fetch(`/api/ai/generations/${streaming.value.token}/stop`,{method:'POST',keepalive:true}).catch(()=>{});streamController?.abort()}
onMounted(()=>window.addEventListener('pagehide',stopReceiving))
onBeforeUnmount(()=>{disposed=true;++openSerial;++sessionSerial;++contextSerial;window.removeEventListener('pagehide',stopReceiving);stopReceiving();streaming.value=null})
/** 把（动作）和 *动作* 渲染成斜体灰字 */
function rich(text) {
  const esc = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))
  return esc(text).replace(/（[^（）]*）|\*[^*\n]+\*/g, (m) => `<i class="act">${m.replace(/^\*|\*$/g, '')}</i>`).replace(/【模拟回复】/g, '<span class="mockbadge">模拟回复</span>')
}
</script>
<template>
  <div v-if="status && !status.available && !modelState?.selection" class="notice" style="margin-bottom:14px">
    AI 服务尚未配置：在 <RouterLink to="/settings">设置</RouterLink> 里添加一个 OpenAI 兼容服务（Ollama、LM Studio、OpenAI、DeepSeek……）并设为对话服务，或设置环境变量
    <span class="mono">FRONT_AI_BASE_URL</span> / <span class="mono">FRONT_AI_MODEL</span>。会话、开场白与历史分支可以照常查看和切换。
  </div>
  <div v-else-if="status" class="small muted" style="margin-bottom:10px">所选服务：{{modelState?.selection?.snapshot?.provider_name || status.label}} · <span class="mono">{{modelState?.selection?.snapshot?.model || status.model}}</span>（可用性以实际请求为准）</div>
  <div class="grid chat-layout">
    <aside class="card grid" style="align-content:start;gap:8px">
      <select :disabled="Boolean(streaming)" aria-label="选择角色卡开始对话" @change="newSession($event.target.value); $event.target.value = ''"><option value="">＋ 选择角色卡开始新对话</option><option v-for="c in cards" :key="c.id" :value="c.id">{{ c.name }}</option></select>
      <form class="row" @submit.prevent="searchSessions"><input v-model="sessionSearch" aria-label="按会话名称搜索" placeholder="搜索会话" maxlength="95" style="min-width:0;width:100%"/><button :disabled="sessionBusy">搜索</button></form>
      <button type="button" v-for="s in sessions" :key="s.id" class="card sess" :class="{ on: cur?.id === s.id }" @click="open(s.id)" :disabled="Boolean(streaming)">
        <b>{{ s.title }}</b>
        <div class="small muted ell">{{ s.last }}</div>
        <div class="small muted">共 {{ s.total_messages }} 条（含分支）；详情按需读取</div>
      </button>
      <nav class="row" aria-label="会话分页"><button :disabled="sessionBusy || sessionCursors.length<2" @click="previousSessionPage">上一页</button><span>第 {{sessionCursors.length}} 页</span><button :disabled="sessionBusy || !sessionNext" @click="nextSessionPage">下一页</button></nav>
      <p v-if="!sessions.length && !sessionBusy" class="small muted">没有匹配会话</p>
    </aside>
    <section v-if="cur" class="card chat-pane">
      <div class="row" style="margin-bottom:8px">
        <div class="avatar" style="width:34px;height:34px" :style="card?.avatar_asset_id ? { backgroundImage: `url(${thumb(card.avatar_asset_id)})` } : {}" />
        <button class="ghost" :disabled="Boolean(streaming)" aria-label="重命名会话" @click="rename">{{ cur.title }}</button>
        <span class="small muted">{{ cur.messages.length }} 条 · 共 {{ cur.total_messages }} 条（含分支）</span>
        <span class="spacer" />
        <span v-for="b in ctx?.lorebooks || []" :key="b.id" class="chip" :title="b.world_id ? '世界观自动关联' : ''"><Ico g="❧" />{{ b.name }}</span>
        <button class="ghost small" title="为这个对话额外启用世界书" @click="showBooks = !showBooks"><Ico g="＋" />世界书</button>
        <button class="ghost small" @click="refreshCtx(); showCtx = true">查看上下文</button>
        <button class="ghost small" :disabled="Boolean(streaming)" @click="showModel=!showModel">模型与预算</button>
        <button class="ghost small danger" :disabled="Boolean(streaming)" @click="remove">删除</button>
      </div>
      <ChatModelPicker v-if="showModel" :key="cur.id" :session-id="cur.id" @selected="modelState=$event;refreshCtx()" />
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
              <span v-if="m.meta?.model" class="muted" :title="JSON.stringify(m.meta.parameters || {})">{{m.meta.provider}} · {{m.meta.model}}<template v-if="m.meta.model_selection"> · 配置 #{{m.meta.model_selection.id}}</template></span>
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
        <button v-else class="primary" :disabled="!canGenerate">发送</button>
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
        <button v-if="editing.msg.role === 'user'" class="primary" :disabled="!canGenerate" @click="saveEdit(true)">另开分支并发送</button>
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
      <p v-if="ctx.budget" class="notice">本次 {{ctx.budget.characters}} 字符（不是 token），省略 {{ctx.budget.dropped_messages}} 条消息：{{ctx.budget.dropped_turns}} 个完整问答轮次<span v-if="ctx.budget.dropped_introductions">，另 {{ctx.budget.dropped_introductions}} 个开场白单元</span>。仅影响请求，不删除历史。</p>
      <details v-if="ctx.omitted_messages?.length" open><summary>本次不发送的历史摘要（每页20条，每条前240字符）</summary><div v-for="m in ctx.omitted_messages" :key="m.position" class="card"><b>请求位置 {{m.position}} · {{m.role}} · {{m.characters}} 字符</b><p style="white-space:pre-wrap">{{m.content}}<span v-if="m.truncated">…（摘要，原文仍在会话历史）</span></p></div><nav class="row"><button :disabled="!ctx.omitted_offset" @click="refreshCtx(Math.max(0,ctx.omitted_offset-ctx.omitted_limit))">上页省略摘要</button><span>{{ctx.omitted_offset+1}}–{{ctx.omitted_offset+ctx.omitted_messages.length}} / {{ctx.omitted_total}}</span><button :disabled="ctx.omitted_offset+ctx.omitted_limit>=ctx.omitted_total" @click="refreshCtx(ctx.omitted_offset+ctx.omitted_limit)">下页省略摘要</button></nav></details>
      <div v-for="(m, i) in ctx.messages" :key="i" class="card" style="background:var(--panel2);padding:8px 12px">
        <div class="small muted mono">{{ m.role }}</div><div class="small" style="white-space:pre-wrap">{{ m.content }}</div>
      </div>
    </div>
  </Modal>
</template>
<style scoped>
.chat-layout{grid-template-columns:250px minmax(0,1fr);align-items:start}.chat-pane{display:flex;flex-direction:column;min-width:0;height:calc(100vh - 170px);min-height:560px;overflow:auto}
@media(max-width:800px){.chat-layout{grid-template-columns:minmax(0,1fr)}.chat-pane{height:auto;min-height:600px}.col{max-width:90%}}
@media(prefers-reduced-motion:reduce){.caret{animation:none}}
.sess { text-align:left; width:100%; cursor: pointer; padding: 10px; overflow: hidden; min-width: 0; }
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
