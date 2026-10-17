<script setup>
// 没有缩略图的素材：按类型显示一个线性图标 + 扩展名，颜色只是很淡的底色区分
import { computed } from 'vue'
import { Box, Sparkles, Music, Clapperboard, FileText, FileSpreadsheet, Presentation, Archive, FileCode2, BookOpen, File, Image } from 'lucide-vue-next'
const props = defineProps({ asset: Object, size: { type: Number, default: 30 } })
const ext = computed(() => (props.asset?.meta?.file?.ext || (props.asset?.original_name || '').split('.').pop() || '').toLowerCase())
const icon = computed(() => {
  const k = props.asset?.kind
  if (k === 'document') return ['xlsx', 'xls', 'ods'].includes(ext.value) ? FileSpreadsheet : ['pptx', 'ppt', 'odp'].includes(ext.value) ? Presentation : FileText
  return { model3d: Box, live2d: Sparkles, audio: Music, video: Clapperboard, pdf: FileText, archive: Archive, code: FileCode2, novel: BookOpen, drawing: Image, ai_image: Image, cg: Image }[k] || File
})
const HUE = { model3d: 195, live2d: 330, audio: 160, video: 20, pdf: 0, document: 215, archive: 40, code: 265, novel: 280 }
const style = computed(() => { const h = HUE[props.asset?.kind] ?? 240; return { '--h': h } })
</script>
<template>
  <div class="kicon" :style="style">
    <component :is="icon" :size="size" :stroke-width="1.5" />
    <span v-if="ext && asset?.kind !== 'novel'" class="kext">{{ ext }}</span>
  </div>
</template>
<style scoped>
.kicon { width: 100%; height: 100%; display: grid; place-items: center; align-content: center; gap: 8px;
  color: hsl(var(--h) 55% 72%); background: radial-gradient(120% 90% at 50% 0%, hsl(var(--h) 45% 50% / .16), transparent 70%), var(--panel2); }
:root[data-theme="light"] .kicon { color: hsl(var(--h) 45% 42%); }
.kext { font: 600 10.5px/1 var(--font); letter-spacing: .12em; text-transform: uppercase; color: var(--faint); }
</style>
