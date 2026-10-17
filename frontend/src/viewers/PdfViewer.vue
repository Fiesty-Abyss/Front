<script setup>
import { ref } from 'vue'
import { ChevronLeft, ChevronRight, ExternalLink } from 'lucide-vue-next'
import { fileUrl } from '../api'
const props = defineProps({ asset: { type: Object, required: true } })
const pages = props.asset.meta?.file?.pages || 0
const page = ref(1)
const go = (d) => { page.value = Math.min(pages, Math.max(1, page.value + d)) }
</script>
<template>
  <div class="pv">
    <div class="pv-stage" tabindex="0" @keydown.left="go(-1)" @keydown.right="go(1)">
      <img :key="page" :src="`/api/assets/${asset.id}/pdf/${page}?width=1100`" :alt="`第 ${page} 页`" />
    </div>
    <div class="row pv-bar">
      <button class="ghost iconbtn" :disabled="page <= 1" aria-label="上一页" @click="go(-1)"><ChevronLeft :size="16" /></button>
      <span class="mono small">{{ page }} / {{ pages }}</span>
      <button class="ghost iconbtn" :disabled="page >= pages" aria-label="下一页" @click="go(1)"><ChevronRight :size="16" /></button>
      <span class="spacer" />
      <a class="btn ghost small" :href="fileUrl(asset.id, true)" target="_blank" rel="noopener"><ExternalLink :size="13" />用浏览器打开</a>
    </div>
  </div>
</template>
<style scoped>
.pv-stage { height: 520px; overflow: auto; display: grid; justify-items: center; padding: 18px; border-radius: var(--radius); background: var(--sunken); border: 1px solid var(--line); outline: none; }
.pv-stage img { max-width: 100%; height: auto; background: #fff; box-shadow: 0 10px 30px -10px rgba(0, 0, 0, .6); border-radius: 2px; }
.pv-bar { margin-top: 8px; gap: 6px; }
</style>
