<script setup>
import {onBeforeUnmount,ref,watch} from 'vue'
import {api} from '../api'
const props=defineProps({project:Object}),emit=defineEmits(['changed','saved'])
const rows=ref([]),total=ref(0),offset=ref(0),chapter=ref(''),speaker=ref(''),review=ref('pending'),stats=ref(null)
const selected=ref({}),selectionToken=ref(null),busy=ref(false),error=ref(''),prepared=ref(null)
const changeName=ref(false),name=ref(''),changeVoice=ref(false),voice=ref(''),confirm=ref(false)
let disposed=false
const base=()=>`/api/voice/books/projects/${props.project.id}`
const count=()=>Object.keys(selected.value).length
async function run(fn){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){if(!disposed)error.value=e.message}finally{if(!disposed)busy.value=false}}
async function load(){const data=await api.get(base()+'/review',{limit:20,offset:offset.value,review:review.value,chapter:chapter.value===''?undefined:Number(chapter.value)-1,speaker:speaker.value||undefined});if(disposed)return;rows.value=data.items;total.value=data.total;stats.value=data.stats;emit('changed',data.project)}
function resetEditing(){changeName.value=false;name.value='';changeVoice.value=false;voice.value='';confirm.value=false}
function clear(){selected.value={};selectionToken.value=null;prepared.value=null;resetEditing()}
function choose(row){const next={...selected.value};if(next[row.uid])delete next[row.uid];else{if(count()>=100){error.value='每批最多100条，请先提交或清空';return}if(!count()){resetEditing();selectionToken.value={project_uid:props.project.uid,expected_project_version:props.project.version}}next[row.uid]={id:row.id,uid:row.uid,version:row.version,speaker:row.speaker,profile_id:row.profile_id,confirm:row.confirmed}}selected.value=next;prepared.value=null;if(!count()){selectionToken.value=null;resetEditing()}}
function payload(edit){return {...selectionToken.value,entries:Object.values(selected.value).map(e=>({...e,...(edit&&changeName.value?{speaker:name.value}:{}),...(edit&&changeVoice.value?{profile_id:voice.value===''?null:Number(voice.value)}:{}),...(edit&&confirm.value?{confirm:true}:{})}))}}
async function save(){const result=await api.post(base()+'/review',payload(true));if(disposed)return;clear();emit('saved',result.project);await load()}
async function prepare(){const result=await api.post(base()+'/prepare',payload(false));if(!disposed)prepared.value=result}
const labels={speaker_review_required:'说话人待审核',empty_text:'朗读稿为空',voice_reference_invalid:'声线/范围引用异常',voice_missing:'未设置声线',model_missing:'未登记模型',engine_unconfigured:'未配置引擎',language_missing:'未设置语言',model_file_missing:'模型文件缺失',model_file_unregistered:'未登记模型文件',model_file_unsupported_path:'模型路径格式不支持',model_file_unreadable:'模型文件不可读'}
watch(()=>props.project?.uid,()=>{offset.value=0;clear();run(load)},{immediate:true})
watch(()=>props.project?.version,()=>{prepared.value=null})
onBeforeUnmount(()=>{disposed=true})
</script>
<template>
  <section class="grid review">
    <p class="muted">规则候选不代表真实身份。跨页选择最多100条；提交只更新说话人、人工确认状态和声线，不覆盖朗读稿、证据、顺序或语言。选择后其他窗口修改时，整批拒绝覆盖，请清空并重新核对。</p>
    <p v-if="error" class="notice" role="alert">{{error}}</p>
    <p v-if="stats" class="small">全工程 {{stats.total}} 条 · 待审核 {{stats.pending}} · 未设声线 {{stats.voice_missing}} · 有采纳记录 {{stats.accepted_records}}（不等于当前可用，需预检）</p>
    <form class="row" @submit.prevent="offset=0;run(load)">
      <label class="field">审核章节（1起，可留空）<input v-model="chapter" type="number" min="1"/></label>
      <label class="field">说话人（完全匹配，可留空）<input v-model="speaker" maxlength="200"/></label>
      <label class="field">审核状态<select v-model="review" aria-label="审核状态"><option value="pending">待审核</option><option value="confirmed">已确认</option><option value="all">全部</option></select></label>
      <button :disabled="busy">筛选审核列表</button>
    </form>
    <div v-for="row in rows" :key="row.uid" class="card grid">
      <label class="row"><input type="checkbox" :checked="!!selected[row.uid]" :disabled="busy" @change="choose(row)"/>第{{row.chapter_index+1}}章 · {{row.speaker}} · {{row.confirmed?'已人工确认':'待审核'}} · 声线 #{{row.profile_id||'未设'}}</label>
      <p class="excerpt">{{row.preview}}</p>
      <small>来源 {{row.start}}–{{row.end}} · {{row.kind==='dialogue_candidate'?'对白候选':'旁白候选'}} · {{row.method}}</small>
      <details><summary>查看原文证据（摘要）</summary><p class="excerpt">{{row.evidence}}{{row.evidence_truncated?'…':''}}</p><RouterLink :to="'/chapters/'+project.book_source.asset_id">核对完整来源章节</RouterLink></details>
    </div>
    <p v-if="!rows.length" class="muted">此筛选下没有待处理片段；未知说话人可保留待确认。</p>
    <div class="row"><button :disabled="busy||!offset" @click="offset-=20;run(load)">审核上页</button><small>{{total}} 条 · 已选 {{count()}} / 100</small><button :disabled="busy||offset+20>=total" @click="offset+=20;run(load)">审核下页</button><button :disabled="busy||!count()" @click="clear">清空审核选择</button></div>
    <div v-if="count()" class="card grid">
      <label class="row"><input v-model="changeName" type="checkbox"/>为所选片段统一设置说话人</label><label v-if="changeName" class="field">批量说话人<input v-model="name" maxlength="200" placeholder="核对后填写姓名或旁白"/></label>
      <label class="row"><input v-model="changeVoice" type="checkbox"/>为所选片段设置声线（留空解除）</label><label v-if="changeVoice" class="field">批量声线档案 ID<input v-model="voice" type="number" min="1"/></label>
      <label class="row"><input v-model="confirm" type="checkbox"/>我已逐条核对所选片段的说话人</label>
      <div class="row"><button :disabled="busy" @click="run(save)">保存所选审核与声线</button><button :disabled="busy" @click="run(prepare)">预检已保存的所选片段</button></div>
      <p class="muted">预检读取已保存配置，不应用上方尚未提交的改动；只作文件/身份检查，不连接引擎、不排队合成。</p>
    </div>
    <div v-if="prepared" class="card grid"><b>配置预检（未验证引擎运行）</b><p v-for="item in prepared.items" :key="item.uid" class="excerpt">片段 #{{item.id}}：{{item.configuration_ready?'配置完整，仍需真实服务与授权验收':item.issues.map(code=>labels[code]||code).join('、')}} · {{item.accepted_current?'有当前有效采纳音频':'无当前有效采纳音频'}}</p></div>
  </section>
</template>
<style scoped>.review{min-width:0}.excerpt{white-space:pre-wrap;overflow-wrap:anywhere;margin:0}input,select{min-width:0;max-width:100%}.field{flex:1 1 160px}</style>
