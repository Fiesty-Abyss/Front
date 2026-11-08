<script setup>
import {defineAsyncComponent,onBeforeUnmount,onMounted,ref} from 'vue'
import {onBeforeRouteLeave} from 'vue-router'
import {api} from '../api'
import JobProgress from '../components/JobProgress.vue'
import VersionPanel from '../components/VersionPanel.vue'
const AssetPicker=defineAsyncComponent(()=>import('../components/AssetPicker.vue'))
const AudioPlayer=defineAsyncComponent(()=>import('../viewers/AudioPlayer.vue'))
const rows=ref([]),total=ref(0),offset=ref(0),q=ref(''),current=ref(null),draft=ref(null),profileID=ref(''),saved=ref(''),incoming=ref(null)
const picker=ref(false),sample=ref(null),job=ref(null),report=ref(null),busy=ref(false),error=ref(''),analysisAck=ref(false)
let disposed=false,timer=null,epoch=0
const defaults=()=>({kind:'audition',profile_ref:null,language:'',reference_text:'',source:'',license:'',notes:'',declaration:{speaker_authorized:false,allow_zero_shot:false,allow_training:false,statement:''}})
const signature=()=>JSON.stringify([draft.value,profileID.value])
const isDirty=()=>Boolean(draft.value)&&signature()!==saved.value
function canLeave(){return !busy.value&&(!isDirty()||window.confirm('参考音频档案尚未保存，确认放弃草稿并离开？'))}
defineExpose({canLeave,isDirty})
const token=()=>({asset_ref:current.value.asset_ref,expected_asset_version:current.value.version})
const base=()=>'/api/voice/references/'+current.value.asset_ref.id
const active=()=>['queued','running'].includes(job.value?.status)
function schedule(){clearTimeout(timer);if(!disposed&&active())timer=setTimeout(()=>{if(busy.value){schedule();return}run(poll)},1500)}
async function run(fn){if(busy.value)return;const key=epoch;busy.value=true;error.value='';try{await fn(key)}catch(e){if(!disposed&&key===epoch)error.value=e.message}finally{if(!disposed&&key===epoch){busy.value=false;schedule()}}}
async function load(key=epoch){const data=await api.get('/api/voice/references',{q:q.value,offset:offset.value,limit:20});if(!disposed&&key===epoch){rows.value=data.items;total.value=data.total}}
function adopt(row){current.value=row;draft.value=JSON.parse(JSON.stringify(row.data||defaults()));profileID.value=draft.value.profile_ref?.id||'';saved.value=signature();incoming.value=null;report.value=row.qc;analysisAck.value=false}
async function open(id,identity,key){const row=await api.get('/api/voice/references/'+id);if(disposed||key!==epoch)return;if(identity&&row.asset_ref.identity!==identity.replace(/Z$|\+00:00$/,''))throw new Error('素材ID已被其他记录复用，请重新选择');if(!row.asset_ref.sha256)throw new Error('请先导入具有Hash的音频文件');adopt(row);sample.value=null;job.value=null;picker.value=false;clearTimeout(timer)}
function choose(asset){if(!canLeave())return;if(asset.kind!=='audio'){error.value='请选择素材库音频';return}run(key=>open(asset.id,asset.created_at,key))}
async function save(key){const data=JSON.parse(JSON.stringify(draft.value));if(profileID.value){if(data.profile_ref?.id!==Number(profileID.value)){const row=await api.get('/api/voice/profiles/'+Number(profileID.value));if(disposed||key!==epoch)return;data.profile_ref={id:row.id,uid:row.uid}}}else data.profile_ref=null;const result=await api.put(base(),{...token(),data});if(!disposed&&key===epoch){adopt(result);await load(key)}}
async function refresh(key){const row=await api.get(base());if(disposed||key!==epoch)return;if(isDirty()){incoming.value=row;report.value=row.qc}else adopt(row)}
function reload(){if(!incoming.value||!canLeave())return;adopt(incoming.value)}
async function inspect(key){if(isDirty())throw new Error('请先保存参考档案草稿，或明确重载后再分析');const value=await api.post(base()+'/inspect',{...token(),confirm_local_analysis:analysisAck.value});if(!disposed&&key===epoch)job.value=value}
async function poll(key){const value=await api.get('/api/jobs/'+job.value.id);if(disposed||key!==epoch)return;job.value=value;if(!active())await refresh(key)}
async function listen(key){const row=await api.get('/api/assets/'+current.value.asset_ref.id);if(disposed||key!==epoch)return;const ref=current.value.asset_ref;if(row.created_at.replace(/Z$|\+00:00$/,'')!==ref.identity||row.sha256!==ref.sha256)throw new Error('试听内容已变化，请重新选择');sample.value=row}
const kinds={audition:'试听参考',zero_shot:'零样本参考',training:'训练资料（仅登记）'}
const issues={reference_content_changed:'参考文件版本已变化，请重新审核档案；不自动沿用用途声明',profile_scope_changed:'声线归属变化，请先解除旧关联，再明确审核',profile_missing_or_scope_changed:'关联声线已丢失或世界观/作品变化',invalid_reference_annotation:'参考档案格式异常或不兼容，当前版本不自动覆盖',unsupported_qc_schema:'技术报告来自较新或未知格式，当前版本不覆盖',qc_content_changed:'以下技术报告属于旧音频内容，请重新检查'}
const codes={reference_validation_failed_404:'原音频缺失，未修改文件',reference_validation_failed_409:'素材/版本或Hash变化，报告未覆盖，请刷新后审核',reference_validation_failed_413:'文件超过64MiB技术分析限额',reference_validation_failed_422:'仅支持完整PCM WAV，本功能不转码',reference_file_unreadable:'本机读写失败，请检查音频读取权限、Front暂存目录或磁盘空间；原件保留'}
const percentage=value=>typeof value==='number'?(value*100).toFixed(2)+'%':'未测'
function unload(event){if(isDirty()){event.preventDefault();event.returnValue=''}}
onBeforeRouteLeave(()=>canLeave())
onMounted(()=>{window.addEventListener('beforeunload',unload);run(load)})
onBeforeUnmount(()=>{disposed=true;epoch++;clearTimeout(timer);sample.value=null;window.removeEventListener('beforeunload',unload)})
</script>
<template>
  <div class="grid references">
    <p class="muted">复用素材库音频，登记来源、人工参考文本及用途声明。试听、零样本与训练用途分别记录；保存不验证法律权利，不启动推理、训练、转写或外部服务。训练资料集与切片仍待后续。</p>
    <p v-if="error" role="alert" class="notice">{{error}}</p>
    <div class="workspace">
      <aside class="card grid"><form class="row" @submit.prevent="offset=0;run(load)"><input v-model="q" aria-label="搜索参考音频" maxlength="200"/><button :disabled="busy">搜索参考档案</button></form><button :disabled="busy" @click="picker=true">从素材库登记参考音频</button><p v-if="!rows.length" class="muted">还没有参考档案。可以先登记，不需要TTS引擎。</p><button v-for="row in rows" :key="row.id+'-'+row.created_at" :disabled="busy" :aria-pressed="current?.asset_ref.id===row.id" @click="canLeave()&&run(key=>open(row.id,row.created_at,key))">{{row.title}} · {{kinds[row.kind]||'待审核'}}</button><div class="row"><button :disabled="busy||!offset" @click="offset-=20;run(load)">参考上页</button><small>{{total}} 项</small><button :disabled="busy||offset+20>=total" @click="offset+=20;run(load)">参考下页</button></div></aside>
      <section v-if="draft" class="card grid">
        <h2>{{current.title}}</h2><small>素材 #{{current.asset_ref.id}} · 版本 {{current.version??'尚未记录'}} · {{isDirty()?'有未保存草稿':'资料已同步'}}</small>
        <p v-for="issue in current.issues" :key="issue" class="notice">{{issues[issue]||issue}}</p>
        <p v-if="incoming" class="notice">刷新保留了草稿与原并发版本。服务端版本 {{incoming.version}}；保存可能产生409，请手动合并或明确重载。<button :disabled="busy" @click="reload">明确重载参考档案</button></p>
        <form class="grid" @submit.prevent="run(save)"><fieldset class="grid" :disabled="busy">
          <label class="field">参考用途<select v-model="draft.kind"><option value="audition">试听参考</option><option value="zero_shot">零样本参考</option><option value="training">训练资料（仅登记）</option></select></label>
          <label class="field">关联声线 ID（可留空）<input v-model.number="profileID" type="number" min="1"/></label>
          <label class="field">参考语言<input v-model="draft.language" maxlength="40"/></label><label class="field">人工参考文本<textarea v-model="draft.reference_text" maxlength="20000" rows="4"/></label>
          <label class="field">参考来源<input v-model="draft.source" maxlength="2000"/></label><label class="field">参考许可与使用范围<textarea v-model="draft.license" maxlength="20000" rows="3"/></label>
          <label class="row"><input v-model="draft.declaration.speaker_authorized" type="checkbox"/>我有权使用此音频及其中涉及的声音</label>
          <label class="row"><input v-model="draft.declaration.allow_zero_shot" type="checkbox"/>授权范围包含零样本参考用途</label><label class="row"><input v-model="draft.declaration.allow_training" type="checkbox"/>授权范围包含训练用途（当前不执行）</label>
          <label class="field">用途声明依据<textarea v-model="draft.declaration.statement" maxlength="2000" rows="2"/></label><label class="field">参考档案备注<textarea v-model="draft.notes" maxlength="5000" rows="2"/></label>
          <button class="primary">保存参考档案与新版本</button>
        </fieldset></form>
        <div class="row"><button :disabled="busy" @click="run(refresh)">刷新参考档案（保留草稿）</button><button :disabled="busy" @click="run(listen)">打开参考试听</button><RouterLink :to="'/assets?open='+current.asset_ref.id">素材与标签</RouterLink></div>
        <AudioPlayer v-if="sample" :key="sample.id+'-'+sample.sha256" :asset="sample"/>
        <label class="row"><input v-model="analysisAck" type="checkbox" :disabled="busy"/>同意在本机只读检查此音频，报告另存于Front，不发送到服务</label><button :disabled="busy||!analysisAck||isDirty()||active()" @click="run(inspect)">本机 PCM 技术检查</button>
        <small>最多64MiB完整PCM WAV；只测技术数据，不转码/降噪/改原件。PCM16近满幅采样是削波风险提示，不代表确定失真；技术检查不验证人声质量或使用权。</small>
        <JobProgress v-if="job" :job="job"/><p v-if="job?.result?.error_code" class="notice">{{codes[job.result.error_code]||job.result.error_code}}</p>
        <div v-if="report?.pcm" class="notice grid"><b>已保存技术报告 · {{report.analyzed_at}}</b><span>{{report.pcm.duration_seconds}} 秒 · {{report.pcm.sample_rate}} Hz · {{report.pcm.channels}}声道 / {{report.pcm.sample_width*8}}bit</span><span v-if="report.pcm.level_measured">峰值 {{report.pcm.peak_dbfs??'静音'}} dBFS · RMS {{report.pcm.rms_dbfs??'静音'}} dBFS · 近满幅 {{percentage(report.pcm.near_full_scale_samples_ratio)}} · 近零采样 {{percentage(report.pcm.near_zero_samples_ratio)}}</span><span v-else>此位深未作音量/静音风险判断。</span><p v-if="report.pcm.silent">整轨为零采样静音；不会自动创建任何克隆或训练任务。</p><p v-if="report.reference_exceeds_front_tts_30s">超过Front当前单次参考30秒限额；原件保持，后续切片须另存。</p><small>未评定语音质量/说话人/权利；不是LUFS分析。</small></div>
        <small v-if="current.version">以下是整个素材的历史，包含标签、备注和文件引用；恢复会追加整份素材版本。请先审核差异，不能只回退参考字段。</small>
        <VersionPanel v-if="current.version" :key="current.asset_ref.id+'-'+current.version" kind="asset" :entity-id="current.asset_ref.id" @restored="run(refresh)"/>
      </section><div v-else class="card empty">从素材库登记音频；不会复制原始文件或建立另一套播放器。</div>
    </div>
    <AssetPicker v-if="picker" @close="picker=false" @pick="choose"/>
  </div>
</template>
<style scoped>.references,.grid,.row,.row span,.field{min-width:0}.workspace{display:grid;grid-template-columns:minmax(220px,300px) minmax(0,1fr);gap:16px;align-items:start}.workspace>aside{min-width:0;grid-template-columns:minmax(0,1fr)}.workspace form.row input{width:100%;flex:1}fieldset{border:0;padding:0;min-width:0}button,p,small,h2,b{overflow-wrap:anywhere}button{max-width:100%;min-width:0;white-space:normal}input,textarea,select{max-width:100%;min-width:0}input[type=checkbox]{width:auto;flex-shrink:0}@media(max-width:800px){.workspace{grid-template-columns:minmax(0,1fr)}}</style>
