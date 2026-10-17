<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, Assets, Cards, Lorebooks, thumb } from '../api'
import { guard, toast } from '../toast'

const router = useRouter()
const route = useRoute()
const items = ref([])
const cur = ref(null)
const images = ref([])
const importInput = ref(null)
const tab = ref('basic')

const books = ref([])
async function load() { items.value = (await Cards.list({ limit: 500 })).items; books.value = (await Lorebooks.list()).items }
onMounted(async () => {
  await load()
  images.value = (await Assets.list({ kind: 'drawing,ai_image,cg,reference', limit: 500 })).items
  const want = items.value.find((c) => c.id === Number(route.query.id))
  if (want || items.value.length) select(want ?? items.value[0])
})
function select(c) {
  cur.value = c
    ? { ...c, greetingsText: c.alternate_greetings.join('\n---\n'), tagsText: c.card_tags.join(', '), extText: JSON.stringify(c.extensions, null, 2) }
    : { name: '', description: '', personality: '', scenario: '', first_mes: '', mes_example: '', creator_notes: '', system_prompt: '', post_history_instructions: '', greetingsText: '', tagsText: '', extText: '{}', creator: '', character_version: '' }
}
function body() {
  const c = cur.value
  let extensions
  try { extensions = JSON.parse(c.extText || '{}') } catch { toast('extensions 需要是 JSON', true); throw new Error('bad json') }
  return {
    name: c.name, description: c.description, personality: c.personality, scenario: c.scenario, first_mes: c.first_mes,
    mes_example: c.mes_example, creator_notes: c.creator_notes, system_prompt: c.system_prompt,
    post_history_instructions: c.post_history_instructions, creator: c.creator, character_version: c.character_version,
    alternate_greetings: c.greetingsText.split(/\n-{3,}\n/).map((s) => s.trim()).filter(Boolean),
    card_tags: c.tagsText.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
    extensions, avatar_asset_id: c.avatar_asset_id || null, character_id: c.character_id || null, lorebook_id: c.lorebook_id || null,
  }
}
async function save() {
  const saved = await guard(() => (cur.value.id ? Cards.update(cur.value.id, body()) : Cards.create(body())), '已保存')
  await load(); select(saved)
}
async function remove() {
  if (!confirm(`删除角色卡「${cur.value.name}」？`)) return
  await guard(() => Cards.remove(cur.value.id), '已删除'); cur.value = null; load()
}
async function doImport() {
  const file = importInput.value.files[0]
  if (!file) return
  const form = new FormData(); form.append('file', file)
  const c = await guard(() => api.upload('/api/cards/import', form), `已导入 ${file.name}`)
  importInput.value.value = ''
  await load(); select(c)
}
async function chat() {
  const s = await guard(() => api.post('/api/ai/sessions', { card_id: cur.value.id, title: `与 ${cur.value.name} 的对话` }))
  router.push({ path: '/chat', query: { session: s.id } })
}
const fields = {
  basic: [['description', '角色描述 description', 180], ['personality', '性格 personality', 70], ['scenario', '场景 scenario', 70], ['first_mes', '开场白 first_mes', 100]],
  advanced: [['mes_example', '对话示例 mes_example（<START> 分隔）', 140], ['system_prompt', '系统提示词 system_prompt', 80], ['post_history_instructions', '历史后指令 post_history_instructions', 60], ['creator_notes', '作者备注 creator_notes', 60]],
}
</script>
<template>
  <div class="grid" style="grid-template-columns: 260px 1fr">
    <aside class="card grid" style="align-content:start;gap:8px">
      <button class="primary" @click="select(null)"><Ico g="＋" />新建角色卡</button>
      <label class="btn" style="justify-content:center"><Ico g="⇪" />导入 JSON / PNG 卡<input ref="importInput" type="file" accept=".json,.png" hidden @change="doImport" /></label>
      <div v-for="c in items" :key="c.id" class="card row" style="cursor:pointer;padding:8px;flex-wrap:nowrap" :style="cur?.id === c.id ? { borderColor: 'var(--accent)' } : {}" @click="select(c)">
        <div class="avatar" style="width:40px;height:40px" :style="c.avatar_asset_id ? { backgroundImage: `url(${thumb(c.avatar_asset_id)})` } : {}" />
        <div><b>{{ c.name }}</b><div class="small muted">{{ c.creator }} {{ c.character_version }}</div></div>
      </div>
      <p class="small muted">兼容 SillyTavern / TavernAI Character Card V2（V1、V3 也可导入）。</p>
    </aside>
    <section v-if="cur" class="card grid" style="align-content:start">
      <div class="row" style="flex-wrap:nowrap;align-items:flex-start">
        <div class="avatar" style="width:120px;height:160px" :style="cur.avatar_asset_id ? { backgroundImage: `url(${thumb(cur.avatar_asset_id)})` } : {}" />
        <div class="grid" style="flex:1">
          <div class="grid cols-3">
            <label class="field">名字 name<input v-model="cur.name" /></label>
            <label class="field">作者 creator<input v-model="cur.creator" /></label>
            <label class="field">版本<input v-model="cur.character_version" /></label>
          </div>
          <div class="grid cols-2">
            <label class="field">头像（素材库图片）<select v-model="cur.avatar_asset_id"><option :value="null">无（导出时用渐变占位图）</option><option v-for="a in images" :key="a.id" :value="a.id">{{ a.title }}</option></select></label>
            <label class="field">标签（逗号分隔）<input v-model="cur.tagsText" /></label>
            <label class="field">角色书 character_book <span class="small muted">（导出时一起导出；<RouterLink :to="cur.lorebook_id ? `/lorebooks?id=${cur.lorebook_id}` : '/lorebooks'">编辑世界书</RouterLink>）</span>
              <select v-model="cur.lorebook_id"><option :value="null">无</option><option v-for="b in books" :key="b.id" :value="b.id">{{ b.name }}（{{ b.entries }} 条）</option></select></label>
          </div>
        </div>
      </div>
      <div class="row"><span v-for="[k, l] in [['basic', '基础'], ['advanced', '进阶'], ['extra', '备用开场白 / 扩展']]" :key="k" class="chip click" :class="{ on: tab === k }" @click="tab = k">{{ l }}</span></div>
      <template v-if="tab !== 'extra'">
        <label v-for="[k, l, h] in fields[tab]" :key="k" class="field">{{ l }}<textarea v-model="cur[k]" :style="{ minHeight: h + 'px' }" /></label>
      </template>
      <template v-else>
        <label class="field">备用开场白 alternate_greetings（用单独一行 --- 分隔）<textarea v-model="cur.greetingsText" style="min-height:140px" /></label>
        <label class="field">extensions（JSON）<textarea v-model="cur.extText" class="mono" /></label>
      </template>
      <p class="small muted" v-pre>支持 {{char}} / {{user}} 占位符。</p>
      <div class="row">
        <button v-if="cur.id" class="danger" @click="remove">删除</button>
        <a v-if="cur.id" class="btn" :href="`/api/cards/${cur.id}/export.json`">导出 JSON</a>
        <a v-if="cur.id" class="btn" :href="`/api/cards/${cur.id}/export.png`">导出 PNG 卡</a>
        <button v-if="cur.id" @click="chat">✉ 开始 AI 对话</button>
        <span class="spacer" /><button class="primary" @click="save">保存</button>
      </div>
    </section>
  </div>
</template>
