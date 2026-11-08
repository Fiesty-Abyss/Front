<script setup>
import { defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import {onBeforeRouteLeave} from 'vue-router'
import { api } from '../api'
import VersionPanel from '../components/VersionPanel.vue'
const AssetPicker = defineAsyncComponent(() => import('../components/AssetPicker.vue'))
const AudioPlayer = defineAsyncComponent(() => import('../viewers/AudioPlayer.vue'))
const VoiceProjects = defineAsyncComponent(() => import('./VoiceProjects.vue'))
const VoiceReferenceAssets=defineAsyncComponent(()=>import('./VoiceReferenceAssets.vue'))
const referenceMode=ref(false),referencesRef=ref(null),savedMetadata=ref('')
const projectMode = ref(false),projectsRef=ref(null)
const metadataDirty=()=>Boolean(draft.value)&&JSON.stringify(draft.value)!==savedMetadata.value
const leaveMetadata=()=>projectMode.value||referenceMode.value||!metadataDirty()||window.confirm('声线/模型/引擎资料尚未保存，确认放弃草稿？')
const leaveReferences=()=>!referenceMode.value||!referencesRef.value||referencesRef.value.canLeave()
async function leaveProjects(key){if(!leaveReferences()||!leaveMetadata()||(projectMode.value&&projectsRef.value&&!projectsRef.value.canLeave()))return;referenceMode.value=false;projectMode.value=false;await run(()=>changeTab(key))}
function enterProjects(){if(!leaveReferences()||!leaveMetadata())return;referenceMode.value=false;projectMode.value=true;sample.value=null;picker.value=false}
function enterReferences(){if(referenceMode.value)return;if(!leaveMetadata()||(projectMode.value&&projectsRef.value&&!projectsRef.value.canLeave()))return;projectMode.value=false;referenceMode.value=true;sample.value=null;picker.value=false}
const tab = ref('profiles'), rows = ref([]), total = ref(0), offset = ref(0), q = ref(''), error = ref(''), busy = ref(false)
const draft = ref(null), current = ref(null), picker = ref(false), sample = ref(null), diagnose = ref(null)
let disposed = false, sequence = 0
const labels = { profiles: '声线', models: '模型登记', providers: '引擎登记' }
const kind = () => ({profiles:'voice_profile',models:'voice_model',providers:'voice_provider'}[tab.value])
const base = () => `/api/voice/${tab.value}`
function defaults() {
  const common = { title: '', notes: '' }
  if (tab.value === 'profiles') return { ...common, model_id:null, character_id:null, oc_id:null, sample_ref:{}, voice_key:'', language:'', source:'', license:'', favorite:false, stars:0, preference:0, tag_ids:[] }
  if (tab.value === 'models') return { ...common, provider_id:null, file_path:'', model_version:'', source:'', license:'' }
  return { ...common, engine:'unconfigured', endpoint:'', credential_id:null }
}
async function run(fn) { if (busy.value) return; busy.value = true; error.value = ''; try { await fn() } catch(e) { if(!disposed) error.value=e.message } finally { if(!disposed) busy.value=false } }
async function load() {
  const n = ++sequence, data = await api.get(base(), {q:q.value, offset:offset.value, limit:30})
  if (!disposed && n === sequence) { rows.value = data.items; total.value = data.total }
}
function adopt(row) {
  current.value = row; const value = defaults()
  for (const key of Object.keys(value)) value[key] = row[key] ?? value[key]
  draft.value = value; savedMetadata.value=JSON.stringify(value);sample.value = null; diagnose.value = null
}
async function open(id) { if(!leaveMetadata())return;const row = await api.get(`${base()}/${id}`); if(!disposed) adopt(row) }
async function changeTab(value) { tab.value=value; offset.value=0; q.value=''; draft.value=null; current.value=null; sample.value=null; picker.value=false; await load() }
function create() { if(!leaveMetadata())return;current.value=null; draft.value=defaults();savedMetadata.value=JSON.stringify(draft.value); sample.value=null; diagnose.value=null }
async function save() {
  const row = current.value ? await api.put(`${base()}/${current.value.id}`, {...draft.value, expected_uid:current.value.uid, expected_version:current.value.version}) : await api.post(base(), draft.value)
  if(!disposed) { adopt(row); await load() }
}
async function pick(asset) {
  if (asset.kind !== 'audio') { error.value='请选择音频素材'; return }
  const row = await api.get(`/api/assets/${asset.id}`)
  if(disposed) return
  draft.value.sample_ref = {id:row.id, identity:row.created_at.replace(/Z$|\+00:00$/, ''), sha256:row.sha256}
  // Python serializes six fractional digits; retain the API's timestamp verbatim.
  picker.value=false; sample.value=null
}
async function listen() {
  const row=await api.get(`/api/assets/${draft.value.sample_ref.id}`)
  const ref=draft.value.sample_ref
  if(row.kind!=='audio' || row.created_at.replace(/Z$|\+00:00$/, '')!==ref.identity || row.sha256!==ref.sha256) throw new Error('试听文件已变化，请重新选择并保存')
  if(!disposed) sample.value=row
}
async function checkPath() { diagnose.value = await api.post(`${base()}/${current.value.id}/diagnose`, {}) }
async function restored() { await open(current.value.id); await load() }
function unload(event){if(!projectMode.value&&!referenceMode.value&&metadataDirty()){event.preventDefault();event.returnValue=''}}
onBeforeRouteLeave(()=>projectMode.value||referenceMode.value?true:!busy.value&&leaveMetadata())
onMounted(() => {window.addEventListener('beforeunload',unload);run(load)})
onBeforeUnmount(() => {disposed=true; sequence++; sample.value=null;window.removeEventListener('beforeunload',unload)})
</script>
<template>
  <div class="voice grid">
    <header><div class="eyebrow">CREATION · VOICE</div><h1>AI Voice Studio</h1><p class="muted">声线、模型、授权与配音工程。引擎按需连接，不会自动启动服务或下载模型。</p></header>
    <p v-if="error" class="notice" role="alert">{{ error }}</p>
    <nav class="row" aria-label="Voice 工作区"><button v-for="(label,key) in labels" :key="key" :disabled="busy" :aria-pressed="!projectMode&&!referenceMode&&tab===key" @click="leaveProjects(key)">{{ label }}</button><button :disabled="busy" :aria-pressed="projectMode" @click="enterProjects">配音工程</button><button :disabled="busy" :aria-pressed="referenceMode" @click="enterReferences">参考音频</button><RouterLink to="/audio">音声收藏</RouterLink><RouterLink to="/characters">角色百科</RouterLink><RouterLink to="/oc">OC Studio</RouterLink></nav>
    <VoiceProjects v-if="projectMode" ref="projectsRef"/>
    <VoiceReferenceAssets v-else-if="referenceMode" ref="referencesRef"/>
    <div v-else class="workspace">
      <aside class="card grid">
        <form class="row" @submit.prevent="offset=0; run(load)"><input v-model="q" aria-label="搜索名称" maxlength="200" placeholder="搜索名称"/><button :disabled="busy">搜索</button></form>
        <button :disabled="busy" @click="create">新建{{ labels[tab] }}</button>
        <p v-if="!rows.length" class="muted">暂无{{ labels[tab] }}。无需配置引擎即可登记资料和试听已有音频。</p>
        <button v-for="r in rows" :key="r.uid" :disabled="busy" class="item" :aria-pressed="current?.uid===r.uid" @click="run(()=>open(r.id))">{{r.favorite?'♥ ':''}}{{ r.title }}<small class="muted"> #{{r.id}}</small></button>
        <div class="row"><button :disabled="busy || !offset" @click="offset-=30; run(load)">上一页</button><small>{{total}} 项</small><button :disabled="busy || offset+30>=total" @click="offset+=30; run(load)">下一页</button></div>
      </aside>
      <section v-if="draft" class="card grid editor">
        <form class="grid" @submit.prevent="run(save)">
          <label class="field">名称<input v-model="draft.title" required maxlength="200" /></label>
          <template v-if="tab==='providers'">
            <label class="field">引擎类型<select v-model="draft.engine"><option value="unconfigured">未配置</option><option value="gpt_sovits">GPT-SoVITS（需显式检查）</option><option value="custom">其他引擎（尚无合成适配）</option></select></label>
            <label class="field">服务地址<input v-model="draft.endpoint" placeholder="仅登记，不发送请求" maxlength="2000"/></label>
            <label class="field">已有 AI 配置 ID（仅引用凭据）<input v-model.number="draft.credential_id" type="number" min="1" @change="draft.credential_id ||= null"/></label>
            <p class="muted">聊天 API 不代表支持语音合成；当前能力尚未验证。请勿在名称、地址或备注填写 API Key。</p>
          </template>
          <template v-if="tab==='models'">
            <label class="field">引擎登记 ID<input v-model.number="draft.provider_id" type="number" min="1" @change="draft.provider_id ||= null"/></label>
            <label class="field">模型原始路径<input v-model="draft.file_path" maxlength="2000" placeholder="只存路径，不复制或加载权重"/></label>
            <label class="field">模型版本<input v-model="draft.model_version" maxlength="200"/></label>
          </template>
          <template v-if="tab==='profiles'">
            <div class="fields"><label class="field">模型登记 ID<input v-model.number="draft.model_id" type="number" min="1" @change="draft.model_id ||= null"/></label><label class="field">引擎声线标识<input v-model="draft.voice_key" maxlength="200"/></label><label class="field">语言<input v-model="draft.language" maxlength="40"/></label></div>
            <div class="fields"><label class="field">角色 ID（可留空）<input v-model.number="draft.character_id" type="number" min="1" @change="draft.character_id ||= null"/></label><label class="field">或 OC ID<input v-model.number="draft.oc_id" type="number" min="1" @change="draft.oc_id ||= null"/></label></div>
            <small class="muted">独立声线无需世界观。绑定沿用角色的世界观／作品 ID；两种绑定不可同时填写。</small>
            <div class="fields"><label class="row"><input v-model="draft.favorite" type="checkbox"/>收藏</label><label class="field">星级<input v-model.number="draft.stars" type="number" min="0" max="5"/></label><label class="field">喜爱度<input v-model.number="draft.preference" type="number" min="0" max="100"/></label></div>
            <label class="field">标签 ID（逗号分隔）<input :value="draft.tag_ids.join(',')" inputmode="numeric" @change="draft.tag_ids=$event.target.value.split(',').filter(x=>x.trim()).map(Number)"/></label>
            <div class="row"><button type="button" @click="picker=true">选择素材库试听样本</button><span v-if="draft.sample_ref.id">素材 #{{draft.sample_ref.id}}</span><button v-if="draft.sample_ref.id" type="button" @click="run(listen)">打开试听</button><button v-if="draft.sample_ref.id" type="button" @click="draft.sample_ref={};sample=null">解除样本关联</button></div>
            <p v-for="issue in current?.issues||[]" :key="issue" class="notice">{{issue}}</p>
          </template>
          <template v-if="tab!=='providers'"><label class="field">来源<input v-model="draft.source" maxlength="2000"/></label><label class="field">许可与使用范围<textarea v-model="draft.license" rows="3" maxlength="20000" placeholder="如实记录授权；登记本身不授予声音克隆或发布权"/></label></template>
          <label class="field">个人备注<textarea v-model="draft.notes" rows="4" maxlength="20000"/></label>
          <button class="primary" :disabled="busy">{{busy?'处理中…':'保存资料与新版本'}}</button>
        </form>
        <div v-if="tab==='models' && current" class="grid"><button :disabled="busy" @click="run(checkPath)">检查已保存路径（只读）</button><p v-if="diagnose" class="notice">{{diagnose.status}} · 运行时兼容性未验证<span v-if="diagnose.size!=null"> · {{diagnose.size}} bytes</span></p></div>
        <AudioPlayer v-if="sample" :key="sample.id+'-'+sample.sha256" :asset="sample"/>
        <VersionPanel v-if="current" :key="kind()+'-'+current.uid+'-'+current.version" :kind="kind()" :entity-id="current.id" @restored="run(restored)"/>
      </section>
      <div v-else class="card empty">选择或新建声线档案；配音工程可整理台词、关联手动音频并导出。档案与手动音频可离线使用；合成需单独明确启用并核对服务。</div>
    </div>
    <AssetPicker v-if="picker" @close="picker=false" @pick="asset=>run(()=>pick(asset))"/>
  </div>
</template>
<style scoped>
.voice{min-width:0}.workspace{display:grid;grid-template-columns:minmax(240px,300px) minmax(0,1fr);gap:16px;align-items:start}.workspace aside{min-width:0}.item{text-align:left;overflow-wrap:anywhere}.editor{min-width:0}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}input,textarea,select{max-width:100%;min-width:0}.workspace form.row input{width:100%;flex:1}@media(max-width:800px){.workspace{grid-template-columns:minmax(0,1fr)}}
</style>
