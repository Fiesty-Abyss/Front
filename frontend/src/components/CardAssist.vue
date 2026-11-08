<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api'
const props=defineProps({current:Object})
const emit=defineEmits(['adopt','open-card'])
const providers=ref([]),providerId=ref(''),brief=ref(''),style=ref(''),prepared=ref(null),confirmed=ref(false),remoteConfirmed=ref(false)
const draft=ref(null),selected=ref([]),error=ref(''),busy=ref(false),drafts=ref([]),offset=ref(0),total=ref(0)
const labels={name:'名字',description:'角色介绍',personality:'性格',scenario:'场景/世界观',first_mes:'开场白',mes_example:'对话示例',system_prompt:'System Prompt',alternate_greetings:'备选开场白',card_tags:'建议标签'}
const active=computed(()=>['queued','running'].includes(draft.value?.status))
let timer,disposed=false
watch([providerId,brief,style],()=>{prepared.value=null;confirmed.value=false;remoteConfirmed.value=false})
watch(()=>props.current?.extText,()=>{try{if(draft.value&&!active.value&&!draft.value.adopted_id&&JSON.parse(props.current?.extText||'{}').front_assist_v1?.draft_id===draft.value.id)run(()=>open(draft.value.id))}catch{}})
async function run(fn){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){if(!disposed)error.value=e.message}finally{if(!disposed)busy.value=false}}
const body=()=>({provider_id:Number(providerId.value),brief:brief.value,style:style.value})
async function load(){const r=await api.get('/api/cards/assist/drafts',{limit:20,offset:offset.value});if(!disposed){drafts.value=r.items;total.value=r.total}}
async function preview(){prepared.value=await api.post('/api/cards/assist/prepare',body());confirmed.value=false;remoteConfirmed.value=false}
async function poll(){const r=await api.get(`/api/cards/assist/drafts/${draft.value.id}`);if(disposed)return;draft.value=r;if(['queued','running'].includes(r.status))timer=setTimeout(()=>run(poll),800);else{selected.value=[];await load()}}
async function generate(){draft.value=await api.post('/api/cards/assist/generate',{...body(),request_id:crypto.randomUUID().replaceAll('-',''),request_hash:prepared.value.request_hash,confirm_send:confirmed.value,confirm_remote:remoteConfirmed.value});await load();timer=setTimeout(()=>run(poll),300)}
async function open(id){clearTimeout(timer);draft.value=await api.get(`/api/cards/assist/drafts/${id}`);selected.value=[];if(active.value)timer=setTimeout(()=>run(poll),300)}
async function cancel(){await api.post(`/api/cards/assist/drafts/${draft.value.id}/cancel`)}
async function refreshStatus(){clearTimeout(timer);await poll()}
function adopt(){emit('adopt',{draftId:draft.value.id,fields:Object.fromEntries(selected.value.map(k=>[k,draft.value.fields[k]]))})}
onMounted(()=>run(async()=>{providers.value=(await api.get('/api/ai/providers')).items.filter(p=>p.chat_model);await load()}))
onBeforeUnmount(()=>{disposed=true;clearTimeout(timer);if(active.value)api.post(`/api/cards/assist/drafts/${draft.value.id}/cancel`).catch(()=>{})})
</script>
<template>
  <section class="card-assist grid"><h3>AI 辅助草稿</h3><p class="small muted">仅发送这里明确填写的说明，不自动附带角色卡、小说、世界书或私人素材。返回内容需人工审核；不会直接写入正式角色卡。</p>
    <p v-if="error" role="alert" class="notice">{{error}}</p><p v-if="!providers.length" class="small muted">尚无已配置的文本模型。<RouterLink to="/settings">配置服务</RouterLink>后可用；手动角色卡不依赖AI。</p>
    <form class="grid" @submit.prevent="run(preview)"><fieldset class="grid" :disabled="busy||active"><label class="field">明确选择文本服务<select v-model="providerId" required><option value="">请选择，不使用隐式默认服务</option><option v-for="p in providers" :key="p.id" :value="String(p.id)">{{p.name}} · {{p.chat_model}}</option></select></label><label class="field">本次创作说明<textarea v-model="brief" required maxlength="12000" rows="5"/></label><label class="field">创作风格（可留空）<input v-model="style" maxlength="200"/></label><button :disabled="!providerId||!brief.trim()">先预览确切发送内容</button></fieldset></form>
    <div v-if="prepared" class="grid"><p>{{prepared.provider.name}} · {{prepared.provider.model}} · {{prepared.remote?'远程/非回环服务':'字面回环服务'}} · 最多2048输出token</p><details open><summary>即将发送的完整消息</summary><pre>{{JSON.stringify(prepared.messages,null,2)}}</pre></details><label><input v-model="confirmed" type="checkbox" :disabled="busy||active"/>我已审核以上发送内容与所选服务</label><label v-if="prepared.remote"><input v-model="remoteConfirmed" type="checkbox" :disabled="busy||active"/>我确认将这段文本发送给该远程服务，并了解其使用条件与可能费用</label><button class="primary" :disabled="busy||active||!confirmed||(prepared.remote&&!remoteConfirmed)" @click="run(generate)">生成可审核草稿</button></div>
    <button v-if="draft" :disabled="busy" @click="run(refreshStatus)">刷新草稿状态</button><div v-if="active" class="row" role="status"><span>草稿正在{{draft.status==='queued'?'排队':'生成'}}；不自动重试</span><button :disabled="busy" @click="run(cancel)">取消草稿生成</button></div>
    <div v-if="draft&&!active" class="grid"><p role="status">草稿状态：{{draft.status==='ready'?(draft.adopted_id?'已采用，保留原候选':'待审核'):draft.status}}</p><p class="small muted">{{draft.provider.name}} · {{draft.provider.model}} · {{draft.created_at}} · 输出预算 {{draft.provider.max_tokens}} token</p><p v-if="draft.error" role="alert" class="notice">{{draft.error}}</p><p v-if="draft.adopted_id">此候选已采用到档案 #{{draft.adopted_id}}；可在版本历史查看当时修改，不自动覆盖当前版本。<button @click="emit('open-card',draft.adopted_id)">打开已采用角色卡</button></p>
      <template v-if="draft.status==='ready'"><div v-for="(value,key) in draft.fields" :key="key" class="suggested-field"><label><input v-model="selected" type="checkbox" :value="key" :disabled="Boolean(draft.adopted_id)"/>采用{{labels[key]||key}}</label><p class="small muted">当前：{{Array.isArray(props.current?.[key])?props.current[key].join('、'):props.current?.[key]||'—'}}</p><pre>{{Array.isArray(value)?value.join('\n'):value||'（空）'}}</pre></div><button :disabled="!selected.length||busy||Boolean(draft.adopted_id)" @click="adopt">把勾选字段放入未保存草稿</button><p class="small muted">只更新编辑表单；仍可修改或撤销，点击角色卡保存后才正式采用并登记来源。</p></template>
    </div>
    <details><summary>保留的生成历史（{{total}}）</summary><div v-for="r in drafts" :key="r.id" class="row"><span class="small">{{r.created_at}} · {{r.status}}{{r.adopted_id?' · 已采用':''}}</span><button :disabled="busy||active" @click="run(()=>open(r.id))">查看草稿</button></div><nav class="row" aria-label="AI角色卡草稿分页"><button :disabled="busy||active||!offset" @click="offset-=20;run(load)">上一页</button><button :disabled="busy||active||offset+20>=total" @click="offset+=20;run(load)">下一页</button></nav></details>
  </section>
</template>
<style scoped>
.card-assist{border-top:1px solid var(--line);padding-top:16px;min-width:0}.card-assist fieldset{border:0;padding:0;margin:0;min-width:0}.card-assist input:not([type=checkbox]),.card-assist select{width:100%;min-width:0}.card-assist input[type=checkbox]{width:auto}.card-assist pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:260px;overflow:auto;font:inherit;font-size:13px}.suggested-field{border-top:1px solid var(--line);padding-top:12px}.card-assist button{white-space:normal}
</style>
