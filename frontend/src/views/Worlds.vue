<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, Characters, Worlds } from '../api'
import TagPicker from '../components/TagPicker.vue'
import { guard, toast } from '../toast'

const router = useRouter()
const items = ref([])
const cur = ref(null)
const chars = ref([])
const busy = ref(false)

async function load() { items.value = (await Worlds.list({ limit: 500 })).items }
onMounted(async () => { await load(); if (items.value[0]) select(items.value[0]) })
async function select(w) {
  cur.value = w ? { ...w, tag_ids: w.tags.map((t) => t.id) } : { name: '', summary: '', content: '', tag_ids: [] }
  chars.value = w ? (await Characters.list({ world_id: w.id, limit: 500 })).items : []
}
async function save() {
  const w = cur.value
  const body = { name: w.name, summary: w.summary, content: w.content, tag_ids: w.tag_ids }
  const saved = await guard(() => (w.id ? Worlds.update(w.id, body) : Worlds.create(body)), '已保存')
  await load()
  select(saved)
}
async function remove() {
  if (!confirm(`删除世界观「${cur.value.name}」？角色不会被删除。`)) return
  await guard(() => Worlds.remove(cur.value.id), '已删除')
  cur.value = null
  load()
}
async function aiSuggest() {
  busy.value = true
  try {
    const r = await api.post(`/api/ai/worlds/${cur.value.id}/suggest-relations`)
    toast(`AI 提出了 ${r.created.length} 条关系建议，请到关系网确认`)
    router.push({ path: '/graph', query: { world_id: cur.value.id } })
  } catch (e) { toast(e.message, true) } finally { busy.value = false }
}
</script>
<template>
  <div class="grid" style="grid-template-columns: 260px 1fr">
    <aside class="card grid" style="align-content:start;gap:6px">
      <button class="primary" @click="select(null)">＋ 新建世界观</button>
      <div v-for="w in items" :key="w.id" class="card" style="cursor:pointer;padding:10px" :style="cur?.id === w.id ? { borderColor: 'var(--accent)' } : {}" @click="select(w)">
        <b>{{ w.name }}</b><div class="small muted">{{ w.summary?.slice(0, 40) }}</div>
      </div>
    </aside>
    <section v-if="cur" class="card grid">
      <label class="field">名称<input v-model="cur.name" /></label>
      <label class="field">概要<textarea v-model="cur.summary" /></label>
      <label class="field">设定正文（Markdown，AI 关系识别会阅读这里）<textarea v-model="cur.content" style="min-height:240px" /></label>
      <TagPicker v-model="cur.tag_ids" />
      <div v-if="cur.id">
        <div class="small muted" style="margin-bottom:6px">此世界观下的角色（{{ chars.length }}）</div>
        <div class="row"><RouterLink v-for="c in chars" :key="c.id" to="/characters" class="chip">{{ c.name }}</RouterLink></div>
      </div>
      <div class="row">
        <button v-if="cur.id" class="danger" @click="remove">删除</button>
        <RouterLink v-if="cur.id" class="btn" :to="{ path: '/graph', query: { world_id: cur.id } }">查看关系网</RouterLink>
        <button v-if="cur.id" :disabled="busy" @click="aiSuggest">{{ busy ? 'AI 分析中…' : '✦ AI 识别角色关系' }}</button>
        <span class="spacer" /><button class="primary" @click="save">保存</button>
      </div>
    </section>
  </div>
</template>
