<script setup>
import {defineAsyncComponent,onBeforeUnmount,onMounted,ref,watch} from 'vue'
import {api} from '../api'
import JobProgress from '../components/JobProgress.vue'
const AssetPicker=defineAsyncComponent(()=>import('../components/AssetPicker.vue'))
const props=defineProps({project:Object,segment:Object,dirty:Boolean}),emit=defineEmits(['changed','refreshed'])
const caps=ref(null),configuration=ref(null),error=ref(''),busy=ref(false),picker=ref(false),reference=ref(null),referenceTitle=ref('')
const text=ref(''),language=ref(''),source=ref(''),network=ref(false),rights=ref(false),modelAck=ref(false),modelRights=ref(false)
const seed=ref(-1),topK=ref(''),topP=ref(''),temperature=ref(''),split=ref(''),preview=ref(null),current=ref(null),job=ref(null),health=ref(null)
let disposed=false,timer=null,epoch=0
const base=()=>`/api/voice/projects/${props.project.id}/segments/${props.segment.id}/local-requests`
const token=()=>({project_uid:props.project.uid,expected_project_version:props.project.version})
const active=()=>['queued','running'].includes(current.value?.status)||['queued','running'].includes(job.value?.status)||['queued','running'].includes(health.value?.status)
function schedule(){clearTimeout(timer);if(!disposed&&active())timer=setTimeout(()=>{if(busy.value){schedule();return}run(poll)},1500)}
async function run(fn){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){if(!disposed)error.value=e.message}finally{if(!disposed){busy.value=false;schedule()}}}
async function pick(asset){if(asset.kind!=='audio')throw new Error('请选择音频素材');const row=await api.get(`/api/assets/${asset.id}`);if(disposed)return;if(!row.sha256)throw new Error('参考音频缺少Hash，请先导入真实WAV文件');reference.value={id:row.id,identity:row.created_at.replace(/Z$|\+00:00$/,''),sha256:row.sha256};referenceTitle.value=row.title;rights.value=false;source.value='';picker.value=false}
function request(){return {...token(),fingerprint:props.segment.fingerprint,idempotency_key:crypto.randomUUID().replaceAll('-',''),reference:reference.value,
  reference_text:text.value,reference_language:language.value,rights_source:source.value,seed:Number(seed.value),
  parameters:{...(topK.value!==''?{top_k:Number(topK.value)}:{}),...(topP.value!==''?{top_p:Number(topP.value)}:{}),...(temperature.value!==''?{temperature:Number(temperature.value)}:{}),...(split.value?{text_split_method:split.value}:{})},
  rights_authorized:rights.value,confirm_local_request:network.value,confirm_loaded_model_unverified:modelAck.value,confirm_model_rights:modelRights.value}}
async function inspect(){const body=request(),key=epoch;const value=await api.post(base()+'/preview',body);if(!disposed&&epoch===key)preview.value={value,body}}
async function create(){const body={...preview.value.body};const result=await api.post(base(),body);if(disposed)return;preview.value=null;current.value=result.render;emit('changed',result.project);emit('refreshed');await poll()}
async function poll(){
  if(current.value){const result=await api.get(base()+`/${current.value.id}`);if(disposed)return;const was=current.value.status;current.value=result.render;emit('changed',result.project);if(result.render.snapshot.job_id)job.value=await api.get('/api/jobs/'+result.render.snapshot.job_id);if(disposed)return;if(was!==current.value.status)emit('refreshed')}
  if(health.value){const value=await api.get('/api/jobs/'+health.value.id);if(!disposed)health.value=value}
}
async function cancel(){const result=await api.post(base()+`/${current.value.id}/cancel`,token());if(disposed)return;current.value=result.render;emit('changed',result.project);emit('refreshed');await poll()}
async function configure(){configuration.value=null;network.value=false;modelAck.value=false;modelRights.value=false;rights.value=false;if(!props.segment.profile_id)return;const profile=await api.get('/api/voice/profiles/'+props.segment.profile_id);if(disposed||!profile.model_id)return;const model=await api.get('/api/voice/models/'+profile.model_id);if(disposed||!model.provider_id)return;const provider=await api.get('/api/voice/providers/'+model.provider_id);if(!disposed)configuration.value={profile,model,provider}}
async function check(){const provider=configuration.value?.provider;if(!provider)throw new Error('请先在声线/模型档案关联引擎登记');const result=await api.post(`/api/voice/providers/${provider.id}/check-local`,{expected_uid:provider.uid,expected_version:provider.version,confirm_local_request:network.value});if(!disposed)health.value=result}
watch(()=>JSON.stringify([props.project?.version,props.segment?.fingerprint,reference.value,text.value,language.value,source.value,seed.value,topK.value,topP.value,temperature.value,split.value,network.value,rights.value,modelAck.value,modelRights.value]),()=>{epoch++;preview.value=null})
watch(()=>props.segment?.fingerprint,()=>{modelAck.value=false;modelRights.value=false;network.value=false;configuration.value=null})
onMounted(()=>run(async()=>{const value=await api.get('/api/voice/local-capabilities');if(!disposed){caps.value=value;await configure()}}))
onBeforeUnmount(()=>{disposed=true;epoch++;clearTimeout(timer)})
</script>
<template>
  <section class="grid local-tts">
    <p class="notice">只连接已登记的本机 GPT-SoVITS，不启动服务、不安装模型、不切换外部权重。此入口不能核实服务实际加载的模型；音质需人工试听。参考音频单独授权，声线的试听样本不会自动用于克隆。</p>
    <p v-if="error" class="notice" role="alert">{{error}}</p>
    <p v-if="caps&&!caps.enabled" class="notice">本机 TTS API 默认关闭。需在 Front 启动环境明确设置 FRONT_ENABLE_LOCAL_TTS=1 后重启自有实例；未启用时仍可管理档案、关联音频与对比。不要重启或修改其他软件。</p>
    <p v-if="dirty" class="notice">请先保存台词草稿；合成只使用已经保存的文本与参数。</p>
    <p v-if="configuration" class="small">声线 {{configuration.profile.title}} · 模型登记 {{configuration.model.title}} · 引擎 {{configuration.provider.title}} · {{configuration.provider.endpoint||'未设置地址'}}</p>
    <p v-else class="muted">尚无当前引擎配置；请先关联模型/引擎，或刷新配置后再确认调用。</p><button :disabled="busy" @click="run(configure)">刷新已登记配置（不连接引擎）</button>
    <form class="grid" @submit.prevent="run(inspect)">
      <fieldset class="grid" :disabled="busy||!caps?.enabled||dirty">
        <label class="row"><input v-model="network" type="checkbox"/>我确认调用此声线已配置的本机服务（不会启动或关闭它）</label>
        <button type="button" :disabled="!network||!configuration" @click="run(check)">检查已配置本机 API</button>
        <button type="button" @click="picker=true">选择有权使用的参考 WAV</button><p v-if="reference" class="small">{{referenceTitle}} · 素材 #{{reference.id}}</p>
        <label class="field">参考音频文字<textarea v-model="text" maxlength="20000" rows="3"/></label>
        <label class="field">参考音频语言<input v-model="language" maxlength="40" required placeholder="使用引擎实际支持的语言代码"/></label>
        <label class="field">参考音频来源与授权说明<textarea v-model="source" required maxlength="2000" rows="2"/></label>
        <label class="row"><input v-model="rights" type="checkbox" required/>我有权将此参考音频用于本次生成；这不是训练授权</label>
        <label class="row"><input v-model="modelRights" type="checkbox" required/>我已核对并有权在本次生成中使用所选引擎与模型</label>
        <label class="row"><input v-model="modelAck" type="checkbox" required/>我理解 Front 未核验外部实际加载的权重，API匹配不代表模型身份或音质通过</label>
        <label class="field">合成种子<input v-model.number="seed" type="number" required min="-1" max="4294967295" step="1"/></label>
        <details><summary>GPT-SoVITS 支持的可选参数</summary><div class="fields"><label class="field">top_k<input v-model.number="topK" type="number" min="1" max="100" step="1"/></label><label class="field">top_p<input v-model.number="topP" type="number" min="0.01" max="1" step="0.01"/></label><label class="field">temperature<input v-model.number="temperature" type="number" min="0.01" max="2" step="0.01"/></label><label class="field">分句策略<select v-model="split" aria-label="分句策略"><option value="">使用引擎默认</option><option value="cut0">cut0</option><option value="cut5">cut5</option></select></label></div></details>
        <button :disabled="!reference||!network||!rights||!modelAck||!modelRights||!configuration">预览本次合成请求（不调用引擎）</button>
      </fieldset>
    </form>
    <div v-if="preview" class="card grid"><b>确认已保存的单片段请求</b><small>合同 {{preview.value.contract}} · 引擎 #{{preview.value.provider.id}} · 模型登记 #{{preview.value.model.id}} · 参考素材 #{{preview.value.reference.id}}</small><p class="muted">提交后在有限队列复制校验短参考音，再调用同机 API。仅支持同一文件系统；不改原音频，参考暂存将在调用结束清理。没有实际模型或授权声音时请停止在此。</p><button :disabled="busy||dirty" @click="run(create)">确认排队本机 TTS</button></div>
    <JobProgress v-if="health" :job="health"/><p v-if="health?.status==='done'" class="notice">{{health.result.contract_matches?'API字段匹配；实际权重、版本与音质仍未核验':'API字段不匹配，不执行合成'}}</p>
    <JobProgress v-if="job" :job="job"/>
    <div v-if="current" class="card grid"><b>本次请求：{{current.status}}</b><p v-if="current.snapshot.error_code||current.execution_issue" role="alert">{{current.snapshot.error_code||current.execution_issue}}</p><p>结果进入上方候选历史，需手动试听与采纳；失败后重新预览会使用新请求键，重复提交同一请求不会重放。</p><div class="row"><button :disabled="busy" @click="run(poll)">刷新本次请求</button><button v-if="['queued','running'].includes(current.status)" :disabled="busy" @click="run(cancel)">取消本次客户端请求</button></div></div>
    <small>取消仅停止本次客户端任务，最长需等待当前网络读取超时；不能保证外部 GPU 推理立即停止，不调用服务关闭接口。离开页面只清理轮询，已提交任务保留。</small>
    <AssetPicker v-if="picker" @close="picker=false" @pick="asset=>run(()=>pick(asset))"/>
  </section>
</template>
<style scoped>.local-tts{min-width:0;overflow-wrap:anywhere}fieldset{min-width:0;padding:0;border:0}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}input,textarea,select{max-width:100%;min-width:0}.row input[type=checkbox]{flex-shrink:0}</style>
