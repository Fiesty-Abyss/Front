<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, LABELS, Tags } from '../api'
import Modal from '../components/Modal.vue'
import TagTree from '../components/TagTree.vue'
import { guard } from '../toast'

const tree = ref([])
const flat = ref([])
const usage = ref({})
const form = reactive({ name: '', category: 'custom' })
const editing = ref(null)
const mergeInto = ref('')

async function load() {
  ;[tree.value, flat.value, usage.value] = await Promise.all([api.get('/api/tags/tree'), Tags.list({ limit: 500 }).then((r) => r.items), api.get('/api/tags/usage')])
}
onMounted(load)
const grouped = computed(() => { const g = {}; for (const t of tree.value) (g[t.category] ??= []).push(t); return g })
const countIn = (list) => list.reduce((n, t) => n + 1 + countIn(t.children), 0)
async function add() { await guard(() => Tags.create({ ...form }), '已添加'); form.name = ''; load() }
function descendants(id) {
  const out = new Set([id]); let grew = true
  while (grew) { grew = false; for (const t of flat.value) if (t.parent_id && out.has(t.parent_id) && !out.has(t.id)) { out.add(t.id); grew = true } }
  return out
}
function open(t) { editing.value = { ...t, aliasText: t.aliases.join('，') }; mergeInto.value = '' }
const parentOptions = computed(() => {
  if (!editing.value) return []
  const bad = descendants(editing.value.id)
  return flat.value.filter((t) => !bad.has(t.id) && t.category === editing.value.category)
})
const mergeOptions = computed(() => editing.value ? flat.value.filter((t) => !descendants(editing.value.id).has(t.id)) : [])
async function save() {
  const e = editing.value
  const aliases = e.aliasText.split(/[,，、\n]/).map((x) => x.trim()).filter(Boolean)
  await guard(() => Tags.update(e.id, { name: e.name, category: e.category, color: e.color || null, parent_id: e.parent_id || null, aliases }), '已保存')
  editing.value = null; load()
}
async function merge() {
  const target = flat.value.find((t) => t.id === mergeInto.value)
  if (!confirm(`把「${editing.value.name}」合并进「${target.name}」？\n所有使用「${editing.value.name}」的条目会改用「${target.name}」，原名称变成别名，此操作不可撤销。`)) return
  await guard(() => api.post(`/api/tags/${editing.value.id}/merge`, { into_id: target.id }), '已合并')
  editing.value = null; load()
}
async function remove() {
  if (!confirm(`删除标签「${editing.value.name}」？它会从所有条目上移除，子标签会变成顶层标签。`)) return
  await guard(() => Tags.remove(editing.value.id), '已删除')
  editing.value = null; load()
}
</script>
<template>
  <form class="row card" style="margin-bottom:14px" @submit.prevent="add">
    <select v-model="form.category" style="width:140px"><option v-for="(l, k) in LABELS.tagCategory" :key="k" :value="k">{{ l }}</option></select>
    <input v-model="form.name" placeholder="标签名" style="max-width:240px" required /><button class="primary">添加标签</button>
    <span class="small muted">点击标签可编辑：上级（层级）、别名（搜索时同样命中）、颜色，或把重复的标签合并。右侧数字是使用次数（含子标签，同一条目只算一次）；按上级标签筛选时会包含所有子标签。</span>
  </form>
  <div class="grid cols-3" style="align-items:start">
    <div v-for="(list, cat) in grouped" :key="cat" class="card">
      <div class="row" style="margin-bottom:6px"><h2 style="margin:0">{{ LABELS.tagCategory[cat] ?? cat }}</h2><span class="small muted">{{ countIn(list) }} 个</span></div>
      <TagTree :nodes="list" :usage="usage" @open="open" />
    </div>
  </div>

  <Modal v-if="editing" :title="`编辑标签：${editing.name}`" @close="editing = null">
    <div class="grid">
      <div class="grid cols-3">
        <label class="field">名称<input v-model="editing.name" /></label>
        <label class="field">分类<select v-model="editing.category"><option v-for="(l, k) in LABELS.tagCategory" :key="k" :value="k">{{ l }}</option></select></label>
        <div class="field">颜色<div class="row" style="flex-wrap:nowrap"><input type="color" :value="editing.color || '#8b7cf6'" style="height:38px;padding:3px" @input="editing.color = $event.target.value" /><button v-if="editing.color" class="ghost small" title="清除颜色" @click="editing.color = null">清除</button><span v-else class="small muted" style="white-space:nowrap">未设置</span></div></div>
      </div>
      <label class="field">上级标签（同一分类内）<select v-model="editing.parent_id"><option :value="null">无（顶层）</option><option v-for="t in parentOptions" :key="t.id" :value="t.id">{{ t.name }}</option></select></label>
      <label class="field">别名（逗号分隔；搜索和标签筛选会把别名当成同一个标签）<input v-model="editing.aliasText" placeholder="如：gal，美少女游戏" /></label>
      <div class="small muted">使用次数：直接 {{ usage[editing.id]?.direct ?? 0 }}，含子标签共 {{ usage[editing.id]?.total ?? 0 }} 个条目</div>
      <div class="row"><button class="danger" @click="remove">删除</button><span class="spacer" /><button class="primary" @click="save">保存</button></div>
      <div class="card" style="background:var(--panel2)">
        <b>合并到其他标签</b>
        <p class="small muted" style="margin:4px 0 8px">适合整理重复标签，例如把「女性」合并进「女」。</p>
        <div class="row" style="flex-wrap:nowrap">
          <select v-model="mergeInto"><option value="" disabled>选择目标标签…</option><option v-for="t in mergeOptions" :key="t.id" :value="t.id">{{ LABELS.tagCategory[t.category] ?? t.category }} · {{ t.name }}</option></select>
          <button :disabled="!mergeInto" @click="merge">合并</button>
        </div>
      </div>
    </div>
  </Modal>
</template>
