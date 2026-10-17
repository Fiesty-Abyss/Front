<script setup>
// 从素材库选一个素材（嵌入笔记用）
import { onMounted, ref, watch } from 'vue'
import { Assets, LABELS } from '../api'
import AssetThumb from './AssetThumb.vue'
import Modal from './Modal.vue'
const emit = defineEmits(['pick', 'close'])
const q = ref('')
const kind = ref('')
const items = ref([])
const KINDS = [['', '全部'], ['drawing,ai_image,cg,material,reference', '图片'], ['model3d,live2d', '模型'], ['audio,video', '音视频'], ['pdf,document,novel,code', '文档'], ['archive', '压缩包']]
async function load() { items.value = (await Assets.list({ q: q.value, kind: kind.value, limit: 60 })).items }
let t
watch([q, kind], () => { clearTimeout(t); t = setTimeout(load, 180) })
onMounted(load)
</script>
<template>
  <Modal title="嵌入素材" wide @close="emit('close')">
    <div class="row" style="margin-bottom:12px">
      <input v-model="q" placeholder="搜索素材标题、正文、标签…" style="max-width:340px" autofocus />
      <div class="seg"><button v-for="[k, l] in KINDS" :key="l" :class="{ on: kind === k }" @click="kind = k">{{ l }}</button></div>
    </div>
    <div class="thumbgrid gallery" style="grid-template-columns: repeat(auto-fill, minmax(150px, 1fr))">
      <div v-for="a in items" :key="a.id" class="tile" @click="emit('pick', a)">
        <AssetThumb :asset="a" />
        <div class="meta"><div class="title">{{ a.title }}</div><div class="small muted">{{ LABELS.assetKind[a.kind] }}</div></div>
      </div>
    </div>
    <div v-if="!items.length" class="empty">没有找到素材</div>
  </Modal>
</template>
