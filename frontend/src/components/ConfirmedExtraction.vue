<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, Assets, Works, Worlds, LABELS } from '../api'
import JobProgress from './JobProgress.vue'
const route = useRoute()
const novels = ref([]), worlds = ref([]), works = ref([]), status = ref(null), plan = ref(null)
const assetId = ref(Number(route.query.asset) || ''), worldId = ref(''), workId = ref('')
const selected = ref([]), chunkSize = ref(3000), maxChunks = ref(20), confirmSend = ref(false)
const error = ref(''), busy = ref(false), batch = ref(null), batches = ref([]), job = ref(null), rows = ref([])
const result = ref(null), updateExisting = ref(false), preview = ref(''), previous = ref(''), difference = ref(null), page = ref(0), chapterPage = ref(0)
let disposed = false, timer, loadSequence = 0
const kinds = { narrator: '叙述者陈述（待核实）', dialogue: '角色说法', inference: '模型推测', unknown: '来源类别未确认' }
const active = computed(() => ['queued', 'running'].includes(job.value?.status) || ['queued', 'running'].includes(batch.value?.status))
const chars = computed(() => (plan.value?.chapters || []).filter(c => selected.value.includes(c.index)).reduce((n, c) => n + c.end - c.start, 0))
const picked = computed(() => rows.value.filter(c => c.pick))
const visible = computed(() => rows.value.slice(page.value * 50, page.value * 50 + 50))
const chapterRows = computed(() => (plan.value?.chapters || []).slice(chapterPage.value * 50, chapterPage.value * 50 + 50))
const graphNodes = computed(() => rows.value.slice(0, 24).map((c, i) => ({ name: c.name, x: 100 + (i % 4) * 190, y: 40 + Math.floor(i / 4) * 90 })))
const graphEdges = computed(() => rows.value.flatMap(c => c.relations.map(r => ({ a: graphNodes.value.find(n => n.name === c.name), b: graphNodes.value.find(n => n.name === r.target), kind: r.kind }))).filter(e => e.a && e.b))
onBeforeUnmount(() => { disposed = true; loadSequence++; clearTimeout(timer) })
async function run(fn) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await fn() } catch (e) { if (!disposed) error.value = e.message }
  finally { if (!disposed) busy.value = false }
}
async function history() {
  if (!worldId.value) { batches.value = []; return }
  const world = worldId.value, asset = assetId.value
  const data = await api.get('/api/ai/extract/reviews', { world_id: world, asset_id: asset, limit: 100 })
  if (!disposed && world === worldId.value && asset === assetId.value) batches.value = data.items
}
async function loadPlan() {
  const n = ++loadSequence; plan.value = null; selected.value = []; confirmSend.value = false; preview.value = ''; chapterPage.value = 0
  if (!assetId.value) return
  const data = await api.get(`/api/assets/${assetId.value}/chapter-plan`)
  if (disposed || n !== loadSequence) return
  plan.value = data
  const novel = novels.value.find(a => a.id === Number(assetId.value))
  const returning=route.query.batch && Number(route.query.asset)===Number(assetId.value)
  worldId.value = novel?.world_id || (returning ? Number(route.query.world_id)||'' : '')
  workId.value = novel?.work_id || (returning ? Number(route.query.work_id)||'' : '')
  await history()
}
watch(assetId, () => { clearTimeout(timer); batch.value = null; job.value = null; rows.value = []; run(loadPlan) })
watch(worldId, () => { confirmSend.value = false; if (batch.value && Number(worldId.value) !== batch.value.world_id) { clearTimeout(timer); batch.value = null; job.value = null; rows.value = [] }; history().catch(e => { error.value = e.message }) })
watch(workId, () => { confirmSend.value = false })
onMounted(() => run(async () => {
  const [ns, ws, ks, st] = await Promise.all([Assets.list({ kind: 'novel', limit: 500 }), Worlds.list({ limit: 500 }), Works.list({ limit: 500 }), api.get('/api/ai/status')])
  if (disposed) return
  novels.value = ns.items; worlds.value = ws.items; works.value = ks.items; status.value = st
  if (!assetId.value) assetId.value = novels.value[0]?.id || ''
  await loadPlan()
  if (route.query.batch) await openBatch(String(route.query.batch))
}))
async function excerpt(c) { const data = await api.get(`/api/assets/${assetId.value}/chapter-plan/excerpt`, { start: c.start }); if (!disposed) preview.value = data.text.slice(0, Math.min(2000, c.end - c.start)) }
async function openBatch(id) {
  const data = await api.get(`/api/ai/extract/reviews/${id}`)
  if (disposed) return
  if (data.asset_id !== Number(assetId.value) || data.world_id !== Number(worldId.value)) throw new Error('请先选择该批次对应的小说与世界观，再打开审核。')
  batch.value = data; page.value = 0; difference.value = null; result.value = null; confirmSend.value = false
  rows.value = data.characters.map(c => ({ ...c, pick: false, existing_id: '', aliasText: c.aliases.join('、'), traitText: c.traits.join('、'), relations: c.relations.map(r => ({ ...r, pick: false })) }))
  if (data.job_id) { job.value = await api.get(`/api/jobs/${data.job_id}`); if (!disposed && ['queued', 'running'].includes(job.value.status)) poll(data.job_id) }
}
async function poll(id) {
  clearTimeout(timer)
  if (disposed) return
  try {
    const data = await api.get(`/api/jobs/${id}`)
    if (disposed) return
    job.value = data
    if (['queued', 'running'].includes(data.status)) timer = setTimeout(() => poll(id), 800)
    else { if (batch.value) await openBatch(batch.value.id); await history() }
  } catch (e) { if (!disposed) error.value = e.message }
}
async function start() {
  const data = await api.post('/api/ai/extract/characters', { asset_id: Number(assetId.value), world_id: Number(worldId.value), work_id: Number(workId.value), chapter_revision: plan.value.base_revision, chapter_indices: selected.value, chunk_size: Number(chunkSize.value), max_chunks: Number(maxChunks.value), confirm_send: confirmSend.value })
  await openBatch(data.batch_id); await history()
}
async function resume() {
  const data = await api.post(`/api/ai/extract/reviews/${batch.value.id}/resume`, { confirm_send: confirmSend.value })
  await openBatch(data.batch_id)
}
async function apply() {
  const split = text => text.split(/[、,，]/).map(x => x.trim()).filter(Boolean)
  result.value = await api.post(`/api/ai/extract/reviews/${batch.value.id}/apply`, {
    update_existing: updateExisting.value,
    characters: picked.value.map(c => ({ candidate_name: c.name, name: c.reviewedName || c.name, aliases: split(c.aliasText), gender: c.gender, summary: c.summary, traits: split(c.traitText), appearance: c.appearance, existing_id: c.existing_id ? Number(c.existing_id) : null })),
    relation_keys: picked.value.flatMap(c => c.relations.filter(r => r.pick).map(r => r.key)),
  })
  const saved = result.value; await openBatch(batch.value.id); result.value = saved
}
async function compare() { difference.value = await api.get(`/api/ai/extract/reviews/${batch.value.id}/compare/${previous.value}`) }
</script>
<template>
  <div class="grid">
    <p v-if="error" class="notice" role="alert">{{ error }}</p>
    <p v-if="!status?.available" class="notice">尚未配置AI。可先确认章节与人工管理百科；DeepSeek兼容接口在 <RouterLink to="/settings">本机设置</RouterLink> 添加，密钥不要发到聊天或仓库。此状态未调用真实模型。</p>
    <div class="extract-grid">
      <section class="card grid">
        <h2>确认章节与发送范围</h2>
        <label class="field">小说<select v-model="assetId" :disabled="busy || active"><option value="">选择小说</option><option v-for="a in novels" :key="a.id" :value="a.id">{{ a.title }}</option></select></label>
        <label class="field">目标世界观<select v-model="worldId" :disabled="busy || active"><option value="">必须选择</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }} · #{{ w.id }}</option></select></label>
        <label class="field">来源作品<select v-model="workId" :disabled="busy || active"><option value="">必须选择</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }} · #{{ w.id }}</option></select></label>
        <div class="row"><RouterLink v-if="assetId" class="btn" :to="`/chapters/${assetId}`">整理并确认目录</RouterLink><button :disabled="busy" @click="run(loadPlan)">重新加载目录</button></div>
        <p v-if="plan && (!plan.base_revision || plan.stale)" role="alert" class="notice">请先在章节编辑器确认当前正文目录；自动识别结果不能直接作为确认。</p>
        <div v-if="plan" class="chapter-list"><label v-for="c in chapterRows" :key="c.index" class="row"><input v-model="selected" :value="c.index" type="checkbox" :disabled="busy || active" @change="confirmSend = false" /><span>{{ c.title }} · {{ c.words }}字</span><button :disabled="busy" @click="run(() => excerpt(c))">预览</button></label></div>
        <div v-if="plan" class="row"><button :disabled="!chapterPage" @click="chapterPage--">前50章</button><button :disabled="(chapterPage + 1) * 50 >= plan.chapters.length" @click="chapterPage++">后50章</button><button :disabled="busy || active" @click="selected = chapterRows.map(c => c.index); confirmSend = false">选择本页</button></div>
        <pre v-if="preview">{{ preview }}</pre>
        <div class="grid cols-2"><label class="field">片段字数<input v-model.number="chunkSize" type="number" min="500" max="20000" /></label><label class="field">批次片段上限<input v-model.number="maxChunks" type="number" min="1" max="200" /></label></div>
        <p class="small">当前服务：{{ status?.label || status?.provider || '未配置' }} / {{ status?.model || '未选择模型' }}<br/>发送 {{ selected.length }} 章，共 {{ chars }} 个字符。超限会拒绝，不静默截断。</p>
        <label class="row"><input v-model="confirmSend" type="checkbox" />我确认将所选正文（重试时为该批次剩余片段）发送给当前服务。</label>
        <button class="primary" :disabled="busy || active || !status?.available || !plan?.base_revision || plan.stale || !selected.length || !worldId || !workId || !confirmSend" @click="run(start)">按已确认章节抽取</button>
        <JobProgress :job="job" />
      </section>
      <section class="card grid">
        <div class="row"><h2>持久批次与证据审核</h2><button :disabled="busy" @click="run(history)">刷新批次</button></div>
        <label class="field">最近100个批次（当前世界观与小说）<select :value="batch?.id || ''" @change="run(() => openBatch($event.target.value))"><option value="" disabled>选择批次</option><option v-for="b in batches" :key="b.id" :value="b.id">{{ b.created_at }} · {{ b.status }} · {{ b.model }} · {{ b.id.slice(0, 8) }}</option></select></label>
        <p v-if="!batch" class="empty">先确认章节，或选择已保存批次。候选不会自动写入百科。</p>
        <template v-if="batch">
          <p class="small mono">{{ batch.id }} · {{ batch.status }} · 世界观 #{{ batch.world_id }} / 作品 #{{ batch.work_id }} / 目录 #{{ batch.revision }}</p>
          <div class="row"><button :disabled="busy || active" @click="run(() => openBatch(batch.id))">刷新审核结果</button><button v-if="['partial', 'interrupted', 'cancelled'].includes(batch.status)" :disabled="busy || active || !confirmSend || !status?.available" @click="run(resume)">明确重试未完成片段</button></div>
          <details><summary>片段状态与失败诊断</summary><p v-for="u in batch.units" :key="u.id">{{ u.chapter_title }} · 字符 {{ u.start }} · {{ u.status }} {{ u.error }}</p></details>
          <p class="notice small">所有内容均为待确认候选。置信度为模型自述，未经校准；引文核对仅证明文本存在，不证明推断正确。别名不会自动合并；同名唯一时重复审核关联已有ID。</p>
          <details v-if="rows.length"><summary>待确认关系预览（前24个节点）</summary><div class="graph-scroll"><svg role="img" aria-label="候选关系示意图" viewBox="0 0 800 580"><line v-for="(e,i) in graphEdges" :key="i" :x1="e.a.x" :y1="e.a.y" :x2="e.b.x" :y2="e.b.y" stroke="currentColor" opacity=".3"/><g v-for="n in graphNodes" :key="n.name"><circle :cx="n.x" :cy="n.y" r="22" fill="var(--accent)" opacity=".35"/><text :x="n.x" :y="n.y+4" text-anchor="middle" fill="currentColor">{{ n.name }}</text></g></svg></div></details>
          <div class="row"><button :disabled="busy || active" @click="visible.forEach(c => { if (!c.approved) c.pick = true })">勾选本页待审核人物</button><label class="row"><input v-model="updateExisting" type="checkbox" />明确补充已有角色（不覆盖已有正文）</label><button class="primary" :disabled="busy || active || !picked.length" @click="run(apply)">审核通过并写入 {{ picked.length }} 人</button></div>
          <p v-if="result" role="status" class="notice">新建 {{ result.created.length }} 人，补充 {{ result.updated.length }} 人，新增 {{ result.relations }} 条待确认关系。<RouterLink :to="`/graph?world_id=${batch.world_id}`">打开关系网复核</RouterLink></p>
          <article v-for="c in visible" :key="c.name" class="card grid">
            <label class="row"><input v-model="c.pick" :disabled="active" type="checkbox" /><b>{{ c.name }}</b><span v-if="c.approved" class="badge">已审核 #{{ c.character_id || '记录已删除' }}</span></label>
            <div class="grid cols-2"><label class="field">审核后名称<input v-model="c.reviewedName" :placeholder="c.name" /></label><label class="field">明确合并建议<select v-model="c.existing_id"><option value="">不按别名自动合并</option><option v-for="k in c.suggestions" :key="k.id" :value="k.id">#{{ k.id }} {{ k.name }} · {{ k.reason }}</option></select></label><label class="field">审核后别名<input v-model="c.aliasText" /></label><label class="field">性别（有证据才设定）<select v-model="c.gender"><option v-for="(l,k) in LABELS.gender" :key="k" :value="k">{{ l }}</option></select></label></div>
            <label class="field">简介候选（可编辑）<textarea v-model="c.summary" /></label><label class="field">特征与组织归属建议<input v-model="c.traitText" /></label>
            <p v-if="c.variant_notice" class="notice">跨章节描述存在多个候选，请核对下方各次观察；系统没有自动裁定冲突或覆盖设定。</p>
            <details><summary>原文证据与各章节观察（{{ c.evidence.length }}）</summary><blockquote v-for="(e,i) in c.evidence" :key="i"><p>{{ e.quote }}</p><small>{{ e.chapter_title }} · Unicode字符 {{ e.start }}–{{ e.end }} · {{ kinds[e.category] }} · {{ e.confidence_source }} {{ e.confidence ?? '无数值' }} {{ e.ambiguous_location ? '引句重复，位置需核对' : '' }}</small></blockquote><div v-for="(o,j) in c.observations" :key="j" class="small"><p>{{o.evidence[0]?.chapter_title}}：{{o.summary || '暂无简介'}} · {{LABELS.gender[o.gender]}} · {{o.traits.join('、')}}</p></div></details>
            <div v-for="r in c.relations" :key="r.key" class="card"><label class="row"><input v-model="r.pick" :disabled="active" type="checkbox" />{{ c.name }} → {{ r.target }} · {{ r.kind }}</label><p>{{ r.evidence.quote }}</p><small>{{ r.evidence.chapter_title }} · {{ kinds[r.evidence.category] }}；关系两端需同时勾选审核。</small></div>
          </article>
          <div class="row"><button :disabled="!page" @click="page--">上一页</button><span>{{ rows.length }} 个候选 · {{ page+1 }}页</span><button :disabled="(page+1)*50 >= rows.length" @click="page++">下一页</button></div>
          <div class="row"><label class="field">与旧批次比较<select v-model="previous"><option value="">选择旧批次</option><option v-for="b in batches.filter(b => b.id !== batch.id)" :key="b.id" :value="b.id">{{ b.created_at }} · {{ b.id.slice(0,8) }}</option></select></label><button :disabled="busy || !previous" @click="run(compare)">比较人物及关系候选变化</button></div>
          <div v-if="difference" class="notice"><p>{{ difference.notice }}；{{ difference.same_scope ? '章节范围相同' : '章节范围不同' }}</p><p>新增人物候选：{{difference.added.join('、') || '无'}}</p><p>本次未出现：{{difference.absent.join('、') || '无'}}</p><p v-for="(e,i) in difference.relations_added" :key="'add'+i">新增关系候选：{{e.join(' → ')}}</p><p v-for="(e,i) in difference.relations_absent" :key="'absent'+i">本次未出现关系：{{e.join(' → ')}}</p></div>
        </template>
      </section>
    </div>
  </div>
</template>
<style scoped>
.extract-grid{display:grid;grid-template-columns:minmax(260px,340px) minmax(0,1fr);gap:14px;align-items:start}.extract-grid>*{min-width:0}h2{margin:0}.chapter-list{max-height:360px;overflow:auto}.chapter-list>.row{padding:5px 0}.chapter-list span{flex:1;min-width:0}.row input[type=checkbox]{width:auto}.graph-scroll{overflow:auto}.graph-scroll svg{width:100%;min-width:440px;max-height:360px}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:280px;overflow:auto;font-size:12px}blockquote{margin:8px 0;padding:8px;border-left:2px solid var(--accent);background:var(--sunken)}@media(max-width:1050px){.extract-grid{grid-template-columns:minmax(0,1fr)}}
</style>
