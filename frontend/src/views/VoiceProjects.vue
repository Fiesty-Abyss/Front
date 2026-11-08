<script setup>
import {computed,defineAsyncComponent,onBeforeUnmount,onMounted,ref} from 'vue'
import {onBeforeRouteLeave} from 'vue-router'
import {draftFromSegment,emptyVoiceDraft,draftChanged} from '../voiceDrafts'
import {api} from '../api'
import VersionPanel from '../components/VersionPanel.vue'
const synthesisUid=ref(null)
const VoiceSynthesisPanel=defineAsyncComponent(()=>import('./VoiceSynthesisPanel.vue'))
const VoiceExportPanel=defineAsyncComponent(()=>import('./VoiceExportPanel.vue'))
const VoiceBookPanel=defineAsyncComponent(()=>import('./VoiceBookPanel.vue'))
const AssetPicker=defineAsyncComponent(()=>import('../components/AssetPicker.vue'))
const AudioPlayer=defineAsyncComponent(()=>import('../viewers/AudioPlayer.vue'))
const projects=ref([]),project=ref(null),segments=ref([]),total=ref(0),offset=ref(0),archived=ref(false),projectOffset=ref(0),projectTotal=ref(0)
const title=ref(''),world=ref(null),search=ref(''),error=ref(''),busy=ref(false),selected=ref(null),draft=ref(null),renders=ref([]),renderTotal=ref(0),renderOffset=ref(0),splitAt=ref(1),picker=ref(false),audio=ref(null)
const voiceSearch=ref(''),voiceChoices=ref([]),savedDraft=ref(null)
const dirty=computed(()=>draftChanged(draft.value,savedDraft.value))
function canLeave(){return !dirty.value||window.confirm('当前台词有未保存修改，确定放弃草稿？')}
defineExpose({canLeave})
onBeforeRouteLeave(()=>canLeave())
function beforeUnload(event){if(dirty.value){event.preventDefault();event.returnValue=''}}
const renderLabels={candidate:'候选',accepted:'已采纳',queued:'排队',running:'处理中',error:'失败',interrupted:'服务中断',cancelled:'已取消'}
let disposed=false
const base=()=>`/api/voice/projects/${project.value.id}`
const segmentUrl=()=>`${base()}/segments/${selected.value.id}`
const token=()=>({project_uid:project.value.uid,expected_project_version:project.value.version})
async function run(fn){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){if(!disposed)error.value=e.message}finally{if(!disposed)busy.value=false}}
async function loadProjects(){const data=await api.get('/api/voice/projects',{q:search.value,limit:20,offset:projectOffset.value});if(!disposed){projects.value=data.items;projectTotal.value=data.total}}
async function findVoices(){const data=await api.get('/api/voice/profiles',{q:voiceSearch.value,limit:50});if(!disposed)voiceChoices.value=data.items}
async function loadSegments(){const data=await api.get(base()+'/segments',{limit:30,offset:offset.value,archived:archived.value});if(!disposed){project.value=data.project;segments.value=data.items;total.value=data.total}}
async function openProject(row,confirmed=false){if(!confirmed&&!canLeave())return; savedDraft.value=null;project.value=await api.get(`/api/voice/projects/${row.id}`);if(disposed)return;offset.value=0;archived.value=false;selected.value=null;draft.value=null;savedDraft.value=null;audio.value=null;await loadSegments()}
async function createProject(){if(!canLeave())return;const row=await api.post('/api/voice/projects',{title:title.value,world_id:world.value||null});if(disposed)return;title.value='';await openProject(row,true);await loadProjects()}
function adoptSegment(row){selected.value=row;draft.value=draftFromSegment(row);savedDraft.value={...draft.value};audio.value=null}
async function loadRenders(){const data=await api.get(segmentUrl()+'/renders',{limit:20,offset:renderOffset.value});if(!disposed){renders.value=data.items;renderTotal.value=data.total}}
async function openSegment(row,confirmed=false){if(!confirmed&&!canLeave())return;const value=await api.get(`${base()}/segments/${row.id}`);if(disposed)return;adoptSegment(value);renderOffset.value=0;await loadRenders()}
function newSegment(){if(!canLeave())return;selected.value=null;draft.value=emptyVoiceDraft();savedDraft.value={...draft.value};renders.value=[];audio.value=null}
async function save(){const body={...token(),...draft.value,expected_segment_version:selected.value?.version??null};const result=selected.value?await api.put(segmentUrl(),body):await api.post(base()+'/segments',body);if(disposed)return;project.value=result.project;adoptSegment(result.segment);await loadSegments();await loadRenders()}
async function structural(action,extra={}){if(dirty.value)throw new Error('请先保存台词修改，再进行拆分、合并或排序');const result=await api.post(segmentUrl()+'/'+action,{...token(),...extra});if(disposed)return;project.value=result.project;selected.value=null;draft.value=null;audio.value=null;await loadSegments()}
async function attach(asset){if(asset.kind!=='audio')throw new Error('请选择音频素材');const row=await api.get(`/api/assets/${asset.id}`);if(disposed)return;const ref={id:row.id,identity:row.created_at.replace(/Z$|\+00:00$/,''),sha256:row.sha256};const result=await api.post(segmentUrl()+'/renders',{...token(),audio_ref:ref,fingerprint:selected.value.fingerprint,note:'手动关联音频；非Front TTS生成'});if(disposed)return;project.value=result.project;picker.value=false;renderOffset.value=0;await loadRenders()}
async function accept(row){const result=await api.post(segmentUrl()+`/renders/${row.id}/accept`,token());if(disposed)return;project.value=result.project;await loadRenders()}
async function listen(row){const asset=await api.get(`/api/assets/${row.audio_ref.id}`);if(asset.created_at.replace(/Z$|\+00:00$/,'')!==row.audio_ref.identity||asset.sha256!==row.audio_ref.sha256)throw new Error('音频文件已变化，请重新选择');if(!disposed)audio.value=asset}
async function restored(){const keep=dirty.value;await loadSegments();if(selected.value){if(keep){await loadRenders();error.value='工程已刷新，未保存草稿及原版本已保留。请保存，或明确重新载入已保存版本。'}else await openSegment(selected.value,true)}}
async function reloadSaved(){if(!canLeave()||!selected.value)return;await openSegment(selected.value,true)}
async function changeArchive(){if(!canLeave())return;archived.value=!archived.value;offset.value=0;selected.value=null;draft.value=null;savedDraft.value=null;audio.value=null;await loadSegments()}
onMounted(()=>{window.addEventListener('beforeunload',beforeUnload);run(loadProjects)});onBeforeUnmount(()=>{window.removeEventListener('beforeunload',beforeUnload);disposed=true;audio.value=null})
</script>
<template>
  <section class="grid dialogue">
    <p class="notice">台词与音频候选管理。手动音频保持原样；语言与速度用于新引擎请求。本机TTS须明确启用并确认参考授权。</p>
    <p v-if="error" class="notice" role="alert">{{error}}</p>
    <VoiceBookPanel :key="project?.uid||'new'" :project="project" @created="row=>run(async()=>{await openProject(row);await loadProjects()})" @changed="row=>project=row" @reviewed="run(restored)"/>
    <div class="projects">
      <aside class="card grid">
        <form class="grid" @submit.prevent="projectOffset=0;run(loadProjects)"><label class="field">搜索工程<input v-model="search" maxlength="200"/></label><button :disabled="busy">搜索</button></form>
        <form class="grid" @submit.prevent="run(createProject)"><label class="field">新工程名称<input v-model="title" required maxlength="200"/></label><label class="field">世界观 ID（可留空）<input v-model.number="world" type="number" min="1"/></label><button :disabled="busy">创建配音工程</button></form>
        <p v-if="!projects.length" class="muted">暂无工程；可以创建独立工程或关联世界观。</p>
        <button v-for="p in projects" :key="p.uid" :disabled="busy" :aria-pressed="project?.uid===p.uid" @click="run(()=>openProject(p))">{{p.title}}</button>
        <div class="row"><button :disabled="busy||!projectOffset" @click="projectOffset-=20;run(loadProjects)">上页</button><small>{{projectTotal}} 个</small><button :disabled="busy||projectOffset+20>=projectTotal" @click="projectOffset+=20;run(loadProjects)">下页</button></div>
      </aside>
      <section v-if="project" class="grid">
        <header><h2>{{project.title}}</h2><p class="muted">世界观：{{project.world_id||'独立工程'}} · 版本 #{{project.version}}</p></header>
        <div class="row"><button :disabled="busy" @click="newSegment">新增台词</button><button :disabled="busy" @click="run(changeArchive)">{{archived?'返回有效片段':'查看拆分/合并前的保留片段'}}</button><button :disabled="busy" @click="run(restored)">刷新工程</button><button v-if="dirty&&selected" :disabled="busy" @click="run(reloadSaved)">重新载入已保存版本（放弃草稿）</button></div>
        <VoiceExportPanel :project="project" :segments="segments" :archived="archived"/>
        <div class="segments">
          <aside class="card grid">
            <p v-if="!segments.length" class="muted">{{archived?'暂无保留片段':'暂无台词。添加旁白或角色对白。'}}</p>
            <button v-for="s in segments" :key="s.uid" :disabled="busy" class="segment" :aria-pressed="selected?.uid===s.uid" @click="run(()=>openSegment(s))"><b>{{s.speaker||'旁白'}}</b><small>{{s.text||'空台词'}}{{s.issue?' · 关联异常':''}}</small></button>
            <div class="row"><button :disabled="busy||!offset" @click="offset-=30;run(loadSegments)">上一页</button><small>{{total}} 片段</small><button :disabled="busy||offset+30>=total" @click="offset+=30;run(loadSegments)">下一页</button></div>
          </aside>
          <div v-if="draft" class="card grid editor">
            <p v-if="selected?.archived" class="notice">此片段由拆分或合并保留，原文、历史及旧音频可查；编辑当前有效片段。</p>
            <p v-if="selected?.issue" class="notice">{{selected.issue}}</p>
            <p v-if="dirty" class="notice" role="status">当前台词有未保存修改；刷新保留草稿，拆分/合并/排序前请先保存。</p><form class="grid" @submit.prevent="run(save)">
              <div v-if="selected?.source?.book&&selected?.source?.suggestion" class="notice grid"><b>原文证据 · 第{{selected.source.book.chapter_index+1}}章 · 区间 {{selected.source.book.start}}–{{selected.source.book.end}}（Unicode字符）</b><p style="white-space:pre-wrap;overflow-wrap:anywhere">{{selected.source.suggestion.evidence}}</p><small>标点/姓名标签规则候选，未执行AI语义归因。朗读文本可独立修改，引用仍指向原文。</small><label class="row"><input v-model="draft.confirm_speaker" type="checkbox" :disabled="selected.archived"/>我已人工核对说话人</label></div>
              <div class="fields"><label class="field">人物/旁白<input v-model="draft.speaker" maxlength="200" :disabled="selected?.archived"/></label><label class="field">声线档案 ID<input v-model.number="draft.profile_id" type="number" min="1" :disabled="selected?.archived" @change="draft.profile_id ||= null"/></label></div>
              <div v-if="!selected?.archived" class="grid"><div class="row"><input v-model="voiceSearch" aria-label="搜索声线名称" maxlength="200" placeholder="查找已登记声线"/><button type="button" :disabled="busy" @click="run(findVoices)">查找声线</button></div><div class="row"><button v-for="voice in voiceChoices" :key="voice.uid" type="button" @click="draft.profile_id=voice.id">{{voice.title}} · #{{voice.id}}</button></div></div>
              <small class="muted">选择绑定角色/OC的声线；未设声线时仍可整理台词和手动音频。不同世界观的声线不会自动混用。</small>
              <label class="field">朗读台词<textarea v-model="draft.text" rows="8" maxlength="20000" :disabled="selected?.archived"/></label>
              <div class="fields"><label class="field">语言<input v-model="draft.language" maxlength="40" :disabled="selected?.archived"/></label><label class="field">期望语速<input v-model.number="draft.speed" type="number" min="0.25" max="4" step="0.05" :disabled="selected?.archived"/></label></div>
              <button class="primary" :disabled="busy||selected?.archived">保存台词版本</button>
            </form>
            <template v-if="selected&&!selected.archived"><div class="row"><button :disabled="busy" @click="run(()=>structural('move',{direction:-1}))">上移</button><button :disabled="busy" @click="run(()=>structural('move',{direction:1}))">下移</button><button :disabled="busy" @click="run(()=>structural('merge-next'))">与下一条合并</button></div><div class="row"><label class="field">拆分位置（已保存正文的字符数）<input v-model.number="splitAt" type="number" min="1" :max="Array.from(selected.text).length-1"/></label><button :disabled="busy" @click="run(()=>structural('split',{at:splitAt}))">拆分并保留原片段</button></div><small class="muted">排序/拆分/合并作用于已保存台词；合并会在两段之间加入换行。未保存的输入请先保存。</small></template>
            <template v-if="selected"><h3>音频候选</h3><button v-if="!selected.archived" :disabled="busy||!selected.fingerprint" @click="picker=true">关联已有音频（手动版本）</button><p v-if="!renders.length" class="muted">暂无音频。可手动关联；合成需单独配置并确认本机引擎。</p><div v-for="r in renders" :key="r.uid" class="card grid"><b>{{renderLabels[r.status]||r.status}} · {{r.origin==='manual'?'手动音频':r.origin==='mock'?'Mock测试音（非语音）':r.origin==='gpt_sovits'?'本机TTS API（权重/音质未核验）':r.origin}}</b><small>{{r.created_at}} · {{r.stale?'台词/声线基线已变化':'基线一致（生成参数见快照）'}} · {{r.audio_status}}</small><p>{{r.note}}</p><div class="row"><button :disabled="busy||r.audio_status!=='ok'" @click="run(()=>listen(r))">试听</button><button :disabled="busy||r.stale||r.audio_status!=='ok'||selected.archived" @click="run(()=>accept(r))">采纳此版本</button><RouterLink v-if="r.audio_ref" :to="'/assets?open='+r.audio_ref.id">素材档案</RouterLink></div><details><summary>台词与参数快照</summary><pre>{{JSON.stringify(r.snapshot,null,2)}}</pre></details></div><div class="row"><button :disabled="busy||!renderOffset" @click="renderOffset-=20;run(loadRenders)">候选上页</button><small>{{renderTotal}} 个版本</small><button :disabled="busy||renderOffset+20>=renderTotal" @click="renderOffset+=20;run(loadRenders)">候选下页</button></div></template>
            <details v-if="selected&&!selected.archived" :key="'synthesis-'+selected.uid" @toggle="synthesisUid=$event.target.open?selected.uid:null"><summary>本机 TTS · 显式授权与请求</summary><VoiceSynthesisPanel v-if="synthesisUid===selected.uid" :project="project" :segment="selected" :dirty="dirty" @changed="row=>project=row" @refreshed="run(restored)"/></details>
            <AudioPlayer v-if="audio" :key="audio.id+'-'+audio.sha256" :asset="audio"/>
            <VersionPanel v-if="selected" :key="selected.uid+'-'+selected.version" kind="voice_segment" :entity-id="selected.id" @restored="run(restored)"/>
          </div>
        </div>
        <details><summary>工程资料历史（台词分别版本化；不回退目录结构）</summary><VersionPanel :key="project.uid+'-'+project.version" kind="voice_project" :entity-id="project.id" @restored="run(restored)"/></details>
      </section>
      <p v-else class="card empty">选择或创建一个配音工程。</p>
    </div>
    <AssetPicker v-if="picker" @close="picker=false" @pick="asset=>run(()=>attach(asset))"/>
  </section>
</template>
<style scoped>
.dialogue,.editor{min-width:0}.projects{display:grid;grid-template-columns:minmax(210px,260px) minmax(0,1fr);gap:16px;align-items:start}.segments{display:grid;grid-template-columns:minmax(170px,230px) minmax(0,1fr);gap:12px;align-items:start}.segment{text-align:left;min-width:0;white-space:normal}.segment small{display:block;overflow-wrap:anywhere}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}input,textarea{min-width:0;max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:250px;overflow:auto}@media(max-width:1100px){.segments{grid-template-columns:minmax(0,1fr)}}@media(max-width:800px){.projects{grid-template-columns:minmax(0,1fr)}}
</style>
