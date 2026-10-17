<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, Assets, Generations, Prompts, SDModels, thumb } from '../api'
import Modal from '../components/Modal.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard, toast } from '../toast'

const f = reactive({ q: '', tag: [] })
const items = ref([])
const cur = ref(null)
const cmp = ref(null)
const models = ref([])
const images = ref([])
const gen = reactive({ model_id: '', asset_id: '' })
const adding = ref(false)

async function load() { items.value = (await Prompts.list({ ...f, limit: 500 })).items }
const route = useRoute()
onMounted(async () => {
  await load()
  const want = items.value.find((p) => p.id === Number(route.query.id))
  if (want || items.value.length) select(want ?? items.value[items.value.length - 1])
})
let t
watch(f, () => { clearTimeout(t); t = setTimeout(load, 200) }, { deep: true })

async function select(p) {
  cur.value = p ? { ...p, tag_ids: p.tags.map((x) => x.id), paramsText: JSON.stringify(p.params, null, 2) } : { title: '', positive: '', negative: '', tag_ids: [], paramsText: '{}' }
  cmp.value = p ? await api.get(`/api/prompts/${p.id}/compare`) : null
}
async function save() {
  const p = cur.value
  let params
  try { params = JSON.parse(p.paramsText || '{}') } catch { return toast('参数需要是 JSON', true) }
  const body = { title: p.title, positive: p.positive, negative: p.negative, notes: p.notes, params, tag_ids: p.tag_ids }
  const saved = await guard(() => (p.id ? Prompts.update(p.id, body) : Prompts.create(body)), '已保存')
  await load(); select(saved)
}
async function remove() {
  if (!confirm('删除提示词及其对比记录？')) return
  await guard(() => Prompts.remove(cur.value.id), '已删除'); cur.value = null; cmp.value = null; load()
}
const copy = (s) => navigator.clipboard?.writeText(s).then(() => toast('已复制'))
async function openAdd() {
  models.value = (await SDModels.list({ limit: 500 })).items
  images.value = (await Assets.list({ kind: 'ai_image', limit: 500 })).items
  adding.value = true
}
async function addGen() {
  await guard(() => Generations.create({ prompt_id: cur.value.id, model_id: gen.model_id || null, asset_id: gen.asset_id || null }), '已加入对比')
  adding.value = false
  cmp.value = await api.get(`/api/prompts/${cur.value.id}/compare`)
}
</script>
<template>
  <div class="grid" style="grid-template-columns: 300px 1fr">
    <aside class="card grid" style="align-content:start;gap:8px">
      <input v-model="f.q" placeholder="搜索提示词内容" />
      <button class="primary" @click="select(null)">＋ 新建提示词</button>
      <div v-for="p in items" :key="p.id" class="card" style="cursor:pointer;padding:10px" :style="cur?.id === p.id ? { borderColor: 'var(--accent)' } : {}" @click="select(p)">
        <b>{{ p.title }}</b><div class="small muted mono" style="max-height:34px;overflow:hidden">{{ p.positive }}</div>
      </div>
    </aside>
    <section v-if="cur" class="grid" style="align-content:start">
      <div class="card grid">
        <label class="field">标题<input v-model="cur.title" /></label>
        <label class="field"><span class="row">正向提示词<span class="spacer" /><a class="small" @click="copy(cur.positive)">复制</a></span><textarea v-model="cur.positive" class="mono" /></label>
        <label class="field"><span class="row">反向提示词<span class="spacer" /><a class="small" @click="copy(cur.negative || '')">复制</a></span><textarea v-model="cur.negative" class="mono" style="min-height:50px" /></label>
        <div class="grid cols-2">
          <label class="field">参数（JSON：steps / sampler / cfg / seed / size）<textarea v-model="cur.paramsText" class="mono" /></label>
          <label class="field">备注<textarea v-model="cur.notes" /></label>
        </div>
        <TagPicker v-model="cur.tag_ids" />
        <div class="row"><button v-if="cur.id" class="danger" @click="remove">删除</button><span class="spacer" /><button class="primary" @click="save">保存</button></div>
      </div>
      <div v-if="cmp" class="card">
        <div class="row"><h2 style="margin:0">同一提示词 × 不同模型</h2><span class="spacer" /><button @click="openAdd">＋ 加入一张出图</button></div>
        <div v-if="!cmp.groups.length" class="empty">还没有出图记录。把 AI 图上传到素材库后，在这里关联模型即可并排对比。</div>
        <div class="grid" :style="{ gridTemplateColumns: `repeat(${Math.max(cmp.groups.length, 1)}, 1fr)` }">
          <div v-for="(g, i) in cmp.groups" :key="i">
            <div class="row" style="margin:8px 0"><b>{{ g.model?.name ?? '未指定模型' }}</b><span v-if="g.model" class="badge">{{ g.model.base_model }}</span></div>
            <div v-for="it in g.items" :key="it.generation_id" class="tile" style="margin-bottom:8px">
              <div class="img" :style="it.asset?.width ? { backgroundImage: `url(${thumb(it.asset.id)})` } : {}" />
              <div class="meta small muted">{{ it.notes || it.asset?.title }}</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
  <Modal v-if="adding" title="加入对比" @close="adding = false">
    <div class="grid cols-2">
      <label class="field">模型<select v-model="gen.model_id"><option value="">未指定</option><option v-for="m in models" :key="m.id" :value="m.id">{{ m.name }}</option></select></label>
      <label class="field">图片（素材库中的 AI 生成图）<select v-model="gen.asset_id"><option value="">无</option><option v-for="a in images" :key="a.id" :value="a.id">{{ a.title }}</option></select></label>
    </div>
    <div class="row" style="margin-top:12px"><span class="spacer" /><button class="primary" @click="addGen">加入</button></div>
  </Modal>
</template>
