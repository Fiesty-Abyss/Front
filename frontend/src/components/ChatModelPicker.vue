<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
const props=defineProps({sessionId:{type:Number,required:true}})
const emit=defineEmits(['selected'])
const providers=ref([]), state=ref(null), history=ref([]), total=ref(0), offset=ref(0), busy=ref(false), error=ref('')
const form=ref({provider_id:'',model:'',temperature:.8,max_tokens:2048,context_characters:32000})
async function refresh(){state.value=await api.get(`/api/ai/sessions/${props.sessionId}/model-state`);emit('selected',state.value)}
async function loadHistory(){const result=await api.get(`/api/ai/sessions/${props.sessionId}/model-history?limit=10&offset=${offset.value}`);history.value=result.items;total.value=result.total}
function fill(snapshot){form.value={provider_id:snapshot.provider_id,model:snapshot.model,temperature:snapshot.temperature,max_tokens:snapshot.max_tokens,context_characters:snapshot.context_characters}}
function providerChanged(){const p=providers.value.find(x=>x.id===Number(form.value.provider_id));if(p)form.value.model=p.chat_model||''}
async function save(){busy.value=true;error.value='';try{const result=await api.post(`/api/ai/sessions/${props.sessionId}/model-selection`,{...form.value,provider_id:Number(form.value.provider_id),expected:state.value.expected});state.value=result;emit('selected',result);offset.value=0;await loadHistory()}catch(e){error.value=e.message;await refresh().catch(()=>{});/* Keep editable fields for review after conflict. */}finally{busy.value=false}}
async function page(delta){offset.value+=delta;try{await loadHistory()}catch(e){error.value=e.message}}
onMounted(async()=>{try{providers.value=(await api.get('/api/ai/providers')).items;await refresh();if(state.value.selection)fill(state.value.selection.snapshot);await loadHistory()}catch(e){error.value=e.message}})
</script>
<template>
<section class="model-config" aria-label="会话模型设置">
  <h3>本会话的模型与预算</h3>
  <p class="small muted">明确选择后固定到此会话；不会随全局默认模型改变。不启动服务、不测试联网，也不发送对话。模型是否存在、实际上下文能力需在对应服务验证。</p>
  <p v-if="error" class="notice" role="alert">{{error}}</p>
  <p v-if="state" class="small">当前：{{state.selection ? `${state.selection.snapshot.provider_name} · ${state.selection.snapshot.model}` : '沿用全局默认（旧会话兼容）'}}</p>
  <form class="model-fields" @submit.prevent="save">
    <label>文本服务<select v-model="form.provider_id" required @change="providerChanged"><option value="" disabled>明确选择已配置服务</option><option v-for="p in providers" :key="p.id" :value="p.id">{{p.name}}</option></select></label>
    <label>模型名称<input v-model="form.model" required maxlength="200" /></label>
    <label>温度<input v-model.number="form.temperature" type="number" min="0" max="2" step="0.1" required /></label>
    <label>输出 token 上限<input v-model.number="form.max_tokens" type="number" min="1" max="32768" required /></label>
    <label>上下文字数预算<input v-model.number="form.context_characters" type="number" min="1024" max="250000" required /></label>
    <button class="primary" :disabled="busy || !state">{{busy?'正在保存…':'明确切换并保存快照'}}</button>
  </form>
  <p class="small muted">字数预算不是模型 token 长度。预算不足时仅省略旧轮次，保留人设、指令和最新消息；过大的必要内容会提示修改，原聊天不截断。服务改变地址或被删除时阻止生成，不自动换服务。</p>
  <details><summary>模型切换历史（{{total}}）</summary>
    <div v-for="row in history" :key="row.id" class="model-history small"><span>#{{row.id}} · {{row.snapshot.provider_name}} · {{row.snapshot.model}} · {{row.created_at}}</span><button type="button" @click="fill(row.snapshot)">将此配置放入表单</button></div>
    <div class="row"><button :disabled="offset===0" @click="page(-10)">上一页</button><button :disabled="offset+10>=total" @click="page(10)">下一页</button></div>
  </details>
</section>
</template>
<style scoped>
.model-config{padding:12px;background:var(--panel2);border:1px solid var(--line);border-radius:10px;margin-bottom:12px;min-width:0}
.model-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.model-fields label{display:grid;gap:5px;min-width:0}.model-fields input,.model-fields select{width:100%;min-width:0}.model-history{display:flex;gap:8px;align-items:center;justify-content:space-between;padding:8px 0;overflow-wrap:anywhere}
</style>
