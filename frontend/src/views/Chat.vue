<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, Cards, thumb } from '../api'
import { guard, toast } from '../toast'

const route = useRoute()
const status = ref(null)
const sessions = ref([])
const cards = ref([])
const cur = ref(null)
const input = ref('')
const sending = ref(false)
const box = ref(null)

async function load() { sessions.value = await api.get('/api/ai/sessions') }
onMounted(async () => {
  status.value = await api.get('/api/ai/status')
  cards.value = (await Cards.list({ limit: 500 })).items
  await load()
  const id = route.query.session ?? sessions.value[0]?.id
  if (id) open(id)
})
const cardOf = (id) => cards.value.find((c) => c.id === id)
async function open(id) { cur.value = await api.get(`/api/ai/sessions/${id}`); scroll() }
function scroll() { nextTick(() => box.value && (box.value.scrollTop = box.value.scrollHeight)) }
async function send() {
  if (!input.value.trim()) return
  sending.value = true
  try {
    cur.value = await api.post(`/api/ai/sessions/${cur.value.id}/messages`, { content: input.value })
    input.value = ''
    scroll()
  } catch (e) { toast(e.message, true) } finally { sending.value = false }
}
async function newSession(cardId) {
  const s = await guard(() => api.post('/api/ai/sessions', { card_id: Number(cardId), title: `与 ${cardOf(Number(cardId)).name} 的对话` }))
  await load(); open(s.id)
}
async function remove() {
  if (!confirm('删除这个对话？')) return
  await guard(() => api.del(`/api/ai/sessions/${cur.value.id}`), '已删除'); cur.value = null; load()
}
</script>
<template>
  <div v-if="status && !status.available" class="notice" style="margin-bottom:14px">
    AI 服务尚未配置：设置环境变量 <span class="mono">FRONT_AI_BASE_URL</span>、<span class="mono">FRONT_AI_MODEL</span>（需要时加 <span class="mono">FRONT_AI_API_KEY</span>）后重启即可对话。支持任何 OpenAI 兼容接口（OpenAI、DeepSeek、Ollama、LM Studio 等）。会话与开场白已可正常创建和保存。
  </div>
  <div v-else-if="status" class="small muted" style="margin-bottom:10px">已连接：{{ status.model }} @ {{ status.base_url }}</div>
  <div class="grid" style="grid-template-columns: 260px 1fr">
    <aside class="card grid" style="align-content:start;gap:8px">
      <select @change="newSession($event.target.value); $event.target.value = ''"><option value="">＋ 选择角色卡开始新对话</option><option v-for="c in cards" :key="c.id" :value="c.id">{{ c.name }}</option></select>
      <div v-for="s in sessions" :key="s.id" class="card" style="cursor:pointer;padding:10px" :style="cur?.id === s.id ? { borderColor: 'var(--accent)' } : {}" @click="open(s.id)">
        <b>{{ s.title }}</b><div class="small muted">{{ s.messages }} 条消息</div>
      </div>
    </aside>
    <section v-if="cur" class="card" style="display:flex;flex-direction:column;height:calc(100vh - 200px)">
      <div class="row" style="margin-bottom:10px"><b>{{ cur.title }}</b><span class="spacer" /><button class="ghost danger" @click="remove">删除对话</button></div>
      <div ref="box" style="flex:1;overflow:auto;display:grid;gap:12px;align-content:start">
        <div v-for="m in cur.messages" :key="m.id" class="row" style="flex-wrap:nowrap;align-items:flex-start" :style="m.role === 'user' ? { flexDirection: 'row-reverse' } : {}">
          <div v-if="m.role !== 'user'" class="avatar" style="width:40px;height:40px" :style="cardOf(cur.card_id)?.avatar_asset_id ? { backgroundImage: `url(${thumb(cardOf(cur.card_id).avatar_asset_id)})` } : {}" />
          <div class="card" style="padding:10px 14px;max-width:70%;white-space:pre-wrap" :style="m.role === 'user' ? { background: '#8b7cf633' } : { background: 'var(--panel2)' }">{{ m.content }}</div>
        </div>
      </div>
      <form class="row" style="margin-top:12px;flex-wrap:nowrap" @submit.prevent="send"><textarea v-model="input" placeholder="输入消息…（Ctrl+Enter 发送）" style="min-height:44px" @keydown.ctrl.enter="send" /><button class="primary" :disabled="sending">{{ sending ? '…' : '发送' }}</button></form>
    </section>
  </div>
</template>
