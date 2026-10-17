<script setup>
import { ref, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const hits = ref([])
const NAMES = { asset: ['素材', '/assets'], character: ['角色', '/characters'], world: ['世界观', '/worlds'], work: ['作品', '/works'], prompt: ['提示词', '/prompts'], sd_model: ['SD 模型', '/models'], card: ['角色卡', '/cards'], collection: ['收藏集', '/works'] }
watchEffect(async () => { hits.value = route.query.q ? await api.get('/api/search', { q: route.query.q }) : [] })
</script>
<template>
  <p class="muted">“{{ $route.query.q }}” 的搜索结果：{{ hits.length }} 条</p>
  <div class="grid">
    <RouterLink v-for="h in hits" :key="h.entity + h.id" :to="NAMES[h.entity]?.[1] ?? '/'" class="card row" style="flex-wrap:nowrap">
      <span class="badge">{{ NAMES[h.entity]?.[0] ?? h.entity }}</span><b>{{ h.title }}</b><span class="small muted" style="overflow:hidden;white-space:nowrap;text-overflow:ellipsis">{{ h.snippet }}</span>
    </RouterLink>
  </div>
</template>
