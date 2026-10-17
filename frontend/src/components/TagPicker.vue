<script setup>
// 按分类展示全部标签，点击切换选中；可就地新建标签
import { computed, onMounted, ref } from 'vue'
import { LABELS, Tags } from '../api'
import { guard } from '../toast'

const props = defineProps({ modelValue: { type: Array, default: () => [] }, categories: Array, allowCreate: { type: Boolean, default: true } })
const emit = defineEmits(['update:modelValue'])
const tags = ref([])
const newName = ref('')
const newCat = ref('custom')

async function load() { tags.value = (await Tags.list({ limit: 500 })).items }
onMounted(load)

const grouped = computed(() => {
  const g = {}
  for (const t of tags.value) {
    if (props.categories && !props.categories.includes(t.category)) continue
    ;(g[t.category] ??= []).push(t)
  }
  return g
})
function toggle(id) {
  const s = new Set(props.modelValue)
  s.has(id) ? s.delete(id) : s.add(id)
  emit('update:modelValue', [...s])
}
async function create() {
  if (!newName.value.trim()) return
  const t = await guard(() => Tags.create({ name: newName.value.trim(), category: newCat.value }))
  newName.value = ''
  await load()
  toggle(t.id)
}
</script>
<template>
  <div class="grid" style="gap:8px">
    <div v-for="(list, cat) in grouped" :key="cat">
      <div class="small muted" style="margin-bottom:4px">{{ LABELS.tagCategory[cat] ?? cat }}</div>
      <div class="row" style="gap:6px">
        <span v-for="t in list" :key="t.id" class="chip click" :class="{ on: modelValue.includes(t.id) }" @click="toggle(t.id)">{{ t.name }}</span>
      </div>
    </div>
    <form v-if="allowCreate" class="row" style="gap:6px" @submit.prevent="create">
      <select v-model="newCat" style="width:100px"><option v-for="(l, k) in LABELS.tagCategory" :key="k" :value="k">{{ l }}</option></select>
      <input v-model="newName" placeholder="新标签" style="width:120px" />
      <button type="submit"><Ico g="＋" /></button>
    </form>
  </div>
</template>
