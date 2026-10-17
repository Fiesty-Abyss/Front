<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, Assets, Characters, LABELS, Relations, thumb, Works, Worlds } from '../api'
import Markdown from '../components/Markdown.vue'
import Modal from '../components/Modal.vue'
import TagChips from '../components/TagChips.vue'
import TagPicker from '../components/TagPicker.vue'
import { guard } from '../toast'

const router = useRouter()
const route = useRoute()
const f = reactive({ q: '', gender: '', tag: [], world_id: '', work_id: '' })
const items = ref([])
const worlds = ref([])
const works = ref([])
const images = ref([])
const editing = ref(null)
const rels = ref([])
const relForm = reactive({ target_id: '', kind: '' })
const all = ref([])

async function load() { items.value = (await Characters.list({ ...f, limit: 500 })).items }
onMounted(async () => {
  worlds.value = (await Worlds.list({ limit: 500 })).items
  works.value = (await Works.list({ limit: 500 })).items
  await load()
  if (route.query.edit) open(await Characters.get(Number(route.query.edit)))
})
let t
watch(f, () => { clearTimeout(t); t = setTimeout(load, 200) }, { deep: true })

const worldName = (id) => worlds.value.find((w) => w.id === id)?.name
const nameOf = (id) => all.value.find((c) => c.id === id)?.name ?? `#${id}`

async function open(c) {
  editing.value = c ? { ...c, tag_ids: c.tags.map((x) => x.id) } : { name: '', gender: 'unknown', tag_ids: [], world_id: f.world_id || null }
  all.value = (await Characters.list({ limit: 500 })).items
  images.value = (await Assets.list({ kind: 'drawing,ai_image,cg,reference', limit: 200 })).items
  rels.value = c ? (await Relations.list({ character_id: c.id, limit: 200 })).items : []
}
async function save() {
  const e = editing.value
  const body = { name: e.name, alias: e.alias, gender: e.gender, summary: e.summary, profile: e.profile, world_id: e.world_id || null, work_id: e.work_id || null, avatar_asset_id: e.avatar_asset_id || null, tag_ids: e.tag_ids }
  const saved = await guard(() => (e.id ? Characters.update(e.id, body) : Characters.create(body)), '已保存')
  editing.value = null
  router.push(`/characters/${saved.id}`)
}
async function remove() {
  if (!confirm(`删除角色「${editing.value.name}」？其关系也会删除。`)) return
  await guard(() => Characters.remove(editing.value.id), '已删除')
  editing.value = null
  load()
}
async function addRel() {
  if (!relForm.target_id || !relForm.kind) return
  await guard(() => Relations.create({ source_id: editing.value.id, target_id: Number(relForm.target_id), kind: relForm.kind }), '已添加关系')
  relForm.kind = ''
  rels.value = (await Relations.list({ character_id: editing.value.id })).items
}
async function delRel(r) {
  await guard(() => Relations.remove(r.id))
  rels.value = rels.value.filter((x) => x.id !== r.id)
}
async function makeCard() {
  await guard(() => api.post(`/api/cards/from-character/${editing.value.id}`), '已生成角色卡')
  router.push('/cards')
}
const genders = computed(() => Object.entries(LABELS.gender))
</script>

<template>
  <div class="with-filters">
    <aside class="filters card">
      <label class="field">搜索<input v-model="f.q" placeholder="名字 / 简介 / 设定" /></label>
      <div class="field small muted">性别</div>
      <div class="row" style="gap:6px">
        <span class="chip click" :class="{ on: !f.gender }" @click="f.gender = ''">全部</span>
        <span v-for="[k, l] in genders" :key="k" class="chip click" :class="{ on: f.gender === k }" @click="f.gender = k">{{ l }}</span>
      </div>
      <label class="field">世界观<select v-model="f.world_id"><option value="">全部</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }}</option></select></label>
      <label class="field">来源作品<select v-model="f.work_id"><option value="">全部</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select></label>
      <div class="field small muted">标签（动漫 / 游戏 / 来源 / 画风…）</div>
      <TagPicker v-model="f.tag" :categories="['medium', 'source', 'style', 'type', 'custom']" :allow-create="false" />
    </aside>
    <section>
      <div class="row" style="margin-bottom:12px"><span class="muted">共 {{ items.length }} 位角色</span><span class="spacer" /><button class="primary" @click="open(null)"><Ico g="＋" />新建角色</button></div>
      <div v-if="!items.length" class="empty card">没有符合条件的角色</div>
      <div v-reveal class="grid cols-2">
        <div v-for="c in items" :key="c.id" class="card row" style="cursor:pointer;flex-wrap:nowrap;align-items:flex-start" @click="router.push(`/characters/${c.id}`)">
          <div class="avatar" :style="c.avatar_asset_id ? { backgroundImage: `url(${thumb(c.avatar_asset_id)})` } : {}" />
          <div style="min-width:0">
            <div class="row" style="gap:8px"><b>{{ c.name }}</b><span class="badge">{{ LABELS.gender[c.gender] }}</span><span v-if="c.world_id" class="small muted">{{ worldName(c.world_id) }}</span></div>
            <div class="small muted" style="margin:4px 0 6px">{{ c.summary }}</div>
            <TagChips :tags="c.tags.filter((x) => x.category !== 'gender')" />
          </div>
        </div>
      </div>
    </section>
  </div>

  <Modal v-if="editing" :title="editing.id ? `角色 · ${editing.name}` : '新建角色'" @close="editing = null">
    <div class="grid">
      <div class="grid cols-3">
        <label class="field">名字<input v-model="editing.name" /></label>
        <label class="field">别名<input v-model="editing.alias" /></label>
        <label class="field">性别<select v-model="editing.gender"><option v-for="[k, l] in genders" :key="k" :value="k">{{ l }}</option></select></label>
        <label class="field">世界观<select v-model="editing.world_id"><option :value="null">无</option><option v-for="w in worlds" :key="w.id" :value="w.id">{{ w.name }}</option></select></label>
        <label class="field">来源作品<select v-model="editing.work_id"><option :value="null">无</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option></select></label>
        <label class="field">头像<select v-model="editing.avatar_asset_id"><option :value="null">无</option><option v-for="a in images" :key="a.id" :value="a.id">{{ a.title }}</option></select></label>
      </div>
      <label class="field">简介<textarea v-model="editing.summary" /></label>
      <div class="grid cols-2">
        <label class="field">详细设定（Markdown，[[名称]] 可链接到站内搜索）<textarea v-model="editing.profile" style="min-height:200px" class="mono" /></label>
        <div class="field">预览<div class="card" style="background:var(--panel2);min-height:200px;max-height:300px;overflow:auto;padding:10px 14px"><Markdown :source="editing.profile || ''" /></div></div>
      </div>
      <TagPicker v-model="editing.tag_ids" />
      <div v-if="editing.id" class="card" style="background:var(--panel2)">
        <b>关系</b>
        <table>
          <tr v-for="r in rels" :key="r.id">
            <td>{{ nameOf(r.source_id) }} → {{ nameOf(r.target_id) }}</td><td><span class="chip">{{ r.kind }}</span> <span v-if="r.ai_suggested" class="badge ai">AI 建议{{ r.confirmed ? '·已确认' : '·待确认' }}</span></td>
            <td style="text-align:right"><button class="ghost danger" @click="delRel(r)">删除</button></td>
          </tr>
        </table>
        <form class="row" style="margin-top:8px;flex-wrap:nowrap" @submit.prevent="addRel">
          <select v-model="relForm.target_id"><option value="">选择角色</option><option v-for="c in all.filter((x) => x.id !== editing.id)" :key="c.id" :value="c.id">{{ c.name }}</option></select>
          <input v-model="relForm.kind" placeholder="关系，如 青梅竹马 / 兄妹 / 对手" /><button type="submit">添加</button>
        </form>
      </div>
      <div class="row">
        <button v-if="editing.id" class="danger" @click="remove">删除</button>
        <button v-if="editing.id" @click="makeCard">生成角色卡</button>
        <span class="spacer" /><button class="primary" @click="save">保存</button>
      </div>
    </div>
  </Modal>
</template>
