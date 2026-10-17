<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, Assets, LABELS, waitJob, Works, Worlds } from '../api'
import JobProgress from '../components/JobProgress.vue'
import { guard, toast } from '../toast'

const route = useRoute()
const status = ref(null)
const novels = ref([])
const worlds = ref([])
const works = ref([])
const form = ref({ asset_id: route.query.asset ? Number(route.query.asset) : '', text: '', world_id: '', work_id: '', max_chunks: 20, chunk_size: 3000 })
const usePaste = ref(false)
const job = ref(null)
const rows = ref([])
const applyOpts = ref({ relations: true, update_existing: false })
const done = ref(null)

onMounted(async () => {
  status.value = await api.get('/api/ai/status')
  novels.value = (await Assets.list({ kind: 'novel', limit: 200 })).items
  worlds.value = (await Worlds.list({ limit: 500 })).items
  works.value = (await Works.list({ limit: 500 })).items
  const n = novels.value.find((x) => x.id === form.value.asset_id) || (!form.value.asset_id && novels.value[0])
  if (n) { form.value.asset_id = n.id; form.value.world_id = n.world_id ?? ''; form.value.work_id = n.work_id ?? '' }
})
const novel = computed(() => novels.value.find((x) => x.id === Number(form.value.asset_id)))
function pickNovel(id) {
  form.value.asset_id = Number(id)
  const n = novel.value
  if (n?.world_id) form.value.world_id = n.world_id
  if (n?.work_id) form.value.work_id = n.work_id
}
async function run() {
  done.value = null
  rows.value = []
  const body = { world_id: form.value.world_id || null, max_chunks: Number(form.value.max_chunks), chunk_size: Number(form.value.chunk_size) }
  if (usePaste.value) body.text = form.value.text
  else body.asset_id = Number(form.value.asset_id)
  const j = await guard(() => api.post('/api/ai/extract/characters', body))
  job.value = j
  const fin = await waitJob(j.id, (x) => { job.value = x; if (x.result?.characters) sync(x.result.characters) }, 500)
  if (fin.status === 'done') { sync(fin.result.characters); toast(`找到 ${fin.result.characters.length} 个角色，请核对后写入`) }
}
function sync(chars) {
  const old = Object.fromEntries(rows.value.map((r) => [r.name, r]))
  rows.value = chars.map((c) => ({ ...c, pick: old[c.name]?.pick ?? !c.existing_id, aliasText: (c.aliases || []).join('、'), traitText: (c.traits || []).join('、') }))
}
const picked = computed(() => rows.value.filter((r) => r.pick))
const names = computed(() => new Set(rows.value.flatMap((r) => [r.name, ...r.aliasText.split(/[、,，]/).map((x) => x.trim()).filter(Boolean)])))
async function apply() {
  const split = (s) => s.split(/[、,，]/).map((x) => x.trim()).filter(Boolean)
  const body = {
    characters: picked.value.map((r) => ({ name: r.name, aliases: split(r.aliasText), gender: r.gender, summary: r.summary, traits: split(r.traitText),
      appearance: r.appearance, relations: r.relations, existing_id: r.existing_id })),
    world_id: form.value.world_id || null, work_id: form.value.work_id || null, source: usePaste.value ? null : novel.value?.title, ...applyOpts.value,
  }
  done.value = await guard(() => api.post('/api/ai/extract/apply', body))
  toast(`新建 ${done.value.created.length} 个角色，补充 ${done.value.updated.length} 个，关系 ${done.value.relations} 条（AI 待确认）`)
  rows.value = rows.value.map((r) => (r.pick && !r.existing_id ? { ...r, pick: false, existing_id: -1 } : r))
}
</script>
<template>
  <div v-if="status && !status.available" class="notice" style="margin-bottom:14px">抽取角色需要先在 <RouterLink to="/settings">设置</RouterLink> 里配置 AI 对话服务。</div>
  <div class="grid" style="grid-template-columns: 320px 1fr; align-items:start">
    <section class="card grid" style="gap:10px">
      <h2 style="margin:0">从小说抽取角色</h2>
      <div class="small muted">按章节分段交给 AI，汇总出角色、别名、性别、简介、特征和角色之间的关系。结果需要你勾选核对后才会写入百科；关系以“AI 待确认”写入关系网。</div>
      <div class="row" style="gap:6px"><span class="chip click" :class="{ on: !usePaste }" @click="usePaste = false">素材库里的小说</span><span class="chip click" :class="{ on: usePaste }" @click="usePaste = true">粘贴文本</span></div>
      <label v-if="!usePaste" class="small">小说<select :value="form.asset_id" @change="pickNovel($event.target.value)"><option v-for="n in novels" :key="n.id" :value="n.id">{{ n.title }}</option></select></label>
      <textarea v-else v-model="form.text" placeholder="粘贴小说或设定正文" style="min-height:160px" />
      <label class="small">写入到世界观<select v-model="form.world_id"><option value="">不指定</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }}</option></select></label>
      <label class="small">来源作品<select v-model="form.work_id"><option value="">不指定</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select></label>
      <div class="grid cols-2">
        <label class="small">最多分析几段<input v-model="form.max_chunks" type="number" min="1" max="200" /></label>
        <label class="small">每段字数<input v-model="form.chunk_size" type="number" min="500" step="500" /></label>
      </div>
      <button class="primary" :disabled="!status?.available || ['queued', 'running'].includes(job?.status)" @click="run">开始抽取</button>
      <JobProgress :job="job" />
      <div class="small muted">已在所选世界观中存在的角色会标出来，默认不勾选；勾选“补充已有角色”可把新发现的别名、特征追加进去。</div>
    </section>

    <section class="card grid" style="gap:10px">
      <div class="row"><h2 style="margin:0">抽取结果</h2><span class="small muted">{{ rows.length }} 个角色 · 已勾选 {{ picked.length }}</span><span class="spacer" />
        <label class="row small" style="gap:4px"><input v-model="applyOpts.relations" type="checkbox" style="width:auto" />写入关系（AI 待确认）</label>
        <label class="row small" style="gap:4px"><input v-model="applyOpts.update_existing" type="checkbox" style="width:auto" />补充已有角色</label>
        <button class="primary" :disabled="!picked.length" @click="apply">写入角色百科（{{ picked.length }}）</button></div>
      <div v-if="done" class="notice small">已写入：新建 {{ done.created.length }} 个角色、补充 {{ done.updated.length }} 个、关系 {{ done.relations }} 条。
        <RouterLink to="/characters">去角色百科 →</RouterLink> <RouterLink :to="form.world_id ? `/graph?world=${form.world_id}` : '/graph'">去关系网确认关系 →</RouterLink></div>
      <div v-if="!rows.length" class="empty">选择一篇小说，点击“开始抽取”</div>
      <table v-else class="xtable">
        <thead><tr><th /><th>名字</th><th>别名</th><th>性别</th><th>简介 / 特征</th><th>关系</th><th>出现</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.name" :class="{ dim: !r.pick }">
            <td><input v-model="r.pick" type="checkbox" style="width:auto" /></td>
            <td><input v-model="r.name" style="width:100px;font-weight:600" /><div v-if="r.existing_id > 0" class="small"><RouterLink :to="`/characters/${r.existing_id}`" class="chip">已存在</RouterLink></div><div v-else-if="r.existing_id === -1" class="small"><span class="chip on">已写入</span></div></td>
            <td><input v-model="r.aliasText" style="width:110px" placeholder="—" /></td>
            <td><select v-model="r.gender" style="width:70px"><option v-for="(v, k) in LABELS.gender" :key="k" :value="k">{{ v }}</option></select></td>
            <td><textarea v-model="r.summary" style="min-height:44px;min-width:260px" /><input v-model="r.traitText" class="small" placeholder="特征，用顿号分隔" /></td>
            <td class="small"><div v-for="(rel, i) in r.relations" :key="i" :title="rel.evidence"><span :class="names.has(rel.target) ? 'chip' : 'muted'">{{ rel.target }}</span> {{ rel.kind }}</div><span v-if="!r.relations.length" class="muted">—</span></td>
            <td class="small mono">{{ r.mentions || 1 }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>
<style scoped>
.xtable { width: 100%; border-collapse: collapse; }
.xtable td, .xtable th { padding: 8px 6px; vertical-align: top; border-bottom: 1px solid #ffffff10; text-align: left; }
.xtable tr.dim { opacity: .55; }
.xtable td:nth-child(6) { min-width: 150px; }
.xtable th { white-space: nowrap; }
</style>
