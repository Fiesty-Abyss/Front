<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../api'
const props = defineProps({ kind: String, entityId: Number })
const kinds={narrator:'叙述者陈述（待核实）',dialogue:'角色说法',inference:'模型推测',unknown:'来源类别未确认'}
const items = ref(null), error = ref(''), offset = ref(0), busy = ref(false)
let sequence = 0, disposed = false
onBeforeUnmount(() => { disposed = true; sequence++ })
watch(() => [props.kind, props.entityId], () => { sequence++; items.value = null; offset.value = 0; busy.value = false; error.value = '' })
async function load() {
  const n = ++sequence; busy.value = true; error.value = ''
  try {
    const data = await api.get(`/api/ai/extract/reviews/evidence/${props.kind}/${props.entityId}`, { offset: offset.value, limit: 50 })
    if (!disposed && n === sequence) items.value = data
  } catch (e) { if (!disposed && n === sequence) error.value = e.message }
  finally { if (!disposed && n === sequence) busy.value = false }
}
</script>
<template>
  <section class="grid evidence">
    <button :disabled="busy" @click="load">读取章节抽取证据</button>
    <p v-if="error" role="alert" class="notice">{{ error }}</p>
    <p v-if="items && !items.length" class="muted small">本记录暂无章节抽取证据；手工/旧版抽取不补造来源。</p>
    <blockquote v-for="(r, i) in items || []" :key="i"><p>{{ r.evidence.quote }}</p><small>{{ r.evidence.chapter_title }} · Unicode字符 {{ r.evidence.start }}–{{ r.evidence.end }}<br/>世界观 #{{ r.world_id }} / 作品 #{{ r.work_id }} / 小说 #{{ r.asset_id }} / 目录 #{{ r.revision }}<br/>{{ kinds[r.evidence.category] || kinds.unknown }} · {{ r.evidence.confidence_source }}；证据仅对应当时正文。</small><p class="mono small">正文 SHA256 {{ r.text_hash }} · 批次 {{ r.batch_id }}</p><RouterLink :to="{path:'/extract',query:{asset:r.asset_id,batch:r.batch_id,world_id:r.world_id,work_id:r.work_id}}">回到抽取审核（选择对应世界观）</RouterLink></blockquote>
    <div v-if="items" class="row"><button :disabled="busy || !offset" @click="offset -= 50; load()">前50项</button><button :disabled="busy || items.length < 50" @click="offset += 50; load()">后50项</button></div>
  </section>
</template>
<style scoped>.evidence{min-width:0}blockquote{margin:0;padding:8px;border-left:2px solid var(--accent);overflow-wrap:anywhere;font-size:12px}</style>
