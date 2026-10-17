<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { composePrompt, LABELS, Prompts, Snippets } from '../api'
import Modal from '../components/Modal.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard, toast } from '../toast'

const router = useRouter()
const items = ref([])
const q = ref('')
const editing = ref(null)
const picked = ref(JSON.parse(sessionStorage.getItem('front.composer') || '[]')) // [{id, weight}]
const base = ref(JSON.parse(sessionStorage.getItem('front.composerBase') || '{"positive":"","negative":""}'))

async function load() { items.value = (await Snippets.list({ limit: 500 })).items }
onMounted(load)
const byId = computed(() => Object.fromEntries(items.value.map((s) => [s.id, s])))
const grouped = computed(() => {
  const g = {}
  const k = q.value.trim().toLowerCase()
  for (const s of items.value) {
    if (k && !`${s.title} ${s.positive} ${s.negative ?? ''}`.toLowerCase().includes(k)) continue
    ;(g[s.category] ??= []).push(s)
  }
  return Object.keys(LABELS.snippetCategory).filter((c) => g[c]).map((c) => [c, g[c]])
})
const persist = () => { sessionStorage.setItem('front.composer', JSON.stringify(picked.value)); sessionStorage.setItem('front.composerBase', JSON.stringify(base.value)) }
function add(s) { if (!picked.value.some((p) => p.id === s.id)) picked.value.push({ id: s.id, weight: 1 }); persist() }
function drop(i) { picked.value.splice(i, 1); persist() }
function move(i, d) { const a = picked.value; const j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; persist() }
const live = computed(() => picked.value.filter((p) => byId.value[p.id]))
const positive = computed(() => composePrompt(base.value.positive, live.value.map((p) => [byId.value[p.id].positive, p.weight])))
const negative = computed(() => composePrompt(base.value.negative, live.value.map((p) => [byId.value[p.id].negative, 1])))
const copy = (s) => navigator.clipboard?.writeText(s).then(() => toast('已复制'))
async function saveAsPrompt() {
  const title = prompt('提示词标题', live.value.map((p) => byId.value[p.id].title.replace('【示例】', '')).slice(0, 3).join(' + '))
  if (!title) return
  const p = await guard(() => Prompts.create({ title, positive: positive.value, negative: negative.value || null, notes: '由提示词片段组合而成' }), '已存入提示词库')
  router.push({ path: '/prompts', query: { id: p.id } })
}
function toGenerate() {
  sessionStorage.setItem('front.generateDraft', JSON.stringify({ positive: positive.value, negative: negative.value }))
  router.push({ path: '/generate', query: { draft: 1 } })
}
function clear() { picked.value = []; base.value = { positive: '', negative: '' }; persist() }

function edit(s) { editing.value = s ? { ...s, tag_ids: s.tags.map((t) => t.id) } : { title: '', category: 'style', positive: '', negative: '', notes: '', position: items.value.length, tag_ids: [] } }
async function save() {
  const { id, created_at, updated_at, tags, ...body } = editing.value
  await guard(() => (id ? Snippets.update(id, body) : Snippets.create(body)), '已保存')
  editing.value = null; load()
}
async function remove() {
  if (!confirm(`删除片段「${editing.value.title}」？`)) return
  await guard(() => Snippets.remove(editing.value.id), '已删除')
  picked.value = picked.value.filter((p) => p.id !== editing.value.id); persist()
  editing.value = null; load()
}
</script>
<template>
  <div class="grid" style="grid-template-columns: 1fr 440px; align-items:start">
    <section class="grid" style="align-content:start">
      <div class="row card" style="padding:10px 14px">
        <input v-model="q" placeholder="搜索片段" style="max-width:260px" />
        <span class="small muted">点击片段加入右侧组合器；✎ 编辑</span>
        <span class="spacer" /><button class="primary" @click="edit(null)"><Ico g="＋" />新片段</button>
      </div>
      <div class="grid cols-2" style="align-items:start">
        <div v-for="[cat, list] in grouped" :key="cat" class="card">
          <div class="row" style="margin-bottom:8px"><h2 style="margin:0">{{ LABELS.snippetCategory[cat] }}</h2><span class="small muted">{{ list.length }}</span></div>
          <div v-for="s in list" :key="s.id" class="snip" :class="{ on: picked.some((p) => p.id === s.id) }" @click="add(s)">
            <div class="row" style="flex-wrap:nowrap"><b>{{ s.title }}</b><span class="spacer" /><a class="small" title="编辑" @click.stop="edit(s)"><Ico g="✎" /></a></div>
            <div v-if="s.positive" class="mono small">{{ s.positive }}</div>
            <div v-if="s.negative" class="mono small neg">− {{ s.negative }}</div>
          </div>
        </div>
      </div>
      <div v-if="!items.length" class="card empty">还没有片段</div>
    </section>
    <aside class="card grid composer" style="align-content:start;position:sticky;top:14px">
      <div class="row"><h2 style="margin:0">组合器</h2><span class="spacer" /><a class="small" @click="clear">清空</a></div>
      <label class="field">基础正向（可选，放在最前）<input v-model="base.positive" class="mono" placeholder="1girl" @input="persist" /></label>
      <div v-if="!live.length" class="small muted">从左边点选片段……</div>
      <div v-for="(p, i) in live" :key="p.id" class="pick row" style="flex-wrap:nowrap">
        <span class="badge">{{ LABELS.snippetCategory[byId[p.id].category] }}</span>
        <b class="small" style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ byId[p.id].title }}</b>
        <input v-model.number="p.weight" type="range" min="0.5" max="1.6" step="0.05" style="width:90px" :disabled="!byId[p.id].positive" @input="persist" />
        <span class="mono small" style="width:34px">{{ (+p.weight).toFixed(2) }}</span>
        <a class="small" @click="move(i, -1)">↑</a><a class="small" @click="move(i, 1)">↓</a><a class="small" @click="drop(i)"><Ico g="✕" /></a>
      </div>
      <label class="field"><span class="row">正向提示词<span class="spacer" /><a class="small" @click="copy(positive)">复制</a></span><textarea class="mono" readonly :value="positive" style="min-height:110px" /></label>
      <label class="field"><span class="row">反向提示词<span class="spacer" /><a class="small" @click="copy(negative)">复制</a></span><textarea class="mono" readonly :value="negative" style="min-height:60px" /></label>
      <label class="field">基础反向（可选）<input v-model="base.negative" class="mono" @input="persist" /></label>
      <div class="row"><button :disabled="!positive" @click="saveAsPrompt">存为提示词</button><span class="spacer" /><button class="primary" :disabled="!positive" @click="toGenerate">去出图 →</button></div>
      <div class="small muted">规则：按顺序用逗号拼接，重复的词只保留一次（不区分大小写）；权重 ≠ 1 时整段写成 <code>(片段:权重)</code>。</div>
    </aside>
  </div>
  <Modal v-if="editing" :title="editing.id ? '编辑片段' : '新片段'" @close="editing = null">
    <div class="grid">
      <div class="grid cols-3">
        <label class="field" style="grid-column: span 2">标题<input v-model="editing.title" /></label>
        <label class="field">分类<select v-model="editing.category"><option v-for="(l, k) in LABELS.snippetCategory" :key="k" :value="k">{{ l }}</option></select></label>
      </div>
      <label class="field">正向<textarea v-model="editing.positive" class="mono" /></label>
      <label class="field">反向（可选）<textarea v-model="editing.negative" class="mono" style="min-height:50px" /></label>
      <label class="field">备注<input v-model="editing.notes" /></label>
      <TagPicker v-model="editing.tag_ids" />
      <div class="row"><button v-if="editing.id" class="danger" @click="remove">删除</button><span class="spacer" /><button class="primary" @click="save">保存</button></div>
    </div>
  </Modal>
</template>
<style scoped>
.snip { padding: 8px 10px; border-radius: 8px; border: 1px solid var(--line); margin-bottom: 6px; cursor: pointer; display: grid; gap: 3px; }
.snip:hover { border-color: var(--accent); }
.snip.on { border-color: var(--accent2); background: var(--accent-soft); }
.snip .neg { color: #fca5a5; }
.pick { padding: 6px 8px; border-radius: 8px; background: var(--panel2); gap: 6px; }
</style>
