<script setup>
import {defineAsyncComponent,onBeforeUnmount,ref,watch} from 'vue'
import {api} from '../api'
const VoiceNovelReview=defineAsyncComponent(()=>import('./VoiceNovelReview.vue'))
const props=defineProps({project:Object}),emit=defineEmits(['created','changed','reviewed'])
const assetId=ref(''),title=ref(''),preview=ref(null),book=ref(null),offset=ref(0),error=ref(''),busy=ref(false)
const first=ref(1),last=ref(1),rangePreview=ref(null),rangeRows=ref([]),followRange=ref(null),reviewOpen=ref(false)
let disposed=false,timer=null
const token=()=>({project_uid:props.project.uid,expected_project_version:props.project.version})
const base=()=>`/api/voice/books/projects/${props.project.id}`
function schedule(){timer=setTimeout(()=>{if(disposed)return;if(busy.value){schedule();return}run(load)},2000)}
async function run(fn){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){if(!disposed)error.value=e.message}finally{if(!disposed)busy.value=false}}
async function load(){
  clearTimeout(timer)
  if(!props.project?.book_source){book.value=null;return}
  const data=await api.get(base(),{offset:offset.value,limit:30})
  if(disposed)return
  book.value=data;emit('changed',data.project)
  let active=data.chapters.some(c=>['queued','running'].includes(c.import?.status))
  if(followRange.value){const range=await api.get(base()+'/imports/range',followRange.value);if(disposed)return;rangeRows.value=range.items;active=active||range.items.some(c=>['queued','running'].includes(c.import?.status));emit('changed',range.project);if(!active)followRange.value=null}
  if(active)schedule()
}
async function inspect(){const data=await api.get(`/api/voice/books/sources/${Number(assetId.value)}`,{limit:30});if(!disposed){preview.value=data;title.value=(data.title+' 配音工程').slice(0,200)}}
async function create(){const row=await api.post(`/api/voice/books/sources/${Number(assetId.value)}/projects`,{title:title.value,source_fingerprint:preview.value.source.fingerprint});if(!disposed){preview.value=null;emit('created',row)}}
async function queue(chapter){const data=await api.post(base()+'/imports',{...token(),source_fingerprint:book.value.source.fingerprint,chapter_index:chapter.index});if(!disposed){emit('changed',data.project);await load()}}
async function cancel(chapter){await api.post(base()+`/imports/${chapter.import.id}/cancel`,token());if(!disposed)await load()}
async function inspectRange(){const a=Number(first.value)-1,b=Number(last.value)-1;if(!Number.isInteger(a)||!Number.isInteger(b)||a<0||b<a||b-a>=20)throw new Error('请选择从1开始的连续至多20章');const body={...token(),source_fingerprint:book.value.source.fingerprint,first:a,last:b};const data=await api.post(base()+'/imports/preview',body);if(!disposed)rangePreview.value={...data,request:body}}
async function queueRange(){const request={...rangePreview.value.request};const data=await api.post(base()+'/imports/batch',request);if(disposed)return;rangePreview.value=null;followRange.value={first:request.first,last:request.last};offset.value=Math.floor(request.first/30)*30;emit('changed',data.project);await load()}
function reviewed(row){emit('changed',row);emit('reviewed')}
watch(()=>props.project?.uid,()=>{offset.value=0;book.value=null;rangePreview.value=null;rangeRows.value=[];followRange.value=null;reviewOpen.value=false;first.value=1;last.value=1;run(load)},{immediate:true})
watch([first,last,()=>props.project?.version],()=>{rangePreview.value=null})
onBeforeUnmount(()=>{disposed=true;clearTimeout(timer)})
</script>
<template>
  <section class="card grid">
    <details><summary>从已确认章节的小说创建配音工程</summary><div class="grid">
      <p class="muted">先在章节整理确认目录。原文保留，朗读稿另存；规则识别的说话人候选需要人工核对。</p>
      <div class="row"><label class="field">小说素材 ID<input v-model="assetId" type="number" min="1"/></label><button :disabled="busy||!assetId" @click="run(inspect)">只读预览来源</button><RouterLink v-if="assetId" :to="'/chapters/'+assetId">打开章节整理</RouterLink></div>
      <div v-if="preview" class="grid"><p>{{preview.title}} · {{preview.total}} 章 · 已确认目录 #{{preview.source.revision_id}}</p><label class="field">新工程名称<input v-model="title" maxlength="200"/></label><p class="small muted">{{preview.chapters.map(c=>c.title).join(' · ')}}{{preview.total>30?'…':''}}</p><button :disabled="busy||!title.trim()" @click="run(create)">创建独立工程（不修改小说）</button></div>
    </div></details>
    <p v-if="error" class="notice" role="alert">{{error}}</p>
    <button v-if="project?.book_source&&!book" :disabled="busy" @click="run(load)">重新核对小说来源</button>
    <div v-if="book" class="grid">
      <div class="row"><b>小说章节</b><button :disabled="busy" @click="run(load)">刷新导入进度</button><RouterLink :to="'/chapters/'+book.source.asset_id">来源章节</RouterLink></div>
      <small class="muted">每章每次至多10万字符/1000片段；批次按章串行，长章达到上限时暂停后续章，重新选择同一范围可续导。原文和已手改朗读稿保留；不执行AI/TTS。取消一章会停止它所属批次，已保存片段保留。</small>
      <div class="row"><label class="field">起始章（1起）<input v-model.number="first" type="number" min="1" :max="book.total"/></label><label class="field">结束章（含，最多20章）<input v-model.number="last" type="number" :min="first" :max="book.total"/></label><button :disabled="busy" @click="run(inspectRange)">预览章节范围</button></div>
      <div v-if="rangePreview" class="card grid"><p>将按顺序处理 {{rangePreview.items.length}} 章；已完成的不重复，未完成的使用已保存游标。</p><small v-for="c in rangePreview.items" :key="c.index">第{{c.index+1}}章 {{c.title}} · {{c.import?.status||'未导入'}}</small><button :disabled="busy" @click="run(queueRange)">确认批量导入/续导朗读稿</button></div>
      <div v-if="rangeRows.length" class="card grid"><b>最近批次进度（{{rangeRows.length}}章）</b><small v-for="c in rangeRows" :key="c.index">第{{c.index+1}}章：{{c.import?.status||'未导入'}}<template v-if="c.import"> · {{c.import.cursor}} / {{c.import.end}}</template></small></div>
      <div v-for="chapter in book.chapters" :key="chapter.index" class="row"><span>{{chapter.title}}</span><small>{{chapter.import?.status||'未导入'}}<template v-if="chapter.import"> · {{chapter.import.cursor}} / {{chapter.import.end}}</template></small><button :disabled="busy||['queued','running','done'].includes(chapter.import?.status)" @click="run(()=>queue(chapter))">{{chapter.import?'续导/重试':'导入本章草稿'}}</button><button v-if="['queued','running'].includes(chapter.import?.status)" :disabled="busy" @click="run(()=>cancel(chapter))">取消本批</button><small v-if="chapter.import?.error_code" role="alert">{{chapter.import.error_code}}；请核对来源或续导前章。</small></div>
      <div class="row"><button :disabled="busy||!offset" @click="offset-=30;run(load)">章节上页</button><small>{{book.total}} 章</small><button :disabled="busy||offset+30>=book.total" @click="offset+=30;run(load)">章节下页</button></div>
      <button :aria-expanded="reviewOpen" @click="reviewOpen=!reviewOpen">{{reviewOpen?'收起':'打开'}}说话人审核与声线批量设置</button>
      <VoiceNovelReview v-if="reviewOpen" :project="project" @changed="row=>emit('changed',row)" @saved="reviewed"/>
      <small class="muted">导入完成后刷新下方片段列表；关闭页面只停止状态轮询，后台有界批次按既有任务继续。重启不自动重放，显式续导；原目录/正文变化不覆盖已保存草稿。</small>
    </div>
  </section>
</template>
<style scoped>.field{min-width:0;flex:1 1 160px}input{min-width:0;max-width:100%}small{overflow-wrap:anywhere}</style>
