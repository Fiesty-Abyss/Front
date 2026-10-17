<script setup>
import { ref, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const hits = ref([])
const NAMES = {
  asset: ['素材', () => '/assets'], character: ['角色', (id) => `/characters/${id}`], world: ['世界观', (id) => `/worlds?id=${id}`],
  world_entry: ['百科条目', (id) => `/worlds?entry=${id}`], work: ['作品', (id) => `/works?id=${id}`], prompt: ['提示词', (id) => `/prompts?id=${id}`],
  sd_model: ['SD 模型', () => '/models'], snippet: ['提示词片段', () => '/snippets'], card: ['角色卡', (id) => `/cards?id=${id}`], collection: ['收藏集', (id) => `/collections?id=${id}`],
}
watchEffect(async () => { hits.value = route.query.q ? await api.get('/api/search', { q: route.query.q }) : [] })
</script>
<template>
  <p class="muted">“{{ $route.query.q }}” 的搜索结果：{{ hits.length }} 条</p>
  <div class="grid">
    <RouterLink v-for="h in hits" :key="h.entity + h.id" :to="NAMES[h.entity]?.[1]?.(h.id) ?? '/'" class="card row" style="flex-wrap:nowrap">
      <span class="badge">{{ NAMES[h.entity]?.[0] ?? h.entity }}</span><b>{{ h.title }}</b><span class="small muted" style="overflow:hidden;white-space:nowrap;text-overflow:ellipsis">{{ h.snippet }}</span>
    </RouterLink>
  </div>
</template>
