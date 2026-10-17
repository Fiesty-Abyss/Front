<script setup>
// 详情页 · 游玩记录：手动记一次游玩（日期 + 时长 + 备注），近 8 周柱状图与时间线
import { computed, onMounted, ref } from 'vue'
import { Plus, Trash2 } from 'lucide-vue-next'
import { api } from '../api'
import { guard } from '../toast'
import { fmtMinutes, isoDay, today } from '../galgame/defs'

const props = defineProps({ game: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const plays = ref([])
const form = ref({ played_on: today(), h: 1, m: 0, note: '' })
async function load() { plays.value = await api.get(`/api/galgames/${props.game.id}/plays`) }
onMounted(load)
async function add() {
  const minutes = (form.value.h | 0) * 60 + (form.value.m | 0)
  if (minutes <= 0) return
  await guard(() => api.post(`/api/galgames/${props.game.id}/plays`, { played_on: form.value.played_on, minutes, note: form.value.note || null }), `已记录 ${fmtMinutes(minutes)}`)
  form.value.note = ''
  await load()
  emit('changed')
}
async function remove(p) {
  if (!confirm(`删除 ${p.played_on} 的这条记录（${fmtMinutes(p.minutes)}）？`)) return
  await guard(() => api.del(`/api/galgames/plays/${p.id}`), '已删除')
  await load()
  emit('changed')
}
// 近 8 周，每周一根柱子
const weeks = computed(() => {
  const now = new Date()
  const monday = new Date(now)
  monday.setDate(now.getDate() - ((now.getDay() + 6) % 7))
  const out = []
  for (let i = 7; i >= 0; i--) {
    const s = new Date(monday)
    s.setDate(monday.getDate() - i * 7)
    const e = new Date(s)
    e.setDate(s.getDate() + 6)
    const [a, b] = [isoDay(s), isoDay(e)]
    out.push({ label: `${s.getMonth() + 1}/${s.getDate()}`, min: plays.value.filter((p) => p.played_on >= a && p.played_on <= b).reduce((n, p) => n + p.minutes, 0) })
  }
  return out
})
const peak = computed(() => Math.max(60, ...weeks.value.map((w) => w.min)))
const total = computed(() => plays.value.reduce((n, p) => n + p.minutes, 0))
</script>

<template>
  <div class="gpl">
    <div class="card grid" style="gap:12px;align-content:start">
      <h3 class="gd-h">记一次游玩</h3>
      <form class="grid" style="gap:10px" @submit.prevent="add">
        <div class="row" style="gap:8px">
          <input v-model="form.played_on" type="date" required style="width:auto" />
          <input v-model.number="form.h" type="number" min="0" max="24" style="width:64px" aria-label="小时" /><span class="small muted">小时</span>
          <input v-model.number="form.m" type="number" min="0" max="59" style="width:64px" aria-label="分钟" /><span class="small muted">分</span>
        </div>
        <input v-model="form.note" maxlength="500" placeholder="备注（可选）：读到哪一章、解锁了什么……" />
        <div class="row"><span class="small faint">Front 不启动游戏，时长手动记；会累加到总游玩时长</span><span class="spacer" /><button class="primary"><Plus :size="15" />记录</button></div>
      </form>
      <div class="gpl-chart" role="img" aria-label="近 8 周游玩时长">
        <div v-for="w in weeks" :key="w.label" class="gpl-bar"><i :style="{ height: `${(w.min / peak) * 100}%` }" :title="fmtMinutes(w.min)" /><span>{{ w.label }}</span></div>
      </div>
      <div class="small muted">记录合计 {{ fmtMinutes(total) }} · {{ plays.length }} 次 · 总游玩 {{ fmtMinutes(game.play_minutes) }}</div>
    </div>
    <div class="card grid" style="gap:8px;align-content:start">
      <h3 class="gd-h">时间线</h3>
      <div v-if="!plays.length" class="empty">还没有游玩记录</div>
      <ol class="gpl-tl">
        <li v-for="p in plays" :key="p.id">
          <i class="gpl-dot" />
          <div class="grid" style="gap:1px;min-width:0"><b>{{ p.played_on }}<span class="muted" style="font-weight:400"> · {{ fmtMinutes(p.minutes) }}</span></b><span v-if="p.note" class="small muted">{{ p.note }}</span></div>
          <button class="iconbtn ghost" title="删除这条记录" @click="remove(p)"><Trash2 :size="14" /></button>
        </li>
      </ol>
    </div>
  </div>
</template>

<style scoped>
.gpl { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.gd-h { margin: 0; font-size: 15px; }
.gpl-chart { display: grid; grid-template-columns: repeat(8, 1fr); gap: 8px; height: 130px; align-items: end; padding: 8px 4px 0; border-top: 1px solid var(--line); }
.gpl-bar { display: grid; grid-template-rows: 1fr auto; height: 100%; gap: 4px; text-align: center; }
.gpl-bar i { align-self: end; display: block; min-height: 2px; border-radius: 6px 6px 2px 2px; background: linear-gradient(var(--accent-hi), var(--accent)); transition: height .4s var(--ease-out); }
.gpl-bar span { font-size: 10px; color: var(--faint); }
.gpl-tl { list-style: none; margin: 0; padding: 0; display: grid; max-height: 420px; overflow: auto; }
.gpl-tl li { display: grid; grid-template-columns: 12px 1fr auto; gap: 12px; align-items: start; padding: 8px 4px 8px 2px; position: relative; }
.gpl-tl li::before { content: ''; position: absolute; left: 7px; top: 0; bottom: 0; width: 2px; background: var(--line); }
.gpl-tl li:first-child::before { top: 14px; }
.gpl-tl li:last-child::before { bottom: calc(100% - 14px); }
.gpl-dot { position: relative; z-index: 1; width: 12px; height: 12px; border-radius: 50%; background: var(--accent); margin-top: 4px; box-shadow: 0 0 0 3px var(--panel); }
@media (max-width: 1000px) { .gpl { grid-template-columns: 1fr; } }
</style>
