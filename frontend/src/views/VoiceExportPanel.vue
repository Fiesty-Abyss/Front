<script setup>
import {onBeforeUnmount,ref,watch} from 'vue'
import {api} from '../api'
import JobProgress from '../components/JobProgress.vue'
const props=defineProps({project:Object,segments:Array,archived:Boolean})
const preview=ref(null),rows=ref([]),chosen=ref([]),offset=ref(0),total=ref(0),busy=ref(false),error=ref(''),pendingKey=ref('')
const candidates=ref([]),page=ref(0),candidateTotal=ref(0),chapter=ref(''),appliedChapter=ref(null),pause=ref(0),checkJob=ref(null),progress=ref({}),opened=ref(false)
const errors={export_validation_failed_413:'超过音轨64MiB、含停顿总PCM128MiB或上传限额，请分批导出',export_validation_failed_422:'音频须为完整且同采样率、声道、位深的PCM WAV；未执行转码',export_validation_failed_409:'工程、采纳版本或音频Hash变化，请重新审核',export_validation_failed_404:'音轨或素材丢失，未自动补写',process_interrupted:'服务中断，原件保留；请重新预览后重试',queue_unavailable:'后台队列已满，请稍后重新预览',export_failed:'导出失败；请检查来源和磁盘，原件保留'}
let disposed=false,epoch=0,timer=null,context=null
const base=()=>`/api/voice/projects/${props.project.id}/exports`
const token=()=>({project_uid:props.project.uid,expected_project_version:props.project.version})
const payload=()=>({...token(),segment_ids:chosen.value.map(s=>s.id),segment_refs:chosen.value.map(({id,uid,version})=>({id,uid,version})),pause_ms:Number(pause.value)})
const requestKey=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),value=>value.toString(16).padStart(2,'0')).join('')
const active=()=>['queued','running'].includes(checkJob.value?.status)||rows.value.some(r=>['queued','running'].includes(r.status))
function schedule(){clearTimeout(timer);if(!disposed&&opened.value&&active())timer=setTimeout(()=>{if(busy.value){schedule();return}run(poll)},1500)}
async function run(fn){if(busy.value)return;const key=epoch;busy.value=true;error.value='';try{await fn(key)}catch(e){if(!disposed&&key===epoch)error.value=e.message}finally{if(!disposed&&key===epoch){busy.value=false;schedule()}}}
async function loadRows(key){const data=await api.get(base(),{limit:20,offset:offset.value});if(disposed||key!==epoch)return;rows.value=data.items;total.value=data.total;const jobs={};for(const row of data.items){if(row.job_id&&['queued','running'].includes(row.status)){const value=await api.get('/api/jobs/'+row.job_id);if(disposed||key!==epoch)return;jobs[row.uid]=value}}progress.value=jobs}
async function loadCandidates(key){const data=await api.get(base()+'/segments',{limit:20,offset:page.value*20,...(appliedChapter.value===null?{}:{chapter:appliedChapter.value})});if(disposed||key!==epoch)return;if(data.project_uid!==props.project.uid||data.project_version!==props.project.version)throw new Error('工程已变化，请刷新工程后重新选择');candidates.value=data.items;candidateTotal.value=data.total}
async function load(key){await loadRows(key);if(!disposed&&key===epoch)await loadCandidates(key)}
async function filter(key){const value=chapter.value===''?null:Number(chapter.value);if(value!==null&&(!Number.isInteger(value)||value<1))throw new Error('章节序号必须为1起整数，或留空');appliedChapter.value=value===null?null:value-1;page.value=0;await loadCandidates(key)}
function selected(row){return chosen.value.some(s=>s.uid===row.uid)}
function toggle(row){if(selected(row))chosen.value=chosen.value.filter(s=>s.uid!==row.uid);else if(chosen.value.length<100)chosen.value=[...chosen.value,row];else error.value='一次最多明确选择100条，请先分批导出'}
function selectPage(){const next=[...chosen.value];for(const row of candidates.value)if(!next.some(s=>s.uid===row.uid)&&next.length<100)next.push(row);chosen.value=next}
async function inspect(key){const data=await api.post(base()+'/preview',payload());if(!disposed&&key===epoch){preview.value=data;pendingKey.value=requestKey()}}
async function create(key){await api.post(base(),{...payload(),fingerprint:preview.value.fingerprint,idempotency_key:pendingKey.value});if(disposed||key!==epoch)return;preview.value=null;pendingKey.value='';offset.value=0;await loadRows(key)}
async function precheck(key){const result=await api.post(base()+'/preflight',payload());if(!disposed&&key===epoch)checkJob.value=result}
async function poll(key){if(checkJob.value){const value=await api.get('/api/jobs/'+checkJob.value.id);if(disposed||key!==epoch)return;checkJob.value=value}await loadRows(key)}
async function cancel(row,key){await api.post(base()+`/${row.id}/cancel`,token());if(!disposed&&key===epoch)await loadRows(key)}
function invalidate(){epoch++;busy.value=false;preview.value=null;pendingKey.value='';checkJob.value=null;clearTimeout(timer);schedule()}
watch(()=>JSON.stringify([props.project?.uid,props.project?.version,props.archived]),()=>{const moved=context!==props.project?.uid;context=props.project?.uid;invalidate();chosen.value=[];if(moved){rows.value=[];offset.value=0;total.value=0;page.value=0;chapter.value='';appliedChapter.value=null}if(opened.value)run(load)},{immediate:true})
watch(()=>JSON.stringify([chosen.value.map(s=>[s.id,s.uid,s.version]),pause.value]),invalidate,{flush:'sync'})
function opening(event){opened.value=event.target.open;if(opened.value)run(load);else clearTimeout(timer)}
onBeforeUnmount(()=>{disposed=true;epoch++;clearTimeout(timer)})
</script>
<template>
  <details class="card grid" @toggle="opening">
    <summary>导出已采纳片段 · PCM WAV / SRT / VTT</summary>
    <p class="muted">独立分页选择，翻页或切换章节保留已选项；最多100条/20万字符。按工程排序拼接同格式PCM，不转码或改原件。工程版本变化需重新选择；章节序号从1起。字幕是片段级顺序时间，不是逐字对齐。</p>
    <p v-if="error" class="notice" role="alert">{{error}}</p>
    <div class="row"><label class="field">章节序号（留空全部）<input v-model="chapter" type="number" min="1" step="1" :disabled="busy"/></label><button :disabled="busy||archived" @click="run(filter)">筛选导出片段</button></div>
    <div class="row"><button :disabled="busy||archived||!candidates.length||chosen.length>=100" @click="selectPage">选择此导出页</button><button :disabled="busy||!chosen.length" @click="chosen=[]">清空跨页选择</button><b>已选 {{chosen.length}} / 100</b></div>
    <div v-if="!archived" class="grid"><label v-for="segment in candidates" :key="segment.uid" class="row"><input type="checkbox" :checked="selected(segment)" :disabled="busy||(!selected(segment)&&chosen.length>=100)" @change="toggle(segment)"/><span>{{segment.chapter_index==null?'独立片段':'第'+(segment.chapter_index+1)+'章'}} · {{segment.speaker}}：{{segment.preview}} · {{segment.accepted_current?'已有当前采纳音频':'缺少有效采纳音频'}}{{!segment.confirmed?' · 说话人待审核':''}}</span></label></div>
    <div class="row"><button :disabled="busy||page===0" @click="page--;run(loadCandidates)">导出片段上页</button><small>{{candidateTotal}} 条 · 第 {{page+1}} 页</small><button :disabled="busy||(page+1)*20>=candidateTotal" @click="page++;run(loadCandidates)">导出片段下页</button></div>
    <label class="field">片段间停顿（毫秒；0–10000）<input v-model.number="pause" type="number" min="0" max="10000" step="1" :disabled="busy"/></label>
    <div class="row"><button :disabled="busy||archived||!chosen.length" @click="run(precheck)">后台校验格式与音量差异</button><button :disabled="busy||archived||!chosen.length" @click="run(inspect)">预览选定片段导出</button><button :disabled="busy" @click="run(loadRows)">刷新导出记录</button></div>
    <JobProgress v-if="checkJob" :job="checkJob"/>
    <div v-if="checkJob?.status==='done'" class="notice grid"><b>{{checkJob.result.compatible?'音轨格式兼容':'存在不兼容、缺失或超限音轨，请先检查'}}</b><small>PCM16按全部采样估算RMS/峰值；不是LUFS响度标准化。其他位深不提供音量结论。</small><p v-if="checkJob.result.level_difference_warning">音轨RMS相差超过6dB，建议试听；未调整音量。</p><p v-if="checkJob.result.total_limit_exceeded">含停顿PCM超过限额，后续项未继续读取，请分批导出。</p><ul><li v-for="item in checkJob.result.items" :key="item.segment_uid">片段 #{{item.segment_id}} · {{item.issue||`${item.sample_rate} Hz / ${item.channels}声道 / ${item.sample_width*8}bit`}}{{item.silent?' · 静音':''}}</li></ul></div>
    <div v-if="preview" class="notice grid"><b>{{preview.snapshot.items.length}} 条片段 · 工程当前排序 · 停顿 {{pause}} ms</b><p v-if="preview.snapshot.contains_mock">包含Mock标记音，不是AI朗读；标记保留在清单。</p><ol><li v-for="item in preview.snapshot.items" :key="item.segment_uid">{{item.speaker}}：{{item.text.slice(0,80)}}</li></ol><button :disabled="busy" @click="run(create)">确认并排队导出 ZIP</button></div>
    <div v-for="row in rows" :key="row.uid" class="grid"><div class="row"><span>{{row.status}} · {{row.created_at}} {{errors[row.error_code]||row.error_code}}{{row.status==='done'&&!row.asset_id?' · 素材已删除，可重新生成':''}}</span><RouterLink v-if="row.status==='done'&&row.asset_id" :to="'/assets?open='+row.asset_id">查看导出素材并下载 ZIP</RouterLink><button v-if="['queued','running'].includes(row.status)" :disabled="busy" @click="run(key=>cancel(row,key))">取消导出任务</button></div><JobProgress v-if="progress[row.uid]" :job="progress[row.uid]"/></div>
    <div class="row"><button :disabled="busy||!offset" @click="offset-=20;run(loadRows)">导出记录上页</button><small>{{total}} 条导出记录</small><button :disabled="busy||offset+20>=total" @click="offset+=20;run(loadRows)">导出记录下页</button></div>
  </details>
</template>
<style scoped>.grid,.row span,.field{min-width:0}.row span,li{overflow-wrap:anywhere}input[type=checkbox]{width:auto;flex:0 0 auto}input[type=number]{max-width:100%;min-width:0}</style>
