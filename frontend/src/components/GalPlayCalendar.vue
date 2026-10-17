<script setup>
// 游玩日历：最近 N 周每天的游玩时长热力图（列 = 周，行 = 周一到周日）
import { computed } from 'vue'
import { isoDay, fmtMinutes } from '../galgame/defs'

const props = defineProps({ byDay: { type: Object, default: () => ({}) }, weeks: { type: Number, default: 17 } })
const cols = computed(() => {
  const end = new Date()
  const start = new Date(end)
  start.setDate(end.getDate() - ((end.getDay() + 6) % 7) - (props.weeks - 1) * 7)
  const out = []
  for (let w = 0; w < props.weeks; w++) {
    const col = []
    for (let d = 0; d < 7; d++) {
      const day = new Date(start)
      day.setDate(start.getDate() + w * 7 + d)
      const key = isoDay(day)
      col.push({ key, min: props.byDay[key] || 0, future: day > end, month: day.getDate() === 1 ? day.getMonth() + 1 : null })
    }
    out.push(col)
  }
  return out
})
const level = (m) => (m <= 0 ? 0 : m < 30 ? 1 : m < 60 ? 2 : m < 120 ? 3 : 4)
const monthOf = (col) => col.find((c) => c.month)?.month
</script>

<template>
  <div class="gpc" role="img" aria-label="游玩日历">
    <div class="gpc-months"><span v-for="(c, i) in cols" :key="i">{{ monthOf(c) ? `${monthOf(c)}月` : '' }}</span></div>
    <div class="gpc-grid">
      <div v-for="(c, i) in cols" :key="i" class="gpc-col">
        <i v-for="d in c" :key="d.key" :class="[`l${level(d.min)}`, { fut: d.future }]" :title="d.future ? '' : `${d.key} · ${d.min ? fmtMinutes(d.min) : '没有记录'}`" />
      </div>
    </div>
    <div class="gpc-legend small faint">少<i class="l0" /><i class="l1" /><i class="l2" /><i class="l3" /><i class="l4" />多</div>
  </div>
</template>

<style scoped>
.gpc { display: grid; gap: 4px; }
.gpc-months { display: grid; grid-auto-flow: column; grid-auto-columns: 13px; gap: 3px; font-size: 10px; color: var(--faint); height: 12px; white-space: nowrap; }
.gpc-grid { display: grid; grid-auto-flow: column; grid-auto-columns: 13px; gap: 3px; }
.gpc-col { display: grid; grid-template-rows: repeat(7, 13px); gap: 3px; }
i { display: block; width: 13px; height: 13px; border-radius: 3px; background: var(--panel2); }
i.l1 { background: color-mix(in oklab, var(--accent) 30%, var(--panel2)); }
i.l2 { background: color-mix(in oklab, var(--accent) 55%, var(--panel2)); }
i.l3 { background: color-mix(in oklab, var(--accent) 80%, var(--panel2)); }
i.l4 { background: var(--accent-hi); }
i.fut { opacity: 0; }
.gpc-legend { display: flex; align-items: center; gap: 3px; justify-content: flex-end; }
.gpc-legend i { width: 10px; height: 10px; }
</style>
