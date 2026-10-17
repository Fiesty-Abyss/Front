<script setup>
// 批量添加：每行一个游戏名，逐个按来源顺序自动匹配；匹配不上的先建一个只有标题的条目
import { computed, ref } from 'vue'
import { Check, CircleAlert, CircleDashed, Copy, Loader2 } from 'lucide-vue-next'
import { api } from '../api'
import Modal from './Modal.vue'
import { STATUS, SOURCES } from '../galgame/defs'

const emit = defineEmits(['close', 'done'])
const text = ref('')
const status = ref('wishlist')
const makeWork = ref(true)
const rows = ref([])
const running = ref(false)
const lines = computed(() => [...new Set(text.value.split('\n').map((l) => l.trim()).filter(Boolean))].slice(0, 100))

async function start() {
  running.value = true
  rows.value = lines.value.map((t) => ({ t, state: 'wait' }))
  for (const r of rows.value) {
    r.state = 'run'
    try {
      const o = await api.post('/api/galgames/quick-add', { title: r.t, status: status.value, work: makeWork.value ? 'new' : null })
      Object.assign(r, { state: o.status, id: o.id, title: o.title, source: o.source, score: o.score })
    } catch (e) { Object.assign(r, { state: 'error', err: e.message }) }
  }
  running.value = false
  emit('done')
}
const done = computed(() => rows.value.filter((r) => !['wait', 'run'].includes(r.state)).length)
const LABEL = { matched: '已匹配', unmatched: '未匹配 · 只建了标题', exists: '已在库里', error: '出错' }
</script>

<template>
  <Modal title="批量添加" @close="emit('close')">
    <div v-if="!rows.length" class="grid" style="gap:10px">
      <label class="field">每行一个游戏名（最多 100 行）
        <textarea v-model="text" rows="9" placeholder="【示例】樱色回廊&#10;【示例】雾港夜想曲&#10;……" /></label>
      <div class="row" style="gap:8px"><span class="small muted">状态</span>
        <div class="seg"><button v-for="(s, k) in STATUS" :key="k" :class="{ on: status === k }" @click="status = k">{{ s.label }}</button></div></div>
      <label class="row small" style="gap:6px"><input v-model="makeWork" type="checkbox" />匹配上的游戏同时新建作品（用来挂 CG 档案）</label>
      <p class="small faint" style="margin:0">按“设置 → 游戏库元数据”里的来源顺序逐个查询，名称相似度够高才自动关联；其余的之后可以在详情页手动匹配。</p>
      <div class="row"><span class="small faint">{{ lines.length }} 个</span><span class="spacer" /><button class="primary" :disabled="!lines.length" @click="start">开始添加</button></div>
    </div>
    <div v-else class="grid" style="gap:8px">
      <div class="row small muted">{{ running ? '正在添加…' : '完成' }} {{ done }} / {{ rows.length }}<span class="spacer" /></div>
      <div class="gb-bar"><i :style="{ width: `${(done / rows.length) * 100}%` }" /></div>
      <div class="gb-list">
        <div v-for="r in rows" :key="r.t" class="row gb-row">
          <Loader2 v-if="r.state === 'run'" :size="14" class="spin" />
          <Check v-else-if="r.state === 'matched'" :size="14" class="ok-t" />
          <Copy v-else-if="r.state === 'exists'" :size="14" class="faint" />
          <CircleAlert v-else-if="r.state === 'error'" :size="14" class="danger-t" />
          <CircleDashed v-else :size="14" class="faint" />
          <span class="ellip" style="flex:1">{{ r.t }}</span>
          <span v-if="r.state === 'matched'" class="small muted ellip">→ {{ r.title }} · {{ SOURCES[r.source]?.short }} {{ Math.round(r.score * 100) }}%</span>
          <span v-else-if="LABEL[r.state]" class="small" :class="r.state === 'error' ? 'danger-t' : 'faint'">{{ r.err || LABEL[r.state] }}</span>
          <RouterLink v-if="r.id" :to="`/galgames/${r.id}`" class="small" @click="emit('close')">打开</RouterLink>
        </div>
      </div>
      <div class="row"><span class="spacer" /><button :disabled="running" @click="emit('close')">关闭</button></div>
    </div>
  </Modal>
</template>

<style scoped>
.gb-bar { height: 6px; border-radius: 99px; background: var(--panel2); overflow: hidden; }
.gb-bar i { display: block; height: 100%; background: var(--accent); transition: width .3s var(--ease-out); }
.gb-list { display: grid; gap: 2px; max-height: 50vh; overflow: auto; }
.gb-row { gap: 8px; flex-wrap: nowrap; padding: 6px 4px; border-bottom: 1px solid var(--line); }
.ok-t { color: var(--ok); } .danger-t { color: var(--danger); }
.spin { animation: spin 1s linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }
</style>
