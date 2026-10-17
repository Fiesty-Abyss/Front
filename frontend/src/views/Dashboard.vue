<script setup>
import { onMounted, ref } from 'vue'
import { api, Assets, LABELS, thumb } from '../api'

const stats = ref(null)
const recent = ref([])
const timeline = ref([])
onMounted(async () => {
  stats.value = await api.get('/api/stats')
  recent.value = (await Assets.list({ limit: 8 })).items
  const rows = await api.get('/api/assets/stats/timeline')
  const byMonth = {}
  for (const r of rows) (byMonth[r.month] ??= {})[r.kind] = r.count
  timeline.value = Object.entries(byMonth)
})
const cards = [
  ['assets', '素材', '/assets'], ['characters', '角色', '/characters'], ['worlds', '世界观', '/worlds'],
  ['relations', '关系', '/graph'], ['prompts', '提示词', '/prompts'], ['sd_models', 'SD 模型', '/models'],
  ['cards', '角色卡', '/cards'], ['works', '作品', '/works'],
]
</script>
<template>
  <div v-if="stats" class="grid">
    <div class="grid cols-4">
      <RouterLink v-for="[k, label, to] in cards" :key="k" :to="to" class="card stat"><b>{{ stats[k] }}</b><span class="muted">{{ label }}</span></RouterLink>
    </div>
    <div class="grid" style="grid-template-columns: 2fr 1fr">
      <div class="card">
        <div class="row"><h2 style="margin-top:0">最近入库</h2><span class="spacer" /><RouterLink to="/assets" class="muted small">全部 →</RouterLink></div>
        <div class="thumbgrid" style="grid-template-columns: repeat(4, 1fr)">
          <div v-for="a in recent" :key="a.id" class="tile">
            <div class="img" :style="a.width ? { backgroundImage: `url(${thumb(a.id)})` } : {}">{{ a.width ? '' : '✎' }}</div>
            <div class="meta"><div class="title">{{ a.title }}</div><span class="badge">{{ LABELS.assetKind[a.kind] }}</span></div>
          </div>
        </div>
      </div>
      <div class="card">
        <h2 style="margin-top:0">按月份</h2>
        <table>
          <tr v-for="[month, kinds] in timeline" :key="month">
            <td><RouterLink :to="{ path: '/assets', query: { month } }">{{ month }}</RouterLink></td>
            <td><span v-for="(n, k) in kinds" :key="k" class="badge" style="margin-right:4px">{{ LABELS.assetKind[k] }} {{ n }}</span></td>
          </tr>
        </table>
        <p class="small muted">数据目录：<span class="mono">{{ stats.data_dir }}</span></p>
      </div>
    </div>
  </div>
</template>
