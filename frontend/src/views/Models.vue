<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { api, LABELS, SDModels } from '../api'
import Modal from '../components/Modal.vue'
import TagChips from '../components/TagChips.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard } from '../toast'

const f = reactive({ q: '', kind: '', base_model: '' })
const items = ref([])
const editing = ref(null)
const inspecting = ref(false)
async function load() { items.value = (await SDModels.list({ ...f, limit: 500 })).items }
onMounted(load)
let t
watch(f, () => { clearTimeout(t); t = setTimeout(load, 200) }, { deep: true })

function edit(m) { editing.value = m ? { ...m, tag_ids: m.tags.map((x) => x.id) } : { name: '', kind: 'checkpoint', tag_ids: [] } }
async function inspect(hash) {
  inspecting.value = true
  try {
    const r = await guard(() => api.post('/api/sd-models/inspect', { path: editing.value.local_path, compute_hash: hash }))
    Object.assign(editing.value, { file_name: r.file_name, size: r.size, ...(r.sha256 ? { sha256: r.sha256 } : {}), ...(r.base_model && !editing.value.base_model ? { base_model: r.base_model } : {}) })
    if (!editing.value.name) editing.value.name = r.file_name.replace(/\.[^.]+$/, '')
  } finally { inspecting.value = false }
}
async function save() {
  const { id, created_at, updated_at, tags, ...body } = editing.value
  await guard(() => (id ? SDModels.update(id, body) : SDModels.create(body)), '已保存')
  editing.value = null; load()
}
async function remove() {
  if (!confirm('删除这条模型登记？（不会删除你电脑上的模型文件）')) return
  await guard(() => SDModels.remove(editing.value.id), '已删除'); editing.value = null; load()
}
const fmt = (n) => (n ? (n / 1024 ** 3 >= 1 ? (n / 1024 ** 3).toFixed(2) + ' GB' : (n / 1024 ** 2).toFixed(1) + ' MB') : '')
</script>
<template>
  <div class="notice" style="margin-bottom:14px">模型文件只登记路径、哈希与元数据，文件本身留在你的硬盘上，永远不会被上传或提交到仓库。</div>
  <div class="row" style="margin-bottom:12px">
    <input v-model="f.q" placeholder="搜索名称 / 触发词 / 备注" style="max-width:280px" />
    <select v-model="f.kind" style="width:150px"><option value="">全部类型</option><option v-for="(l, k) in LABELS.modelKind" :key="k" :value="k">{{ l }}</option></select>
    <select v-model="f.base_model" style="width:130px"><option value="">全部底模</option><option v-for="b in ['SD1.5', 'SD2', 'SDXL', 'Pony', 'Illustrious', 'SD3', 'Flux']" :key="b">{{ b }}</option></select>
    <span class="spacer" /><button class="primary" @click="edit(null)">＋ 登记模型</button>
  </div>
  <div class="card" style="padding:0">
    <table>
      <thead><tr><th>名称</th><th>类型</th><th>底模</th><th>触发词</th><th>本地路径</th><th>大小</th><th>标签</th></tr></thead>
      <tbody>
        <tr v-for="m in items" :key="m.id" style="cursor:pointer" @click="edit(m)">
          <td><b>{{ m.name }}</b><div class="small muted">{{ m.notes }}</div></td>
          <td><span class="badge">{{ LABELS.modelKind[m.kind] }}</span></td><td>{{ m.base_model }}</td>
          <td class="mono">{{ m.trigger_words }}</td><td class="mono muted">{{ m.local_path }}</td><td>{{ fmt(m.size) }}</td>
          <td><TagChips :tags="m.tags" /></td>
        </tr>
      </tbody>
    </table>
    <div v-if="!items.length" class="empty">还没有登记模型</div>
  </div>
  <Modal v-if="editing" :title="editing.id ? '编辑模型' : '登记模型'" @close="editing = null">
    <div class="grid">
      <label class="field">本地路径（运行 Front 的这台电脑上）<div class="row" style="flex-wrap:nowrap"><input v-model="editing.local_path" class="mono" placeholder="D:/sd-webui/models/Lora/xxx.safetensors" /><button :disabled="inspecting" @click="inspect(false)">读取信息</button><button :disabled="inspecting" @click="inspect(true)">计算 SHA256</button></div></label>
      <div class="grid cols-3">
        <label class="field">名称<input v-model="editing.name" /></label>
        <label class="field">类型<select v-model="editing.kind"><option v-for="(l, k) in LABELS.modelKind" :key="k" :value="k">{{ l }}</option></select></label>
        <label class="field">底模<input v-model="editing.base_model" placeholder="SDXL / SD1.5 / Flux…" /></label>
        <label class="field">版本<input v-model="editing.version" /></label>
        <label class="field">文件名<input v-model="editing.file_name" /></label>
        <label class="field">来源链接<input v-model="editing.source_url" /></label>
      </div>
      <label class="field">触发词<input v-model="editing.trigger_words" class="mono" /></label>
      <label class="field">SHA256<input v-model="editing.sha256" class="mono" /></label>
      <label class="field">备注<textarea v-model="editing.notes" /></label>
      <TagPicker v-model="editing.tag_ids" />
      <div class="row"><button v-if="editing.id" class="danger" @click="remove">删除登记</button><span class="spacer" /><button class="primary" @click="save">保存</button></div>
    </div>
  </Modal>
</template>
