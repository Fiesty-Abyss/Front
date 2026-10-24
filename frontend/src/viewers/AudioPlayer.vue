<script setup>
import {computed,onMounted,onBeforeUnmount,ref} from 'vue'
import {Play,Pause,Volume2,VolumeX,Download} from 'lucide-vue-next'
import {api,fileUrl,hasThumb,thumb} from '../api'
import KindIcon from '../components/KindIcon.vue'
const props=defineProps({asset:{type:Object,required:true},remember:Boolean,autoplay:Boolean}),emit=defineEmits(['ended'])
const el=ref(null),playing=ref(false),t=ref(0),dur=ref(props.asset.meta?.file?.duration||0),muted=ref(false),rate=ref(1),loop=ref(false),state=ref(null),notes=ref(''),bookmarkLabel=ref(''),error=ref(''),cue=ref(''),subtitle=ref(''),subtitleRows=ref([]),subtitleQ=ref(''),subtitleId=ref('')
const f=computed(()=>props.asset.meta?.file||{}),fmt=s=>{s=Math.max(0,Math.floor(s||0));return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`}
const saving=ref(false)
let disposed=false,lastSaved=0,pending={}
async function load(){if(props.remember){state.value=await api.get(`/api/audio/tracks/${props.asset.id}/state`);notes.value=state.value.notes;rate.value=state.value.rate;loop.value=state.value.loop;if(el.value?.readyState>=1&&!state.value.source_changed&&state.value.position<dur.value)el.value.currentTime=state.value.position}}
onMounted(()=>load().catch(e=>error.value=e.message))
async function play(){try{await el.value.play();error.value=''}catch{error.value='浏览器未能播放：请检查格式/编码、原文件是否移动，或再次点击播放。'}}
function toggle(){el.value.paused?play():el.value.pause()}
function seek(event){el.value.currentTime=Number(event.target.value)}
async function persist(changes={}){if(!props.remember||!state.value||disposed)return;Object.assign(pending,changes);if(saving.value)return;saving.value=true;try{while(Object.keys(pending).length&&!disposed){const next=pending;pending={};const s=state.value;const value=await api.put(`/api/audio/tracks/${props.asset.id}/state`,{asset_identity:s.asset_identity,sha256:s.sha256,expected_revision:s.revision,...next});if(!disposed)state.value=value}}catch(e){if(!disposed)error.value=e.message;pending={}}finally{saving.value=false}}
function updateTime(event){t.value=event.target.currentTime;if(props.remember&&Date.now()-lastSaved>5000&&!state.value?.source_changed){lastSaved=Date.now();persist({position:t.value})}}
function pause(){playing.value=false;if(!disposed&&!state.value?.source_changed)persist({position:el.value.currentTime})}
function metadata(){dur.value=Number.isFinite(el.value.duration)?el.value.duration:dur.value;if(state.value&&!state.value.source_changed&&state.value.position<dur.value)el.value.currentTime=state.value.position;if(props.autoplay)play()}
async function bookmark(){if(!state.value||saving.value)return;await persist({bookmarks:[...state.value.bookmarks,{id:crypto.randomUUID(),position:t.value,label:bookmarkLabel.value||`书签 ${fmt(t.value)}`} ]});bookmarkLabel.value=''}
async function chooseSubtitles(){try{subtitleRows.value=(await api.get('/api/assets',{kind:'code',q:subtitleQ.value,limit:50})).items.filter(a=>/\.(lrc|srt|vtt)$/i.test(a.original_name||''))}catch(e){error.value=e.message}}
async function attachSubtitle(){if(saving.value)return;await persist({subtitle_asset_ids:[...state.value.subtitles.map(s=>s.id),Number(subtitleId.value)]});if(state.value.subtitles.some(s=>s.id===Number(subtitleId.value)))subtitle.value=String(subtitleId.value)}
function trackReady(){const track=el.value?.textTracks?.[0];if(track)track.mode='hidden'}
function cueChange(event){cue.value=[...(event.target.track.activeCues||[])].map(c=>c.text).join(' / ')}
onBeforeUnmount(()=>{if(props.remember&&state.value&&!state.value.source_changed){const s=state.value;const body={asset_identity:s.asset_identity,sha256:s.sha256,expected_revision:s.revision,position:el.value?.currentTime||t.value};if(!saving.value)fetch(`/api/audio/tracks/${props.asset.id}/state`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),keepalive:true}).catch(()=>{})}disposed=true;pending={};if(el.value){el.value.pause();el.value.removeAttribute('src');el.value.load()}})
</script>
<template><div class="grid">
<div class="ap"><div class="cover"><img v-if="hasThumb(asset)" :src="thumb(asset.id,asset.updated_at)" alt="音轨封面"/><KindIcon v-else :asset="asset" :size="44"/></div><div class="body"><div class="eyebrow">{{[f.genre,f.year].filter(Boolean).join(' · ')||'音频'}}</div><h3>{{f.title||asset.title}}</h3><p class="muted">{{[f.artist,f.album].filter(Boolean).join(' — ')||'艺术家与专辑未标注'}}</p><small>{{f.format||f.ext?.toUpperCase()}} · {{f.samplerate?f.samplerate+' Hz':'采样率未识别'}} · {{f.bitrate?f.bitrate+' kbps':'码率未识别'}} · {{f.channels?f.channels+'声道':''}} · {{f.codec||'编码名称未提供'}}</small><div class="ctl"><button class="primary play" :aria-label="playing?'暂停':'播放'" @click="toggle"><component :is="playing?Pause:Play" :size="18"/></button><span class="mono small">{{fmt(t)}}</span><input class="seek" aria-label="播放位置" type="range" min="0" :max="dur||0" step="0.1" :value="t" :style="{'--p':dur?t/dur*100+'%':'0%'}" @input="seek"/><span class="mono small">{{fmt(dur)}}</span><button class="ghost iconbtn" :aria-label="muted?'取消静音':'静音'" @click="muted=!muted"><component :is="muted?VolumeX:Volume2" :size="16"/></button><a class="btn" :href="fileUrl(asset.id)" title="下载原文件"><Download :size="16"/></a></div><div class="row"><label>倍速 <select v-model.number="rate" aria-label="播放倍速" @change="persist({rate})"><option v-for="r in [.5,.75,1,1.25,1.5,2,3]" :key="r" :value="r">{{r}}×</option></select></label><label class="row"><input v-model="loop" type="checkbox" @change="persist({loop})"/>单曲循环</label></div><p v-if="cue" class="notice" aria-live="off">{{cue}}</p></div>
<audio ref="el" :src="fileUrl(asset.id,true)" preload="metadata" :muted="muted" :playbackRate="rate" :loop="loop" @play="playing=true" @pause="pause" @timeupdate="updateTime" @loadedmetadata="metadata" @ended="playing=false;emit('ended')" @error="error='当前浏览器无法解码或文件失效，请查看素材格式；本轮不自动转码，不覆盖原件。'"><track v-if="subtitle" :key="subtitle" kind="subtitles" :src="`/api/audio/tracks/${asset.id}/subtitles/${subtitle}`" srclang="zh" label="关联字幕" default @load="trackReady" @cuechange="cueChange"/></audio></div>
<p v-if="error" class="notice" role="alert">{{error}}</p><p v-if="f.error" class="notice">元数据解析未完成：{{f.error}}。保留原文件，不代表完整编码支持。</p>
<template v-if="remember&&state"><p v-if="state.source_changed" class="notice">音频内容已有新版，旧进度保留。<button @click="persist({confirm_source_change:true,position:0})">确认开始新版续听</button></p><div class="row"><span class="small muted">{{saving?'保存进度…':'进度每5秒/暂停时保存'}} · 版本{{state.revision}}</span><button :disabled="saving" @click="load">重新加载续听资料</button></div><label class="field">音轨个人笔记<textarea v-model="notes" maxlength="30000" @blur="persist({notes})"/></label><div class="row"><input v-model="bookmarkLabel" aria-label="时间戳书签名称" maxlength="500" placeholder="书签说明"/><button :disabled="saving||state.source_changed" @click="bookmark">在{{fmt(t)}}添加书签</button></div><div class="row"><span v-for="b in state.bookmarks" :key="b.id" class="chip"><button :disabled="b.sha256!==state.sha256" @click="el.currentTime=b.position">{{fmt(b.position)}} · {{b.label}}{{b.sha256!==state.sha256?'（旧文件）':''}}</button><button :aria-label="'移除书签 '+b.label" @click="persist({bookmarks:state.bookmarks.filter(x=>x.id!==b.id)})">×</button></span></div><details><summary>关联歌词 / 字幕</summary><div class="grid"><form class="row" @submit.prevent="chooseSubtitles"><input v-model="subtitleQ" aria-label="搜索字幕素材" placeholder="查找已导入LRC/SRT/VTT"/><button>搜索字幕</button></form><label class="field">可用字幕<select v-model="subtitleId"><option value="">选择已导入字幕</option><option v-for="s in subtitleRows" :key="s.id" :value="s.id">{{s.title}}</option></select></label><button :disabled="saving||!subtitleId" @click="attachSubtitle">关联该字幕</button><label class="field">播放字幕<select v-model="subtitle"><option value="">关闭</option><option v-for="s in state.subtitles" :key="s.id" :value="s.id">{{s.title}}</option></select></label><button @click="persist({subtitle_asset_ids:[]});subtitle=''">移除字幕关联（保留文件）</button></div></details></template>
</div></template>
<style scoped>
.ap { display: grid; grid-template-columns: 168px 1fr; gap: 22px; align-items: center; padding: 18px; border-radius: var(--radius-lg);
  background: radial-gradient(120% 140% at 0% 0%, var(--accent-soft), transparent 60%), var(--panel2); border: 1px solid var(--line); }
.cover { width: 168px; aspect-ratio: 1; border-radius: 14px; overflow: hidden; box-shadow: 0 18px 40px -18px rgba(0, 0, 0, .7); }
.cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
h3 { margin: 4px 0 2px; font-size: 20px; }
.ctl { display: flex; align-items: center; gap: 10px; margin-top: 18px; }
.play { width: 44px; height: 44px; border-radius: 50%; padding: 0; justify-content: center; flex: none; }
.seek { flex: 1; -webkit-appearance: none; appearance: none; height: 4px; border-radius: 4px; padding: 0; border: 0;
  background: linear-gradient(to right, var(--accent) var(--p), var(--line-strong) var(--p)); }
.seek::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; border-radius: 50%; background: var(--text); }
</style>

<style scoped>.body{min-width:0}.row input[type=checkbox]{width:auto}.ctl{flex-wrap:wrap}.seek{min-width:80px}@media(max-width:700px){.ap{grid-template-columns:1fr;padding:12px;gap:10px}.cover{width:90px}h3{font-size:17px}.ctl{gap:6px}}
</style>
