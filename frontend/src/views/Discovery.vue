<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { api } from '../api'
import JobProgress from '../components/JobProgress.vue'
const LibraryImportPanel=defineAsyncComponent(()=>import('../components/LibraryImportPanel.vue'))
const kinds={mixed:'综合资料',game:'游戏/特典',novel:'小说/图书',drawing:'绘画素材',audio:'音声',model3d:'3D',live2d:'Live2D',ai_model:'AI模型',document:'文档'}
const states={idle:'尚未扫描',queued:'排队',running:'扫描中',pausing:'暂停中',cancelling:'取消中',paused:'已暂停',cancelled:'已取消',interrupted:'已中断',error:'扫描失败',done:'扫描完成',limited:'达到预算，结果不完整'}
const limits={entry_budget:'目录项数量上限',file_budget:'可识别文件数量上限',size_budget:'声明文件总大小上限',time_budget:'协作时间预算'}
const defaults=()=>({kind:'mixed',max_depth:4,ignores:[],max_files:1000,max_entries:20000,max_bytes:32*1024**3,hash_file_bytes:16*1024**2,hash_bytes:256*1024**2,max_seconds:60})
const form=reactive({name:'',path:'',config:defaults(),rules:''})
const roots=ref([]),source=ref(null),job=ref(null),error=ref(''),busy=ref(false),offset=ref(0),hasMore=ref(false),notice=ref('')
const base=ref(''),loaded=ref(false)
const snapshot=()=>JSON.stringify({name:form.name,path:form.path,config:form.config,rules:form.rules})
const dirty=computed(()=>loaded.value&&snapshot()!==base.value)
const active=computed(()=>['queued','running','pausing','cancelling'].includes(source.value?.state))
let timer,disposed=false,sequence=0
function guard(){return !dirty.value||window.confirm('扫描来源配置尚未保存，确认放弃这些修改？')}
function leave(e){if(dirty.value){e.preventDefault();e.returnValue=''}}
onBeforeRouteLeave(()=>guard())
onBeforeUnmount(()=>{disposed=true;sequence++;clearTimeout(timer);window.removeEventListener('beforeunload',leave)})
async function perform(fn){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){if(!disposed)error.value=e.message}finally{if(!disposed)busy.value=false}}
async function list(){const data=await api.get('/api/discovery-roots',{offset:offset.value,limit:20});if(!disposed){roots.value=data.items;hasMore.value=data.has_more}}
function reset(row=null){source.value=row;job.value=null;notice.value='';form.name=row?.name||'';form.path=row?.path||'';form.config=structuredClone(row?.config||defaults());form.rules=form.config.ignores.join('\n');base.value=snapshot();loaded.value=true}
async function select(row){if(!guard())return;sequence++;clearTimeout(timer);const n=sequence;const current=await api.get(`/api/discovery-roots/${row.id}`);if(disposed||n!==sequence)return;reset(current);if(active.value&&current.job_id)poll(current.job_id,n)}
function fresh(){if(!guard())return;sequence++;clearTimeout(timer);reset()}
async function save(){const config={...form.config,ignores:form.rules.split('\n').map(s=>s.trim()).filter(Boolean)};const body={name:form.name,config};const row=source.value?await api.patch(`/api/discovery-roots/${source.value.id}`,{...body,uid:source.value.uid,version:source.value.version}):await api.post('/api/discovery-roots',{...body,path:form.path});reset(row);await list()}
const identity=()=>({uid:source.value.uid,version:source.value.version})
async function poll(id,n){try{const data=await api.get(`/api/jobs/${id}`);if(disposed||n!==sequence)return;job.value=data;if(['queued','running'].includes(data.status))timer=setTimeout(()=>poll(id,n),1000);else{source.value=await api.get(`/api/discovery-roots/${source.value.id}`);await list();notice.value=source.value.state==='error'?'扫描未完成，诊断已保存；请检查下方错误提示。':'预览结果已保存；原目录未写入，尚未自动导入。'}}catch(e){if(!disposed&&n===sequence)error.value=e.message}}
async function scan(){notice.value='';if(dirty.value){error.value='请先保存配置再扫描';return}const data=await api.post(`/api/discovery-roots/${source.value.id}/scan`,identity());source.value=await api.get(`/api/discovery-roots/${source.value.id}`);job.value=data.job;const n=++sequence;clearTimeout(timer);poll(data.job.id,n);await list()}
async function control(action){source.value=await api.post(`/api/discovery-roots/${source.value.id}/control/${action}`,identity());await list()}
async function remove(){if(!window.confirm('只移除这个扫描来源配置？原文件、素材和预览历史均保留。'))return;await api.post(`/api/discovery-roots/${source.value.id}/remove`,identity());reset();await list()}
onMounted(()=>{reset();window.addEventListener('beforeunload',leave);perform(list)})
</script>
<template>
  <div class="grid">
    <header class="row"><div><h2>资料发现</h2><p class="small muted">手动启动只读扫描，确认后才归档。不会联网、执行程序或自动创建作品。</p></div><span class="spacer"/><button :disabled="busy" @click="perform(list)">刷新来源列表</button><button :disabled="busy" @click="fresh">添加扫描来源</button></header>
    <p v-if="error" class="notice" role="alert">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
    <div class="source-layout">
      <aside class="card grid"><h3>已保存的本地目录</h3><p v-if="!roots.length" class="small muted">先添加具体文件夹。系统不会自动扫描整盘。</p>
        <button v-for="r in roots" :key="r.uid" class="source-item" :aria-pressed="source?.uid===r.uid" :disabled="busy" @click="perform(()=>select(r))"><b>{{r.name}}</b><small>{{kinds[r.config.kind]}} · {{states[r.state]}}</small><small>{{r.stats?.files??'—'}} 项 · {{r.stats?.finished_at?new Date(r.stats.finished_at).toLocaleString():'尚无结果'}}</small></button>
        <nav class="row" aria-label="扫描来源分页"><button :disabled="busy||!offset" @click="offset-=20;perform(list)">上一页</button><button :disabled="busy||!hasMore" @click="offset+=20;perform(list)">下一页</button></nav>
      </aside>
      <section class="card grid"><h3>{{source?'管理扫描来源':'添加扫描来源'}}</h3>
        <form class="grid" @submit.prevent="perform(save)"><fieldset :disabled="busy||active" class="grid">
          <label class="field">来源名称<input v-model="form.name" required maxlength="120"/></label>
          <label class="field">实际本地文件夹<input v-model="form.path" :disabled="Boolean(source)" required placeholder="输入具体目录路径"/></label>
          <div class="form-columns"><label class="field">资料类型<select v-model="form.config.kind"><option v-for="(name,key) in kinds" :key="key" :value="key">{{name}}</option></select></label><label class="field">最大子目录深度<input v-model.number="form.config.max_depth" type="number" min="0" max="32" required/></label></div>
          <label class="field">忽略规则（每行一个，支持 *、?；匹配相对路径或文件名）<textarea v-model="form.rules" rows="3" placeholder="缓存/*&#10;*.tmp" maxlength="8000"/></label>
          <details><summary>扫描预算</summary><div class="form-columns">
            <label class="field">文件数量上限<input v-model.number="form.config.max_files" type="number" min="1" max="5000" required/></label><label class="field">所有目录项上限<input v-model.number="form.config.max_entries" type="number" min="1" max="50000" required/></label>
            <label class="field">声明文件总大小上限（bytes）<input v-model.number="form.config.max_bytes" type="number" min="1" max="1099511627776" required/></label><label class="field">协作时间预算（秒）<input v-model.number="form.config.max_seconds" type="number" min="1" max="600" required/></label>
            <label class="field">单文件Hash上限（bytes）<input v-model.number="form.config.hash_file_bytes" type="number" min="0" max="268435456" required/></label><label class="field">本轮Hash读取预算（bytes）<input v-model.number="form.config.hash_bytes" type="number" min="0" max="1073741824" required/></label>
          </div><p class="small muted">大文件可只登记元数据，未Hash的文件不进入通用导入；模型权重仅供专用模型库管理。时间预算在目录项和读取块间检查，不是对操作系统阻塞读的硬超时。</p></details>
          <button class="primary" :disabled="busy||active">{{source?'保存配置':'保存扫描来源'}}</button>
        </fieldset></form>
        <template v-if="source"><p class="small mono">{{source.path}}</p><div class="row"><span class="badge">{{states[source.state]}}</span><button :disabled="busy||active||dirty" @click="perform(scan)">{{['paused','cancelled','interrupted'].includes(source.state)?'继续扫描（复用指纹）':'重新扫描'}}</button><button v-if="['running','queued'].includes(source.state)" :disabled="busy" @click="perform(()=>control('pause'))">暂停扫描</button><button v-if="['running','queued'].includes(source.state)" :disabled="busy" @click="perform(()=>control('cancel'))">取消扫描</button><button :disabled="busy||active" @click="perform(remove)">移除来源配置</button></div>
          <p class="small muted">恢复会重新枚举并复用已完成文件的指纹；不会自动重新导入或覆盖资料。符号链接、Junction和Front数据目录会跳过。</p>
          <div v-if="source.stats?.finished_at" class="row stats"><span>文件 {{source.stats.files}}</span><span>新增候选 {{source.stats.new}}</span><span>变化候选 {{source.stats.changed}}</span><span>缺失 {{source.stats.missing??'未知/不可比较'}}</span><span>重复 {{source.stats.duplicates}}</span><span>复用Hash {{source.stats.reused_hashes}}</span><span>只登记信息 {{source.stats.deferred_hashes}}</span></div>
          <p v-if="source.stats?.error_code==='source_unavailable'" class="notice" role="alert">扫描来源已移动、失效或不可读。请检查实际目录与权限；Front未改写或修复原件。</p>
        </template><JobProgress :job="job"/>
      </section>
    </div>
    <RouterLink v-if="source?.baseline_report_id&&!source.report_available" :to="{path:'/project-preview',query:{report_id:source.baseline_report_id}}">查看上次完整预览（不是当前扫描结果）</RouterLink>
    <template v-if="source?.report_available&&!active&&['done','limited','paused','cancelled'].includes(source.state)"><p class="notice" v-if="source.state==='limited'">扫描触及{{limits[source.stats?.limit]||'预算'}}，以下只是部分结果，不能据此认定其他文件已经缺失。可调整配置后重新扫描。</p><RouterLink :to="{path:'/project-preview',query:{report_id:source.report_id}}">打开单项文本/图片预览与世界观归档</RouterLink><LibraryImportPanel :key="source.report_id" :report-id="source.report_id"/></template>
  </div>
</template>
<style scoped>
.source-layout{display:grid;grid-template-columns:minmax(220px,.65fr) minmax(0,1.6fr);gap:16px;align-items:start}.source-layout>*{min-width:0}.source-item{text-align:left;white-space:normal;display:grid;gap:5px;overflow-wrap:anywhere}.source-item[aria-pressed=true]{border-color:var(--accent)}small{color:var(--muted)}h2,h3{margin:0}.form-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}fieldset{padding:0;border:0;min-width:0}.field,input,textarea,select{min-width:0;width:100%;box-sizing:border-box}.mono{overflow-wrap:anywhere}.row{flex-wrap:wrap}.row button{white-space:normal}.stats{gap:12px;font-size:13px}@media(max-width:760px){.source-layout,.form-columns{grid-template-columns:minmax(0,1fr)}}
</style>
