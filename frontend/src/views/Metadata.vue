<script setup>
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
const VersionPanel = defineAsyncComponent(() => import('../components/VersionPanel.vue'))
const route = useRoute()
const kind=ref('book'),title=ref(''),author=ref(''),providers=ref([]),selectedProviders=ref([])
const error=ref(''),notice=ref(''),job=ref(null),results=ref(null),detail=ref(null),busy=ref(false)
const targetKind=ref(route.query.target==='galgame'?'galgame':'work'),targetId=ref(''),targetQuery=ref(''),targets=ref([]),target=ref(null),offset=ref(0),more=ref(false)
const selected=ref([]),replace=ref([]),refresh=ref([]),history=ref(false)
const detailHeading=ref(null),errorElement=ref(null)
const labels={title:'作品名称',title_cn:'中文名',original:'原名',description:'简介',year:'年份',publisher:'出版商',url:'来源链接',developer:'开发商',release_date:'发行日期',platforms:'平台',source_tags:'来源标签',aliases:'别名',cover_url:'封面候选地址',authors:'作者',tags:'建议标签',covers:'封面候选地址'}
const sourceLabels={openlibrary:'Open Library',bangumi:'Bangumi',vndb:'VNDB',ymgal:'月幕',civitai:'Civitai'}
const active=computed(()=>['queued','running'].includes(job.value?.status))
const available=computed(()=>providers.value.filter(p=>p.kinds.includes(kind.value)))
const candidates=computed(()=>Object.entries(results.value?.results||{}).flatMap(([source,r])=>(r.items||[]).map(i=>({...i,source}))))
const proposed=computed(()=>{const d=detail.value?.item;if(!d||!target.value||d.kind==='model')return {};const v={...d,release_date:d.date,source_tags:d.tags,cover_url:d.covers?.[0]};if(d.date&&/^\d{4}/.test(d.date))v.year=Number(d.date.slice(0,4));return Object.fromEntries(Object.keys(target.value.values).filter(k=>v[k]!==null&&v[k]!==undefined&&v[k]!==''&&(!Array.isArray(v[k])||v[k].length)).map(k=>[k,v[k]]))})
let timer,disposed=false
async function run(fn){if(busy.value)return;busy.value=true;error.value='';notice.value='';try{await fn()}catch(e){if(!disposed){error.value=e.message;await nextTick();errorElement.value?.focus()}}finally{if(!disposed)busy.value=false}}
function show(value){return value===null||value===undefined||value===''?'—':Array.isArray(value)?value.join('、'):String(value)}
async function loadTargets(){const page=await api.get(targetKind.value==='work'?'/api/works':'/api/galgames',{q:targetQuery.value,offset:offset.value,limit:20});if(disposed)return;targets.value=page.items;more.value=offset.value+20<page.total}
async function loadTarget(){target.value=null;selected.value=[];replace.value=[];refresh.value=[];history.value=false;if(!targetId.value)return;const data=await api.get(`/api/metadata/targets/${targetKind.value}/${targetId.value}`);if(!disposed){target.value=data;if(!title.value)title.value=data.values.title}}
function resetSearch(){selectedProviders.value=available.value.filter(p=>p.enabled).map(p=>p.id);results.value=null;detail.value=null;selected.value=[]}
async function poll(){const data=await api.get(`/api/jobs/${job.value.id}`);if(disposed)return;job.value=data;if(['queued','running'].includes(data.status)){timer=setTimeout(()=>run(poll),700);return}if(data.status==='done'){if(data.result.operation==='search'){results.value=data.result;notice.value='检索完成。选择具体条目读取详情，尚未写入本地资料。'}else{detail.value=Object.values(data.result.results)[0];selected.value=[];replace.value=[];refresh.value=[];notice.value='详情已缓存一小时。请核对原始条目、作品类型和字段。';await nextTick();detailHeading.value?.focus()}}else if(data.status==='error'){results.value=data.result;error.value=Object.entries(data.result?.errors||{}).map(([source,message])=>`${sourceLabels[source]||source}：${message}`).join('；')||data.message||'来源不可用；可稍后重试。';await nextTick();errorElement.value?.focus()}else notice.value='检索已停止，已有资料保持不变。'}
async function search(){detail.value=null;results.value=null;job.value=await api.post('/api/metadata/search',{online:true,kind:kind.value,title:title.value,author:author.value||null,providers:selectedProviders.value});timer=setTimeout(()=>run(poll),300)}
async function inspect(item){detail.value=null;job.value=await api.post('/api/metadata/detail',{online:true,kind:kind.value,provider:item.source,sid:item.sid});timer=setTimeout(()=>run(poll),300)}
async function cancel(){if(job.value)await api.post(`/api/jobs/${job.value.id}/cancel`)}
async function apply(){target.value=await api.post(`/api/metadata/targets/${targetKind.value}/${targetId.value}/apply`,{expected:target.value.expected,receipt:detail.value.receipt,fields:selected.value,replace:replace.value.filter(f=>selected.value.includes(f)),allow_refresh:refresh.value.filter(f=>selected.value.includes(f))});notice.value=target.value.changed?'已保存资料及字段来源，版本历史保留应用前快照。':'资料没有变化，未重复创建版本。';selected.value=[];history.value=false}
onMounted(()=>run(async()=>{providers.value=(await api.get('/api/metadata/providers')).items;resetSearch();await loadTargets();if(route.query.id){targetId.value=String(route.query.id);await loadTarget();kind.value=targetKind.value==='galgame'||['game','galgame'].includes(target.value.kind)?'game':'book';resetSearch()}}))
onBeforeUnmount(()=>{disposed=true;clearTimeout(timer);if(active.value)api.post(`/api/jobs/${job.value.id}/cancel`).catch(()=>{})})
</script>
<template>
  <div class="grid metadata-page">
    <header><h2>联网资料匹配</h2><p class="muted">主动检索公开资料，核对候选后按字段补全。不会发送小说正文、私人设定、本地路径或完整文件。</p></header>
    <p v-if="error" ref="errorElement" class="notice" role="alert" tabindex="-1">{{error}}</p><p v-if="notice" role="status">{{notice}}</p>
    <div class="metadata-columns">
      <section class="card grid"><h3>1 · 选择已有档案</h3>
        <label class="field">档案类型<select v-model="targetKind" :disabled="busy||active" @change="targetId='';target=null;offset=0;run(loadTargets)"><option value="work">作品 / 图书</option><option value="galgame">Galgame</option></select></label>
        <form class="row" @submit.prevent="offset=0;run(loadTargets)"><label class="field">本地档案搜索<input v-model="targetQuery" maxlength="95"/></label><button :disabled="busy||active">查找档案</button></form>
        <label class="field">目标档案<select v-model="targetId" :disabled="busy||active" @change="run(loadTarget)"><option value="">仅检索，不应用资料</option><option v-for="r in targets" :key="r.id" :value="String(r.id)">{{r.title}}</option></select></label>
        <nav class="row" aria-label="本地档案分页"><button :disabled="busy||active||!offset" @click="offset-=20;run(loadTargets)">上一页</button><button :disabled="busy||active||!more" @click="offset+=20;run(loadTargets)">下一页</button></nav>
        <p class="small muted">不自动新建或合并作品、角色与世界观。<RouterLink to="/works">管理作品</RouterLink> · <RouterLink to="/models">管理模型档案</RouterLink></p>
        <template v-if="target"><h4>{{target.values.title}}</h4><button :disabled="busy||active" @click="run(loadTarget)">重新载入目标资料</button><details><summary>已保存的字段来源</summary><div v-for="(f,key) in target.catalog.fields" :key="key" class="source-field"><b>{{labels[key]||key}}</b><p>{{sourceLabels[f.provider]}} · {{f.source_id}} · {{f.fetched_at}}</p><p>允许显式刷新：{{f.allow_refresh?'是':'否'}} · 当前值：{{show(target.values[key])}}</p></div></details><button @click="history=!history">{{history?'收起版本历史':'查看版本历史'}}</button><VersionPanel v-if="history" :kind="targetKind" :entity-id="Number(targetId)" @restored="run(loadTarget)"/></template>
      </section>
      <section class="card grid"><h3>2 · 手动发起在线检索</h3>
        <form class="grid" @submit.prevent="run(search)"><fieldset class="grid" :disabled="busy||active"><label class="field">资料种类<select v-model="kind" @change="resetSearch"><option value="book">小说 / 图书</option><option value="game">游戏 / Galgame</option><option value="model">SD 模型 / LoRA（Hash 查询）</option></select></label>
          <label class="field">{{kind==='model'?'已登记模型的 SHA256':'公开书名 / 作品名'}}<input v-model="title" required maxlength="95"/></label><label v-if="kind==='book'" class="field">作者（可留空）<input v-model="author" maxlength="95"/></label>
          <fieldset><legend>发送到以下来源</legend><label v-for="p in available" :key="p.id" class="provider-choice"><input v-model="selectedProviders" type="checkbox" :value="p.id" :disabled="!p.enabled"/>{{sourceLabels[p.id]}}{{p.enabled?'':'（已关闭）'}}</label></fieldset>
          <p class="small muted">本次仅发送上方检索词{{kind==='book'?'和作者':''}}。来源条款与封面授权需分别遵守；联网失败不影响离线资料。不会下载模型或启动 AI。</p><button class="primary" :disabled="!selectedProviders.length">确认发送并搜索</button></fieldset></form>
        <div v-if="active" class="row" role="status"><span>检索进度 {{job.done}} / {{job.total}}</span><button :disabled="busy" @click="run(cancel)">取消检索</button></div>
        <p v-for="(message,source) in results?.errors" :key="source" class="notice">{{sourceLabels[source]}}：{{message}}</p>
        <p v-if="results&&!candidates.length&&!active" class="muted">没有可用候选。可修改检索词，或保留人工填写的本地档案。</p>
        <div v-if="candidates.length" class="candidate-list" role="region" aria-label="资料候选列表" tabindex="0"><article v-for="i in candidates" :key="`${i.source}:${i.sid}`" class="candidate"><div class="row"><b>{{i.title}}</b><span class="badge">{{sourceLabels[i.source]}}</span><span class="badge">{{i.match.tier==='exact'?'完全匹配':i.match.tier==='strong'?'较强候选':'弱候选'}}</span><span v-if="i.match.ambiguous" class="badge">同名歧义</span></div><p class="small">{{[i.authors?.join('、'),i.year||i.date,i.sid].filter(Boolean).join(' · ')}}</p><p v-for="why in i.match.reasons" :key="why" class="small muted">{{why}}</p><button :disabled="busy||active" @click="run(()=>inspect(i))">核对这个条目的详情</button></article></div>
      </section>
    </div>
    <section v-if="detail" class="card grid"><h3 ref="detailHeading" tabindex="-1">3 · 核对字段与来源</h3><div class="row"><b>{{detail.item.title}}</b><span class="badge">{{sourceLabels[detail.item.provider]}} · {{detail.item.sid}}</span><a v-if="detail.item.url" class="btn" :href="detail.item.url" target="_blank" rel="noopener noreferrer">查看来源 ↗</a></div><p class="small muted">{{detail.fetched_at}} · 封面仅提供链接候选；建议标签与别名不会自动合并本地标签。</p>
      <p v-if="detail.item.kind==='model'" class="muted">模型候选仅供核对：{{detail.item.base_model}} · {{detail.item.version}} · {{detail.item.trigger_words}}。请到现有模型档案按 Hash 匹配并确认应用；来源声明不等于目标引擎兼容证明。</p>
      <p v-else-if="!target" class="muted">先选择本地目标档案，再选择需要补全的字段。</p>
      <form v-else class="grid" @submit.prevent="run(apply)"><fieldset :disabled="busy||active" class="grid"><div v-for="(value,key) in proposed" :key="key" class="field-comparison"><label><input v-model="selected" type="checkbox" :value="key"/> {{labels[key]||key}}</label><div><span class="small muted">当前</span><p>{{show(target.values[key])}}</p></div><div><span class="small muted">来源候选</span><p>{{show(value)}}</p></div><div class="grid"><label><input v-model="replace" type="checkbox" :value="key" :aria-label="`${labels[key]||key}：确认替换已有内容`"/>确认替换已有内容</label><label><input v-model="refresh" type="checkbox" :value="key" :aria-label="`${labels[key]||key}：允许以后显式刷新`"/>允许以后显式刷新此字段</label></div></div><button class="primary" :disabled="!selected.length">应用已确认字段</button></fieldset></form>
      <details v-if="detail.item.covers?.length"><summary>封面候选地址（不自动加载图片）</summary><p v-for="(u,index) in detail.item.covers" :key="u"><a :href="u" target="_blank" rel="noopener noreferrer">在外部查看封面 {{index+1}} ↗</a></p><p class="small muted">打开后会联系相应图床；封面不因可查看就获得再分发授权。</p></details>
    </section>
  </div>
</template>
<style scoped>
.metadata-page{min-width:0}.metadata-columns{display:grid;grid-template-columns:minmax(250px,1fr) minmax(0,1.8fr);gap:16px;align-items:start}.metadata-columns>*{min-width:0}.metadata-page fieldset{border:0;padding:0;margin:0;min-width:0}.metadata-page input:not([type=checkbox]),.metadata-page select{width:100%;min-width:0}.metadata-page input[type=checkbox]{width:auto}.provider-choice{display:inline-flex;gap:6px;margin-right:16px}.candidate-list{max-height:440px;overflow:auto;overscroll-behavior:contain}.candidate,.source-field{border-top:1px solid var(--line);padding-top:12px;overflow-wrap:anywhere}.field-comparison{display:grid;grid-template-columns:minmax(100px,.7fr) minmax(0,1fr) minmax(0,1fr) minmax(140px,1fr);gap:16px;border-top:1px solid var(--line);padding:14px 0}.field-comparison p{white-space:pre-wrap;overflow-wrap:anywhere;max-height:220px;overflow:auto}.metadata-page h3,.metadata-page h4{margin:0}.metadata-page .row{flex-wrap:wrap}.source-field p{overflow-wrap:anywhere}@media(max-width:850px){.metadata-columns{grid-template-columns:minmax(0,1fr)}.field-comparison{grid-template-columns:minmax(0,1fr)}.field-comparison p{margin:5px 0}.metadata-page button{white-space:normal}}
</style>
