<script setup>
// 把旧版界面里的字符图标统一换成同一套线性图标（lucide），保证粗细与尺寸一致
import { computed } from 'vue'
import { Plus, Pencil, Waypoints, IdCard, Upload, Cloud, Play, ScanSearch, WandSparkles, BookMarked, RefreshCw, Download, X, Box, Copy } from 'lucide-vue-next'
const MAP = { '＋': Plus, '+': Plus, '✎': Pencil, '◈': Waypoints, '▤': IdCard, '⇪': Upload, '☁': Cloud, '▶': Play, '⌕': ScanSearch, '✦': WandSparkles, '❧': BookMarked, '↻': RefreshCw, '⇩': Download, '✕': X, '⬡': Box, '⎘': Copy }
const props = defineProps({ g: String, size: { type: Number, default: 14 } })
const comp = computed(() => MAP[props.g] || Plus)
</script>
<template><component :is="comp" :size="size" :stroke-width="1.9" class="ico-inline" /></template>
