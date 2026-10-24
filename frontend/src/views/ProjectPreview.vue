<script setup>
import { defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
const ProjectImportPanel=defineAsyncComponent(()=>import('../components/ProjectImportPanel.vue'))
import { useRoute } from 'vue-router'
import { api, Worlds } from '../api'
import JobProgress from '../components/JobProgress.vue'

const route=useRoute()
const form = reactive({path:'',recursive:true,world_id:route.query.world_id || ''})
const report = ref(null), job = ref(null), detail = ref(null), error = ref(''), busy = ref(false), worlds = ref([])
const offset = ref(0), reportId = ref(''), imageVisible = ref(false), imageError = ref(false)
let disposed = false, timer, sequence = 0
onBeforeUnmount(() => { disposed = true; sequence++; clearTimeout(timer) })
const CATEGORIES = {character:'人物候选',organization:'组织候选',location:'地点候选',novel:'小说/剧情候选',world:'世界设定候选',image:'图片',resource:'其他资源'}
const localDate = value => value ? new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}) : ''
async function load(id, start = 0) {
  try { const data = await api.get(`/api/project-previews/${id}`,{offset:start,limit:50}); if (!disposed) {report.value = data; reportId.value = id; offset.value = start} }
  catch (e) { if (!disposed) error.value = e.message }
}
async function poll(id) {
  if (disposed) return
  try {
    const data = await api.get(`/api/jobs/${id}`)
    if (disposed) return
    job.value = data; busy.value = ['queued','running'].includes(data.status)
    if (busy.value) timer = setTimeout(() => poll(id),600)
    else if (data.result?.report_id) await load(data.result.report_id)
  } catch (e) { if (!disposed) {error.value = e.message; busy.value = false} }
}
async function scan() {
  sequence++; busy.value = true; error.value = ''; detail.value = null; report.value = null
  try { const data = await api.post('/api/project-previews',{...form,world_id:form.world_id ? Number(form.world_id) : null}); await poll(data.id) }
  catch (e) { error.value = e.message; busy.value = false }
}
async function select(file) {
  const current = ++sequence
  detail.value = null; imageVisible.value = false; imageError.value = false
  try { const data = await api.get(`/api/project-previews/${reportId.value}/files/${file.index}`); if (!disposed && current === sequence) {detail.value = data; error.value = ''} }
  catch (e) { if (!disposed && current === sequence) error.value = e.message }
}
onMounted(async () => {
  worlds.value = (await Worlds.list({limit:500})).items
  if(route.query.import_id){try{const run=await api.get(`/api/project-imports/${route.query.import_id}`);await load(run.report_id);return}catch(e){error.value=e.message}}
  const history = await api.get('/api/jobs?kind=project-preview')
  if (!disposed && history.length) await poll(history[0].id)
})
</script>
<template>
  <div class="grid">
    <div class="card grid"><h2 style="margin:0">项目文件只读预览</h2><p class="small muted" style="margin:0">扫描阶段只读，不执行脚本或调用 AI。正式归档必须在下方明确选择并确认。</p>
      <form class="grid" @submit.prevent="scan"><label class="field">本机项目目录<input v-model="form.path" required placeholder="输入任意原创项目文件夹路径" /></label>
        <div class="row"><label class="row small"><input v-model="form.recursive" type="checkbox" style="width:auto" />包含子目录</label><span class="spacer" /><label class="field">重复项的世界观参考范围<select v-model="form.world_id"><option value="">未选择 / 新项目预览</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }} · #{{ w.id }}</option></select></label><button class="primary" :disabled="busy || !form.path">扫描预览</button></div>
      </form>
    </div>
    <JobProgress :job="job" />
    <p v-if="error" role="alert" class="notice">{{ error }}</p>
    <template v-if="report">
      <div class="row"><span class="badge">可识别 {{ report.total }} 项</span><span class="badge">重复候选 {{ report.duplicate_files }}</span><span class="badge">跳过未知格式 {{ report.unsupported }}</span><span class="badge">异常 {{ report.errors }}</span><span class="badge">复用哈希 {{ report.reused_hashes }}</span><span class="spacer" /><span class="small muted">原目录保持不变 · 导入结果见批次记录</span></div>
      <p class="small muted">分类依据路径和格式，仅供人工审核；同内容不代表同一人物或同一世界观，跨世界观资源不会自动合并。</p>
      <ProjectImportPanel :key="reportId" :report-id="reportId" :initial-world-id="form.world_id" :import-id="route.query.import_id"/>
      <div class="preview-layout">
        <section class="card grid"><div class="file-list"><table><thead><tr><th>文件</th><th>候选分类</th><th>状态</th></tr></thead><tbody><tr v-for="file in report.items" :key="file.index"><td><button @click="select(file)">{{ file.relative }}</button><small class="muted">{{ file.bytes?.toLocaleString() || '—' }} bytes<span v-if="file.width"> · {{ file.width }}×{{ file.height }}</span></small></td><td>{{ CATEGORIES[file.candidate] || file.kind }}</td><td>{{ file.error || (file.duplicate_of != null ? `与第 ${file.duplicate_of + 1} 项重复` : file.existing.length ? '库内相同内容' : '未发现重复') }}</td></tr></tbody></table></div>
          <nav class="row" aria-label="项目文件分页"><button :disabled="!offset" @click="load(reportId,offset-50)">上一页</button><span class="small">{{ Math.floor(offset/50)+1 }} / {{ Math.max(1,Math.ceil(report.total/50)) }}</span><button :disabled="offset+50 >= report.total" @click="load(reportId,offset+50)">下一页</button></nav>
        </section>
        <section class="card grid">
          <template v-if="detail"><h2 style="margin:0;overflow-wrap:anywhere">{{ detail.name }}</h2><p class="small muted">{{ detail.reason }}</p><p class="mono">SHA256 {{ detail.sha256 || '未计算' }}</p><p class="small muted">{{ localDate(detail.mtime) }} · {{ detail.kind }}</p>
            <p v-for="match in detail.existing" :key="match.asset_id" class="small">已有素材 #{{ match.asset_id }} · {{ match.same_world ? '同一参考世界观' : '其他世界观或未归属（不自动关联）' }}</p>
            <p v-if="detail.error" role="alert">{{ detail.error }}</p><pre v-if="detail.text">{{ detail.text }}</pre><p class="small muted">{{ detail.note }}</p>
            <button v-if="detail.kind === 'drawing' && !imageVisible" @click="imageVisible = true">显示这张原图（仅当前预览）</button>
            <img v-if="imageVisible" :src="`/api/project-previews/${reportId}/files/${detail.index}/image`" :alt="detail.name" @error="imageError = true" />
            <p v-if="imageError" role="alert">图片不可预览、超限或原文件已变化；请重新扫描并检查元数据。</p>
          </template><p v-else class="small muted">选择一个文件，按需查看文本片段或图片。图库不会自动加载全部原图。</p>
        </section>
      </div>
    </template>
  </div>
</template>
<style scoped>
.preview-layout { display:grid; grid-template-columns:minmax(0,1.2fr) minmax(0,1fr); gap:14px; align-items:start; }
.preview-layout > * { min-width:0; }
.file-list { max-height:600px; overflow:auto; }
td { overflow-wrap:anywhere; }
td button { white-space:normal; text-align:left; }
td small { display:block; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; max-height:520px; overflow:auto; font-size:12px; }
img { max-width:100%; max-height:550px; object-fit:contain; }
@media (max-width:1000px) { .preview-layout { grid-template-columns:minmax(0,1fr); } }
</style>
