<script setup>
import {onBeforeUnmount,ref,watch} from 'vue'
import {api} from '../api'
import {exportContext} from '../voiceDrafts'
const props=defineProps({project:Object,segments:Array,archived:Boolean})
const preview=ref(null),rows=ref([]),chosen=ref([]),offset=ref(0),total=ref(0),busy=ref(false),error=ref('')
const pendingKey=ref('')
const errors={export_validation_failed_413:'超过音轨64MiB、总PCM128MiB或资料库上传限额，请分批导出',export_validation_failed_422:'音频须为完整且同采样率、声道、位深的PCM WAV；未执行转码',export_validation_failed_409:'工程、采纳版本或实际音频Hash变化，请重新审核',process_interrupted:'服务中断，原件保留；请重新预览后重试',queue_unavailable:'后台队列已满，请稍后重新预览并排队',export_failed:'导出失败；请检查来源和磁盘空间，原件保留'}
let disposed=false,epoch=0
errors.export_validation_failed_404='音轨或关联素材已丢失，请检查来源；未自动补写原文件'
const base=()=>`/api/voice/projects/${props.project.id}/exports`
const token=()=>({project_uid:props.project.uid,expected_project_version:props.project.version})
const requestKey=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),value=>value.toString(16).padStart(2,'0')).join('')
async function run(fn){if(busy.value)return;const key=epoch;busy.value=true;error.value='';try{await fn(key)}catch(e){if(!disposed&&key===epoch)error.value=e.message}finally{if(!disposed&&key===epoch)busy.value=false}}
async function load(key=epoch){const data=await api.get(base(),{limit:20,offset:offset.value});if(!disposed&&key===epoch){rows.value=data.items;total.value=data.total}}
async function inspect(key){const data=await api.post(base()+'/preview',{...token(),segment_ids:[...chosen.value]});if(!disposed&&key===epoch){preview.value=data;pendingKey.value=requestKey()}}
async function create(key){const ids=preview.value.snapshot.items.map(s=>s.segment_id);await api.post(base(),{...token(),segment_ids:ids,fingerprint:preview.value.fingerprint,idempotency_key:pendingKey.value});if(disposed||key!==epoch)return;preview.value=null;pendingKey.value='';offset.value=0;await load(key)}
async function cancel(row,key){await api.post(base()+`/${row.id}/cancel`,token());if(!disposed&&key===epoch)await load(key)}
let contextUID=null
watch(()=>exportContext(props.project,props.segments),()=>{const moved=contextUID!==props.project?.uid;contextUID=props.project?.uid;epoch++;busy.value=false;preview.value=null;pendingKey.value='';chosen.value=[];if(moved){rows.value=[];offset.value=0;total.value=0}run(load)},{immediate:true})
watch(chosen,()=>{preview.value=null;pendingKey.value=''},{deep:true})
onBeforeUnmount(()=>{disposed=true;epoch++})
</script>
<template>
  <details class="card grid">
    <summary>导出已采纳片段 · PCM WAV / SRT / VTT</summary>
    <p class="muted">勾选当前页中需要的有效片段（API最多100条）。每条须已采纳与当前指纹一致的音频。后台按工程顺序拼接同格式 PCM WAV，字幕按片段时长顺序计时，不是语音强制对齐；不调用 TTS 或转码器。可按章节或分页分批导出。</p>
    <p v-if="error" class="notice" role="alert">{{error}}</p>
    <div class="row"><button :disabled="busy||archived||!segments?.length" @click="chosen=segments.map(s=>s.id)">选择当前页</button><button :disabled="busy||!chosen.length" @click="chosen=[]">清空选择</button></div>
    <div v-if="!archived" class="grid"><label v-for="segment in segments" :key="segment.uid" class="row"><input v-model="chosen" type="checkbox" :value="segment.id" :disabled="busy"/><span>{{segment.speaker}}：{{segment.text.slice(0,80)}}</span></label></div>
    <div class="row"><button :disabled="busy||archived||!chosen.length" @click="run(inspect)">预览选定片段导出</button><button :disabled="busy" @click="run(load)">刷新导出记录</button></div>
    <div v-if="preview" class="notice grid"><b>{{preview.snapshot.items.length}} 条片段 · 工程当前排序</b><p v-if="preview.snapshot.contains_mock">包含 Mock 标记音，不是 AI 朗读；此标记会保存在导出清单。</p><ol><li v-for="item in preview.snapshot.items" :key="item.segment_uid">{{item.speaker}}：{{item.text.slice(0,80)}}</li></ol><button :disabled="busy" @click="run(create)">确认并排队导出 ZIP</button></div>
    <div v-for="row in rows" :key="row.uid" class="row"><span>{{row.status}} · {{row.created_at}} {{errors[row.error_code]||row.error_code}}{{row.status==='done'&&!row.asset_id?' · 导出素材已删除，可重新预览生成':''}}</span><RouterLink v-if="row.status==='done'&&row.asset_id" :to="'/assets?open='+row.asset_id">查看导出素材并下载 ZIP</RouterLink><button v-if="['queued','running'].includes(row.status)" :disabled="busy" @click="run(key=>cancel(row,key))">取消</button></div>
    <div class="row"><button :disabled="busy||!offset" @click="offset-=20;run(load)">上页</button><small>{{total}} 条导出记录</small><button :disabled="busy||offset+20>=total" @click="offset+=20;run(load)">下页</button></div>
  </details>
</template>
<style scoped>
.grid,.row span{min-width:0}.row span,li{overflow-wrap:anywhere}input[type="checkbox"]{width:auto;flex:0 0 auto}
</style>
