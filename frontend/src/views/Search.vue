<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const hits = ref([])
const loading = ref(false)
const error = ref('')
const meta = ref(null)
const status = ref(null)
const NAMES = {
  asset: ['素材', (id) => `/assets?open=${id}`], character: ['角色', (id) => `/characters/${id}`], world: ['世界观', (id) => `/worlds?id=${id}`],
  world_entry: ['百科条目', (id) => `/worlds?entry=${id}`], work: ['作品', (id) => `/works?id=${id}`], prompt: ['提示词', (id) => `/prompts?id=${id}`],
  sd_model: ['SD 模型', () => '/models'], snippet: ['提示词片段', () => '/snippets'], card: ['角色卡', (id) => `/cards?id=${id}`], collection: ['收藏集', (id) => `/collections?id=${id}`],
  lore: ['世界书条目', () => '/lorebooks'],
  note: ['笔记', (id) => `/notes/${id}`],
  diagram: ['图表', (id) => `/diagrams/${id}`],
  galgame: ['游戏库', (id) => `/galgames/${id}`],
}
const MODES = [['keyword', '关键词', '精确子串匹配（FTS5）'], ['semantic', '语义', '按意思相近排序'], ['hybrid', '混合', '关键词 + 语义融合排序']]
const mode = computed(() => MODES.some(([key]) => key === route.query.mode) ? route.query.mode : 'keyword')
const entity = computed(() => route.query.entity || '')
const maxScore = computed(() => Math.max(...hits.value.map((h) => h.score || 0), 0.0001))

async function load() {
  error.value = ''
  hits.value = []
  if (!route.query.q) return
  loading.value = true
  try {
    if (mode.value === 'keyword') {
      hits.value = await api.get('/api/search', { q: route.query.q, entity: entity.value })
      meta.value = null
    } else {
      const r = await api.get('/api/search/semantic', { q: route.query.q, mode: mode.value, entity: entity.value })
      hits.value = r.items
      meta.value = r
      status.value = await api.get('/api/search/semantic/status')
    }
  } catch (e) { error.value = e.message } finally { loading.value = false }
}
watch(() => [route.query.q, mode.value, entity.value], load, { immediate: true })
watch(mode, async (v) => { if (v !== 'keyword') status.value = await api.get('/api/search/semantic/status') }, { immediate: true })
const setQ = (patch) => router.replace({ query: { ...route.query, ...patch } })
</script>
<template>
  <div class="card row" style="margin-bottom:12px;gap:10px">
    <span class="small muted">检索方式</span>
    <span v-for="[k, label, tip] in MODES" :key="k" class="chip click" :class="{ on: mode === k }" :title="tip" @click="setQ({ mode: k })">{{ label }}</span>
    <select :value="entity" style="width:auto" @change="setQ({ entity: $event.target.value || undefined })">
      <option value="">全部类型</option><option v-for="(v, k) in NAMES" :key="k" :value="k">{{ v[0] }}</option>
    </select>
    <span class="spacer" />
    <span v-if="mode !== 'keyword' && status" class="small muted">
      向量：<span class="mono">{{ status.model || '未配置' }}</span> · 已索引 {{ status.indexed }} / {{ status.total }}
      <template v-if="status.backend === 'local'"> · 本地 n-gram 向量只能找到用词相近的内容，在 <RouterLink to="/settings">设置</RouterLink> 里换成嵌入模型才是真正的语义检索</template>
    </span>
  </div>
  <p class="muted">“{{ $route.query.q }}” 的{{ MODES.find((m) => m[0] === mode)[1] }}搜索结果：{{ loading ? '…' : hits.length + ' 条' }}</p>
  <div v-if="error" class="notice">{{ error }}</div>
  <div class="grid">
    <RouterLink v-for="h in hits" :key="h.entity + h.id" :to="NAMES[h.entity]?.[1]?.(h.id) ?? '/'" class="card row hit" style="flex-wrap:nowrap">
      <span class="badge">{{ NAMES[h.entity]?.[0] ?? h.entity }}</span><b style="white-space:nowrap">{{ h.title }}</b>
      <span class="small muted" style="overflow:hidden;white-space:nowrap;text-overflow:ellipsis;flex:1">{{ h.snippet }}</span>
      <span v-if="h.sources" class="row" style="gap:4px;flex-wrap:nowrap">
        <span v-for="s in h.sources" :key="s" class="chip small">{{ s === 'keyword' ? '关键词' : '语义' }}</span>
      </span>
      <span v-if="h.score != null" class="score" :title="`余弦相似度 ${h.score}`"><i :style="{ width: Math.max(4, (h.score / maxScore) * 100) + '%' }" /><em class="mono">{{ h.score.toFixed(3) }}</em></span>
    </RouterLink>
  </div>
</template>
<style scoped>
.hit { min-width: 0; overflow: hidden; }
.score { display: flex; align-items: center; gap: 6px; width: 150px; flex: none; }
.score i { display: block; height: 6px; border-radius: 99px; background: linear-gradient(90deg, var(--accent), var(--accent2)); }
.score em { white-space: nowrap; font-style: normal; font-size: 11px; color: var(--muted, #9aa0c0); }
</style>
