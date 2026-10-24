<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../api'
const props = defineProps({ kind: String, entityId: Number })
const emit = defineEmits(['restored'])
const page = ref({ items: [], total: 0, enabled: false }), offset = ref(0)
const note = ref(''), left = ref(''), right = ref(''), changes = ref(null), inspected = ref(null)
const error = ref(''), busy = ref(false), mode = ref('side'), amount = ref(50), natural = ref(false)
const incoming = ref(null), mediaError = ref('')
const pending = ref(null)
let sequence = 0, disposed = false
const base = computed(() => `/api/versions/${props.kind}/${props.entityId}`)
const media = id => `${base.value}/${id}/media`
const images = computed(() => changes.value && props.kind === 'asset' && changes.value.images)
onBeforeUnmount(() => { disposed = true; sequence++ })
async function run(fn) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await fn() } catch (e) { if (!disposed) error.value = e.message }
  finally { if (!disposed) busy.value = false }
}
async function load() {
  const n = ++sequence
  const data = await api.get(base.value, { offset: offset.value, limit: 50 })
  if (!disposed && n === sequence) page.value = data
}
watch(() => [props.kind, props.entityId], () => {
  offset.value = 0; changes.value = null; inspected.value = null; left.value = ''; right.value = ''
  run(load)
}, { immediate: true })
async function save() { await api.post(base.value, { note: note.value || '手动保存' }); await load() }
async function inspect(id) { inspected.value = await api.get(`${base.value}/${id}`) }
async function compare() {
  const [diff, a, b] = await Promise.all([
    api.get(`${base.value}/compare`, { left: left.value, right: right.value }),
    api.get(`${base.value}/${left.value}`), api.get(`${base.value}/${right.value}`),
  ])
  changes.value = { ...diff, images: a.media_saved && b.media_saved && a.payload.mime?.startsWith('image/') && b.payload.mime?.startsWith('image/') }
  mediaError.value = ''
}
async function restore(id) {
  await api.post(`${base.value}/${id}/restore`, { expected_latest: page.value.items[0].id, note: note.value || '恢复历史版本' })
  await load(); inspected.value = null; changes.value = null; emit('restored')
}
async function pin() {
  await api.post(`${base.value}/pin`, { expected_latest: page.value.items[0].id, note: note.value || '明确固定媒体版本' }); await load(); emit('restored')
}
async function upload(event) {
  const file = event.target.files?.[0]
  if (!file) return
  await run(async () => {
    const form = new FormData(); form.append('file', file)
    let row
    try { row = await api.upload('/api/assets/upload', form) }
    catch (e) { if (e.status === 409 && e.data?.detail?.asset_id) row = { id: e.data.detail.asset_id }; else throw e }
    // Upload alone creates a library item. Explicit adoption preserves the old version.
    incoming.value = row.id
  })
  event.target.value = ''
}
async function adopt() {
  await api.post(`${base.value}/adopt`, { asset_id: Number(incoming.value), expected_latest: page.value.items[0].id, note: note.value || '采用新版文件' })
  incoming.value = null; changes.value = null; await load(); emit('restored')
}
async function confirmPending() {
  const action = pending.value; pending.value = null
  if (action.type === 'restore') await restore(action.id)
  else await pin()
}
</script>
<template>
  <section class="version-panel grid">
    <p v-if="error" class="notice" role="alert">{{ error }}</p>
    <p class="small muted">明确启用后记录后续编辑；保存的是已提交资料。恢复会追加版本，不改写原始文件。原地索引不会自动保存旧图原件。</p>
    <div class="row"><label class="field grow">版本说明<input v-model="note" maxlength="500" /></label><button :disabled="busy" @click="run(save)">{{ page.enabled ? '保存当前版本' : '启用版本记录' }}</button><button :disabled="busy" @click="run(load)">刷新历史</button></div>
    <div v-if="pending" class="notice grid" role="alert"><p>{{ pending.type === 'restore' ? '恢复会替换已保存资料并追加新版本，未保存的编辑不会采用；不改写源文件。' : '固定版本会将原文件复制到Front托管目录，占用额外磁盘空间；原件保持不变。' }}</p><div class="row"><button :disabled="busy" @click="run(confirmPending)">确认执行{{ pending.type === 'restore' ? '恢复' : '固定' }}</button><button @click="pending = null">取消</button></div></div>
    <template v-if="page.enabled">
      <div v-if="kind === 'asset'" class="card grid">
        <div class="row"><button :disabled="busy" @click="pending = {type:'pin'}">固定当前原文件（托管副本）</button><label class="field">上传候选新版文件<input type="file" :disabled="busy" @change="upload" /></label></div>
        <div class="row"><label class="field">或选择素材ID<input v-model="incoming" type="number" min="1" /></label><button :disabled="busy || !incoming" @click="run(adopt)">确认采用为新文件版本</button></div>
        <small class="muted">上传先存入通用素材库，再确认采用；同内容只存一份。未确认的候选仍保留在素材库。</small>
      </div>
      <div class="history-list"><div v-for="r in page.items" :key="r.id" class="row"><b>#{{ r.id }}</b><span>{{ r.created_at }} · {{ r.note }} · {{ r.source }}</span><button :disabled="busy" @click="run(() => inspect(r.id))">查看</button><button :disabled="busy" @click="pending = {type:'restore',id:r.id}">恢复为新版本</button></div></div>
      <div class="row"><button :disabled="busy || !offset" @click="offset -= 50; run(load)">上一页</button><span>{{ page.total }} 个版本</span><button :disabled="busy || offset + 50 >= page.total" @click="offset += 50; run(load)">下一页</button></div>
      <div class="row"><label class="field">旧版本<select v-model="left"><option value="">选择</option><option v-for="r in page.items" :key="r.id" :value="r.id">#{{ r.id }} {{ r.note }}</option></select></label><label class="field">新版本<select v-model="right"><option value="">选择</option><option v-for="r in page.items" :key="r.id" :value="r.id">#{{ r.id }} {{ r.note }}</option></select></label><button :disabled="busy || !left || !right" @click="run(compare)">比较版本</button></div>
    </template>
    <div v-if="inspected" class="card"><b>版本 #{{ inspected.id }}</b><p v-if="inspected.indexed_notice" class="notice">{{ inspected.indexed_notice }}</p><pre>{{ JSON.stringify(inspected.payload, null, 2) }}</pre></div>
    <section v-if="changes" class="grid">
      <b>{{ changes.changed_fields }} 个字段发生变化</b>
      <template v-if="images">
        <div class="row"><select v-model="mode" aria-label="图片对比方式"><option value="side">并排</option><option value="slider">滑杆</option><option value="overlay">透明叠加</option></select><label class="row"><input v-model="natural" type="checkbox" />原始分辨率</label><a :href="media(left)" target="_blank" rel="noopener">打开旧原图</a><a :href="media(right)" target="_blank" rel="noopener">打开新原图</a></div>
        <label v-if="mode !== 'side'" class="field">{{ mode === 'overlay' ? '新版不透明度' : '分割位置' }} {{ amount }}%<input v-model.number="amount" type="range" min="0" max="100" /></label>
        <p v-if="mediaError" class="notice" role="alert">{{ mediaError }}</p>
        <div class="image-scroll"><div class="comparison" :class="{ side: mode === 'side', natural }"><img :src="media(left)" alt="旧版本" @error="mediaError = '历史图片不可用，请检查托管文件。'" /><img :src="media(right)" alt="新版本" :class="{ layered: mode !== 'side' }" :style="mode === 'overlay' ? { opacity: amount / 100 } : mode === 'slider' ? { clipPath: `inset(0 ${100 - amount}% 0 0)` } : {}" @error="mediaError = '历史图片不可用，请检查托管文件。'" /></div></div>
        <small class="muted">按画布左上角对齐；不同尺寸不自动配准。原始分辨率视图可滚动。</small>
      </template>
      <div v-for="field in changes.fields" :key="field.field" class="card"><b>{{ field.field }}</b><small v-if="field.truncated" class="notice">超长字段仅显示片段，请查看完整版本。</small><template v-if="field.paragraphs"><div v-for="(p, i) in field.paragraphs" :key="i" class="diff-pair"><pre class="removed">− {{ p.before }}</pre><pre class="added">+ {{ p.after }}</pre></div></template><div v-else class="diff-pair"><pre class="removed">− {{ field.before }}</pre><pre class="added">+ {{ field.after }}</pre></div></div>
    </section>
  </section>
</template>
<style scoped>
.version-panel{min-width:0}.grow{flex:1}.history-list{max-height:280px;overflow:auto}.history-list>.row{padding:6px 0;border-bottom:1px solid var(--line)}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:360px;overflow:auto;font-size:12px}.diff-pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px}.removed{background:#a4484820}.added{background:#36886220}.image-scroll{overflow:auto;max-height:650px;background:repeating-conic-gradient(#7772 0% 25%,transparent 0% 50%) 0 0/20px 20px}.comparison{position:relative;min-height:100px}.comparison img{display:block;max-width:100%;height:auto}.comparison.side{display:grid;grid-template-columns:1fr 1fr;gap:8px}.comparison .layered{position:absolute;top:0;left:0;max-height:100%;object-fit:contain;object-position:top left}.comparison.natural{width:max-content}.comparison.natural img{max-width:none;max-height:none}@media(max-width:700px){.diff-pair,.comparison.side{grid-template-columns:minmax(0,1fr)}}
</style>
