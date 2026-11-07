<script setup>
import {onBeforeUnmount,ref,watch} from 'vue'
import {api} from '../api'
const props=defineProps({project:Object}),emit=defineEmits(['created','changed'])
const assetId=ref(''),title=ref(''),preview=ref(null),book=ref(null),offset=ref(0),error=ref(''),busy=ref(false)
let disposed=false,timer=null
const token=()=>({project_uid:props.project.uid,expected_project_version:props.project.version})
async function run(fn){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){if(!disposed){error.value=e.message;book.value=null}}finally{if(!disposed)busy.value=false}}
async function load(){
  clearTimeout(timer)
  if(!props.project?.book_source){book.value=null;return}
  const data=await api.get(`/api/voice/books/projects/${props.project.id}`,{offset:offset.value,limit:30})
  if(disposed)return
  book.value=data;emit('changed',data.project)
  if(data.chapters.some(c=>['queued','running'].includes(c.import?.status)))timer=setTimeout(()=>run(load),2000)
}
async function inspect(){const data=await api.get(`/api/voice/books/sources/${Number(assetId.value)}`,{limit:30});if(!disposed){preview.value=data;title.value=(data.title+' 配音工程').slice(0,200)}}
async function create(){const row=await api.post(`/api/voice/books/sources/${Number(assetId.value)}/projects`,{title:title.value,source_fingerprint:preview.value.source.fingerprint});if(!disposed){preview.value=null;emit('created',row)}}
async function queue(chapter){const data=await api.post(`/api/voice/books/projects/${props.project.id}/imports`,{...token(),source_fingerprint:book.value.source.fingerprint,chapter_index:chapter.index});if(!disposed){emit('changed',data.project);await load()}}
async function cancel(chapter){await api.post(`/api/voice/books/projects/${props.project.id}/imports/${chapter.import.id}/cancel`,token());if(!disposed)await load()}
watch(()=>props.project?.id,()=>{offset.value=0;book.value=null;run(load)},{immediate:true})
onBeforeUnmount(()=>{disposed=true;clearTimeout(timer)})
</script>
<template>
  <section class="card grid">
    <details><summary>从已确认章节的小说创建配音工程</summary><div class="grid">
      <p class="muted">先在章节整理确认目录。原文保留，朗读稿另存；规则识别的说话人候选需要人工核对。</p>
      <div class="row"><label class="field">小说素材 ID<input v-model="assetId" type="number" min="1"/></label><button :disabled="busy||!assetId" @click="run(inspect)">只读预览来源</button><RouterLink v-if="assetId" :to="'/chapters/'+assetId">打开章节整理</RouterLink></div>
      <div v-if="preview" class="grid"><p>{{preview.title}} · {{preview.total}} 章 · 已确认目录 #{{preview.source.revision_id}}</p><label class="field">新工程名称<input v-model="title" maxlength="200"/></label><p class="small muted">{{preview.chapters.map(c=>c.title).join(' · ')}}{{preview.total>30?'…':''}}</p><button :disabled="busy||!title.trim()" @click="run(create)">创建独立工程（不修改小说）</button></div>
    </div></details>
    <p v-if="error" class="notice" role="alert">{{error}}</p>
    <button v-if="project?.book_source&&!book" :disabled="busy" @click="run(load)">重新核对小说来源</button>
    <div v-if="book" class="grid"><div class="row"><b>小说章节</b><button :disabled="busy" @click="run(load)">刷新导入进度</button><RouterLink :to="'/chapters/'+book.source.asset_id">来源章节</RouterLink></div>
      <small class="muted">使用确认目录 #{{book.source.revision_id}}。每次至多导入10万字符/1000片段，剩余内容可显式续导。只读原文，不执行AI或TTS。</small>
      <div v-for="chapter in book.chapters" :key="chapter.index" class="row"><span>{{chapter.title}}</span><small>{{chapter.import?.status||'未导入'}}<template v-if="chapter.import"> · {{chapter.import.cursor}} / {{chapter.import.end}}</template></small><button :disabled="busy||['queued','running','done'].includes(chapter.import?.status)" @click="run(()=>queue(chapter))">{{chapter.import?'续导/重试':'导入本章草稿'}}</button><button v-if="['queued','running'].includes(chapter.import?.status)" :disabled="busy" @click="run(()=>cancel(chapter))">取消</button><small v-if="chapter.import?.error_code" role="alert">{{chapter.import.error_code}}；请核对来源后重试。</small></div>
      <div class="row"><button :disabled="busy||!offset" @click="offset-=30;run(load)">章节上页</button><small>{{book.total}} 章</small><button :disabled="busy||offset+30>=book.total" @click="offset+=30;run(load)">章节下页</button></div>
      <small class="muted">导入完成后刷新下方片段列表，编辑朗读稿并确认说话人。原目录/正文变化不自动覆盖已保存草稿。</small>
    </div>
  </section>
</template>
