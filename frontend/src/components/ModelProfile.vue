<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { guard, toast } from '../toast'
const props=defineProps({modelId:Number})
const data=ref(null), result=ref(null)
onMounted(()=>guard(async()=>{data.value=await api.get(`/api/model-assets/${props.modelId}/profile`)}))
async function save(){await guard(()=>api.put(`/api/model-assets/${props.modelId}/profile`,data.value),'使用资料已保存')}
async function check(engine){result.value=await guard(()=>api.post('/api/model-assets/compatibility',{engine,model_ids:[props.modelId]}));toast('仅检查登记信息，未连接或修改生成软件')}
async function connect(){if(!confirm('连接已配置的生成服务读取模型目录？不会启动服务、生成图片或修改配置。'))return;const r=await guard(()=>api.post('/api/model-assets/catalog-check',{engine:'comfyui',confirm_connect:true,model_ids:[props.modelId]}));toast(r.items[0].catalog_verified?'ComfyUI目录已识别该名称；运行兼容仍待验证':'ComfyUI目录未识别该名称')}
</script>
<template>
 <details v-if="data" class="card"><summary>收藏、使用心得与引擎名称映射</summary>
  <div class="grid" style="margin-top:12px">
   <div class="row"><label><input v-model="data.favorite" type="checkbox" style="width:auto"/> 收藏</label>
    <label>星级 <select v-model.number="data.stars"><option v-for="n in 6" :key="n" :value="n-1">{{n-1}}</option></select></label>
    <label>喜爱度 <input v-model.number="data.preference" type="number" min="0" max="100"/></label></div>
   <label class="field">画风<input v-model="data.style"/></label><label class="field">适用场景<input v-model="data.scenes"/></label>
   <label class="field">使用心得<textarea v-model="data.usage_notes"/></label>
   <p class="small muted">映射只保存在 Front，不改动外部配置。填写目标软件实际识别的相对名称；未连接目标引擎验证。</p>
   <label v-for="engine in ['webui','forge','comfyui']" :key="engine" class="field">{{engine}} 模型名称
    <div class="row"><input :value="data.engine_mappings[engine]||''" @input="e=>{if(e.target.value.trim())data.engine_mappings[engine]=e.target.value;else delete data.engine_mappings[engine]}"/><button @click="check(engine)">检查登记</button></div></label>
   <div v-if="result" class="notice">{{result.items[0].reason}}</div>
   <div v-if="data.observation?.diagnostics" class="small muted">扫描诊断：{{data.observation.diagnostics.join('；')}}</div>
   <button @click="save">保存使用资料</button>
   <button @click="connect">连接已配置的 ComfyUI 检查目录…</button>
  </div>
 </details>
</template>
