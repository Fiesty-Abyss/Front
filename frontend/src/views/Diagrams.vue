<script setup>
// 图表画布列表：按类型筛选、模板新建、导入 JSON、复制 / 删除
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Upload, Copy, Trash2, Pin, Workflow, GitFork, Network, Shapes } from 'lucide-vue-next'
import { api, Diagrams } from '../api'
import { guard, toast } from '../toast'
import Modal from '../components/Modal.vue'
import { KINDS } from '../diagram/defs'

const route = useRoute()
const router = useRouter()
const items = ref([])
const kind = ref('')
const loading = ref(true)
const creating = ref(route.query.new === '1')
const templates = ref([])
const fileInput = ref(null)
const ICON = { flowchart: GitFork, workflow: Workflow, mindmap: Network, other: Shapes }

async function load() {
  loading.value = true
  items.value = (await Diagrams.list({ kind: kind.value || undefined, limit: 200 })).items
  loading.value = false
}
watch(kind, load)
onMounted(async () => { await guard(load); templates.value = await api.get('/api/diagrams/templates') })

async function create(t) {
  const d = await guard(() => Diagrams.create({ title: t.id === 'blank' ? '未命名图表' : t.title.replace('【示例】', ''), kind: t.kind, data: t.data }))
  if (d) router.push(`/diagrams/${d.id}`)
}
async function importFile(e) {
  const f = e.target.files?.[0]
  e.target.value = ''
  if (!f) return
  let body
  try { body = JSON.parse(await f.text()) } catch { toast('不是有效的 JSON 文件', true); return }
  const d = await guard(() => api.post('/api/diagrams/import', body), '已导入')
  if (d) router.push(`/diagrams/${d.id}`)
}
async function duplicate(d) { await guard(() => api.post(`/api/diagrams/${d.id}/duplicate`), '已复制'); load() }
async function remove(d) { if (!confirm(`删除图表“${d.title}”？`)) return; await guard(() => Diagrams.remove(d.id), '已删除'); load() }
const preview = (d) => `/api/diagrams/${d.id}/preview?v=${encodeURIComponent(d.updated_at)}`
const broken = ref(new Set())
const when = (s) => new Date(s.endsWith('Z') || s.includes('+') ? s : s + 'Z').toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
const counts = computed(() => items.value.reduce((m, d) => ({ ...m, [d.kind]: (m[d.kind] || 0) + 1 }), {}))
const TPL_ART = { blank: Plus, flow: GitFork, workflow: Workflow, mind: Network }
</script>

<template>
  <div class="dgl">
    <div class="row dgl-head">
      <div class="seg" role="tablist" aria-label="按类型筛选">
        <button :class="{ on: !kind }" @click="kind = ''">全部</button>
        <button v-for="(l, k) in KINDS" :key="k" :class="{ on: kind === k }" @click="kind = k">{{ l }}</button>
      </div>
      <span class="small faint">共 {{ items.length }} 张</span>
      <span class="spacer" />
      <input ref="fileInput" type="file" accept=".json,application/json" hidden @change="importFile" />
      <button @click="fileInput.click()"><Upload :size="15" />导入 JSON</button>
      <button class="primary" @click="creating = true"><Plus :size="15" />新建图表</button>
    </div>

    <div v-if="!loading && !items.length" class="dgl-empty">
      <Workflow :size="34" class="faint" />
      <h3>还没有图表</h3>
      <p class="muted small">画剧情流程、角色关系草图或者出图工作流，都保存在 Front 里，随时导出 PNG / SVG / JSON。</p>
      <button class="primary" @click="creating = true"><Plus :size="15" />从模板开始</button>
    </div>

    <div v-reveal class="dgl-grid">
      <RouterLink v-for="d in items" :key="d.id" :to="`/diagrams/${d.id}`" class="dgl-card">
        <div class="dgl-thumb">
          <img v-if="!broken.has(d.id)" :src="preview(d)" :alt="d.title" loading="lazy" @error="broken = new Set([...broken, d.id])" />
          <component :is="ICON[d.kind]" v-else :size="30" class="faint" />
          <div class="dgl-actions" @click.prevent>
            <button class="iconbtn" title="复制" @click.prevent="duplicate(d)"><Copy :size="14" /></button>
            <button class="iconbtn danger" title="删除" @click.prevent="remove(d)"><Trash2 :size="14" /></button>
          </div>
        </div>
        <div class="dgl-meta">
          <div class="row" style="gap:6px"><Pin v-if="d.pinned" :size="12" class="accent" /><b class="ellip">{{ d.title }}</b></div>
          <div class="row small muted" style="gap:8px"><span class="badge"><component :is="ICON[d.kind]" :size="11" />{{ KINDS[d.kind] }}</span>{{ d.nodes }} 节点 · {{ d.edges }} 连线<span class="spacer" /><span class="faint">{{ when(d.updated_at) }}</span></div>
        </div>
      </RouterLink>
    </div>

    <Modal v-if="creating" title="新建图表" wide @close="creating = false; router.replace('/diagrams')">
      <div class="dgl-tpls">
        <button v-for="t in templates" :key="t.id" class="dgl-tpl" @click="create(t)">
          <span class="dgl-tpl-art"><component :is="TPL_ART[t.id] || Shapes" :size="26" /></span>
          <b>{{ t.title }}</b>
          <span class="small muted">{{ KINDS[t.kind] }} · {{ t.description }}</span>
          <span class="small faint">{{ t.data.nodes.length ? `${t.data.nodes.length} 个节点` : '空白' }}</span>
        </button>
      </div>
      <p class="small faint" style="margin:14px 0 0">模板内容均为原创示例，新建后可以随意修改。</p>
    </Modal>
  </div>
</template>

<style scoped>
.dgl-head { gap: 12px; margin-bottom: 16px; }
.dgl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.dgl-card { display: grid; gap: 10px; color: inherit; text-decoration: none; }
.dgl-thumb { position: relative; aspect-ratio: 16 / 10; border-radius: 14px; overflow: hidden; display: grid; place-items: center;
  background: var(--sunken); border: 1px solid var(--line); transition: border-color .15s var(--ease-out), transform .2s var(--ease-out); }
.dgl-thumb img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; padding: 10px; }
.dgl-card:hover .dgl-thumb { border-color: var(--accent); }
.dgl-actions { position: absolute; top: 8px; right: 8px; display: flex; gap: 4px; opacity: 0; transition: opacity .15s var(--ease-out); }
.dgl-card:hover .dgl-actions, .dgl-card:focus-visible .dgl-actions { opacity: 1; }
.dgl-actions button { background: var(--chrome); backdrop-filter: blur(10px); }
.dgl-meta { display: grid; gap: 4px; padding: 0 2px; }
.dgl-meta .badge { display: inline-flex; align-items: center; gap: 4px; }
.accent { color: var(--accent); }
.dgl-empty { display: grid; justify-items: center; gap: 8px; padding: 70px 20px; text-align: center; }
.dgl-empty h3 { margin: 6px 0 0; }
.dgl-empty p { max-width: 420px; margin: 0 0 8px; }
.dgl-tpls { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.dgl-tpl { flex-direction: column; align-items: flex-start; gap: 6px; padding: 16px; border-radius: 14px; white-space: normal; text-align: left; background: var(--panel2); }
.dgl-tpl:hover { border-color: var(--accent); }
.dgl-tpl-art { display: grid; place-items: center; width: 48px; height: 48px; border-radius: 12px; background: var(--accent-soft); color: var(--accent); margin-bottom: 4px; }
@media (max-width: 900px) { .dgl-tpls { grid-template-columns: 1fr 1fr; } }
</style>
