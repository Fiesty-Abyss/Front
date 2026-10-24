<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api, Worlds } from '../api'
import JobProgress from './JobProgress.vue'
import TagPicker from './TagPicker.vue'
const props=defineProps({reportId:String,initialWorldId:[String,Number],importId:String})
const open=ref(false),page=ref({items:[],total:0}),offset=ref(0),choices=ref({}),worlds=ref([]),worldId=ref(props.initialWorldId||''),worldName=ref(''),target=ref(props.initialWorldId?'existing':'new'),mode=ref('')
const tags=ref([]),labels=ref([]),labelIds=ref([]),error=ref(''),busy=ref(false),job=ref(null),run=ref(null)
let disposed=false,timer
onBeforeUnmount(()=>{disposed=true;clearTimeout(timer)})
watch(worldId,async id=>{labelIds.value=[];labels.value=id?await api.get(`/api/worlds/${id}/labels`).catch(()=>[]):[]})
const count=computed(()=>Object.keys(choices.value).length)
async function load(start=0){page.value=await api.get(`/api/project-previews/${props.reportId}`,{limit:50,offset:start});offset.value=start;if(!worldName.value)worldName.value=page.value.root.split(/[\\/]/).filter(Boolean).pop()}
async function show(){open.value=!open.value;if(open.value){try{await load();worlds.value=(await Worlds.list({limit:500})).items;if(worldId.value)labels.value=await api.get(`/api/worlds/${worldId.value}/labels`)}catch(e){error.value=e.message}}}
function toggle(file){const key=file.index;if(choices.value[key])delete choices.value[key];else choices.value[key]={index:key,title:file.name.replace(/\.[^.]+$/,''),category:file.candidate||'resource'}}
function choosePage(){for(const f of page.value.items)if(f.sha256&&!f.error&&!choices.value[f.index])toggle(f)}
async function all(){busy.value=true;try{for(let start=0;start<page.value.total;start+=100){const data=await api.get(`/api/project-previews/${props.reportId}`,{limit:100,offset:start});if(disposed)return;for(const f of data.items)if(f.sha256&&!f.error&&!choices.value[f.index])toggle(f)}}catch(e){error.value=e.message}finally{busy.value=false}}
async function poll(importId,jobId){if(disposed)return;try{const [j,r]=await Promise.all([api.get(`/api/jobs/${jobId}`),api.get(`/api/project-imports/${importId}`)]);if(disposed)return;job.value=j;run.value=r;busy.value=['queued','running'].includes(j.status);if(busy.value)timer=setTimeout(()=>poll(importId,jobId),600)}catch(e){if(!disposed){error.value=e.message;busy.value=false}}}
async function start(){error.value='';busy.value=true;try{const data=await api.post('/api/project-imports',{report_id:props.reportId,world_id:target.value==='existing'?Number(worldId.value):null,new_world_name:target.value==='new'?worldName.value:null,mode:mode.value,files:Object.values(choices.value).map(f=>({...f,tag_ids:tags.value,label_ids:target.value==='existing'?labelIds.value:[]}))});await poll(data.import_id,data.job.id)}catch(e){error.value=e.message;busy.value=false}}
async function resume(){busy.value=true;try{const data=await api.post(`/api/project-imports/${run.value.id}/resume`);await poll(data.import_id,data.job.id)}catch(e){error.value=e.message;busy.value=false}}
onMounted(async()=>{if(props.importId){try{run.value=await api.get(`/api/project-imports/${props.importId}`);worldId.value=run.value.world_id;target.value='existing';mode.value=run.value.mode;await show();if(['running','queued'].includes(run.value.status)&&run.value.job_id)await poll(run.value.id,run.value.job_id)}catch(e){error.value=e.message}}})
</script>
<template>
<section class="card grid">
<div class="row"><h2 style="margin:0">正式归档</h2><span class="small muted">预览不等于导入，只有明确确认后才创建档案。</span><span class="spacer"/><button @click="show">{{open?'收起导入确认':'选择文件与导入方式'}}</button></div>
<template v-if="open">
<p v-if="error" role="alert" class="notice">{{error}}</p>
<div class="grid cols-2"><label class="field">目标方式<select v-model="target"><option value="new">新建独立世界观</option><option value="existing">已有世界观</option></select></label><label v-if="target==='new'" class="field">新世界观名称<input v-model="worldName" maxlength="200"/></label><label v-else class="field">目标世界观<select v-model="worldId"><option value="">请选择</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{w.name}} · #{{w.id}}</option></select></label></div>
<label class="field">文件存储方式（必须选择）<select v-model="mode"><option value="">请选择</option><option value="index">原地索引：不复制原文件</option><option value="managed">托管导入：复制到 Front，保留原件</option></select></label>
<p class="small muted">原地索引依赖原文件位置；修改/移动会提示审核。托管模式复用相同内容，不覆盖已有档案。资料候选不会自动变成同名人物。</p>
<details><summary>统一添加全局标签</summary><TagPicker v-model="tags"/></details>
<div v-if="target==='existing' && labels.length" class="row"><label v-for="l in labels" :key="l.id" class="row small"><input v-model="labelIds" type="checkbox" :value="l.id" style="width:auto"/>{{l.name}}</label></div>
<div class="row"><b>已确认 {{count}} 项</b><button :disabled="busy" @click="choosePage">确认本页</button><button :disabled="busy" @click="all">确认全部可导入文件</button><button :disabled="busy" @click="choices={}">清空选择</button></div>
<div class="import-table"><table><thead><tr><th>确认</th><th>文件 / 类型 / 大小</th><th>档案标题与候选分类</th></tr></thead><tbody><tr v-for="f in page.items" :key="f.index"><td><input type="checkbox" :checked="!!choices[f.index]" :disabled="busy||!f.sha256||!!f.error" @change="toggle(f)"/></td><td>{{f.relative}}<small class="muted">{{f.kind}} · {{f.bytes?.toLocaleString()}} bytes</small></td><td v-if="choices[f.index]"><input v-model="choices[f.index].title" :aria-label="`档案标题 ${f.index+1}`" maxlength="300"/><select v-model="choices[f.index].category" :aria-label="`候选分类 ${f.index+1}`"><option v-for="(v,k) in {character:'人物资料',organization:'组织资料',location:'地点资料',novel:'小说/剧情',world:'世界设定',image:'图片',resource:'其他资源'}" :key="k" :value="k">{{v}}</option></select></td><td v-else>{{f.reason||f.error}}</td></tr></tbody></table></div>
<div class="row"><button :disabled="!offset||busy" @click="load(offset-50)">上一页</button><span>{{Math.floor(offset/50)+1}} / {{Math.max(1,Math.ceil(page.total/50))}}</span><button :disabled="offset+50>=page.total||busy" @click="load(offset+50)">下一页</button><span class="spacer"/><button class="primary" :disabled="busy||!count||!mode||(target==='new'?!worldName.trim():!worldId)" @click="start">确认导入所选 {{count}} 项</button></div>
<JobProgress :job="job"/>
<template v-if="run"><p class="small">持久导入批次 {{run.id}} · {{run.status}} · {{run.counts}}</p><div v-for="item in run.items.filter(i=>i.message)" :key="item.index" class="notice">{{item.title}}：{{item.message}}</div><div class="row"><button v-if="['interrupted','cancelled','partial'].includes(run.status)" :disabled="busy" @click="resume">恢复未完成项目</button><RouterLink class="btn primary" :to="{path:'/worlds',query:{id:run.world_id,tab:'archive'}}">打开世界观项目档案</RouterLink></div></template>
</template>
</section>
</template>
<style scoped>.import-table{max-height:440px;overflow:auto}td{overflow-wrap:anywhere;min-width:70px}td small{display:block}td input{min-width:0}summary{cursor:pointer}</style>
