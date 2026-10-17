<script setup>
// 添加游戏 / 匹配元数据：在 Bangumi / VNDB / 月幕 里搜索，选一条后预览混合补全的结果，再加入游戏库
import { computed, onMounted, ref } from 'vue'
import { Search, Check, CircleAlert, Minus, ExternalLink, ArrowLeft, Loader2 } from 'lucide-vue-next'
import { api, Works } from '../api'
import { guard } from '../toast'
import Modal from './Modal.vue'
import { SOURCES, STATUS, year } from '../galgame/defs'

const props = defineProps({ matchFor: { type: Object, default: null }, initial: { type: String, default: '' } })
const emit = defineEmits(['close', 'added'])

const q = ref(props.initial || props.matchFor?.original || props.matchFor?.title || '')
const only = ref('')
const res = ref(null)
const searching = ref(false)
const picked = ref(null)
const preview = ref(null)
const loadingPreview = ref(false)
const works = ref([])
const opts = ref({ status: 'wishlist', work: 'new', save_cover: true, import_characters: false })
const busy = ref(false)
const cfg = ref(null)
const input = ref(null)

onMounted(async () => {
  cfg.value = await api.get('/api/galgames/meta/settings')
  works.value = (await Works.list({ kind: 'galgame', limit: 500 })).items
  input.value?.focus()
  if (q.value) run()
})

async function run() {
  if (!q.value.trim()) return
  searching.value = true
  picked.value = null
  preview.value = null
  try { res.value = await guard(() => api.get('/api/galgames/meta/search', { q: q.value.trim(), source: only.value || undefined })) } finally { searching.value = false }
}
const columns = computed(() => (res.value ? res.value.order.map((s) => ({ s, ...res.value.results[s] })).filter((c) => c.ok !== undefined) : []))
const total = computed(() => columns.value.reduce((n, c) => n + c.items.length, 0))

async function pick(item) {
  picked.value = item
  preview.value = null
  loadingPreview.value = true
  try {
    preview.value = await guard(() => api.post('/api/galgames/meta/preview', { picks: { [item.source]: item.sid }, auto_match: props.matchFor ? false : undefined }))
    const exist = works.value.find((w) => w.title === preview.value.merged.title)
    opts.value.work = exist ? exist.id : 'new'
  } catch { picked.value = null } finally { loadingPreview.value = false }
}

async function add() {
  busy.value = true
  try {
    let g
    if (props.matchFor) {
      g = await guard(() => api.post(`/api/galgames/${props.matchFor.id}/match`, { source: picked.value.source, sid: picked.value.sid, save_cover: opts.value.save_cover }), '已关联元数据')
    } else {
      const body = { picks: { [picked.value.source]: picked.value.sid }, ...opts.value, work: opts.value.work === 'none' ? null : opts.value.work }
      g = await guard(() => api.post('/api/galgames/from-meta', body), '已加入游戏库')
    }
    emit('added', g)
  } finally { busy.value = false }
}
const m = computed(() => preview.value?.merged)
const srcRows = computed(() => {
  if (!preview.value) return []
  return (cfg.value?.order || Object.keys(SOURCES)).map((s) => {
    const d = preview.value.details[s]
    const err = preview.value.errors[s]
    const mt = preview.value.matched[s]
    const how = picked.value.source === s ? '选中' : mt?.sid ? `自动匹配 · 相似度 ${Math.round(mt.score * 100)}%` : ''
    return { s, d, err, how, none: !d && !err }
  })
})
</script>

<template>
  <Modal :title="matchFor ? `匹配元数据 · ${matchFor.title}` : '添加游戏'" wide @close="emit('close')">
    <div v-if="!picked" class="gad">
      <form class="row gad-bar" @submit.prevent="run">
        <div class="gad-q"><Search :size="15" class="faint" /><input ref="input" v-model="q" placeholder="游戏名、原名或别名…" maxlength="95" /></div>
        <div class="seg" role="tablist" aria-label="来源">
          <button type="button" :class="{ on: !only }" @click="only = ''; run()">{{ cfg?.mode === 'mixed' ? '混合' : '自动' }}</button>
          <button v-for="(s, k) in SOURCES" :key="k" type="button" :class="{ on: only === k }" @click="only = k; run()">{{ s.short }}</button>
        </div>
        <button class="primary" :disabled="searching"><Loader2 v-if="searching" :size="15" class="spin" /><Search v-else :size="15" />搜索</button>
      </form>
      <p v-if="cfg && !cfg.online" class="small warn">联网元数据已关闭（FRONT_GALGAME=off），只能手动添加。</p>
      <div v-if="res" class="gad-cols" :style="{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }">
        <section v-for="c in columns" :key="c.s" class="gad-col">
          <header class="row"><i class="dot" :style="{ background: SOURCES[c.s].color }" /><b>{{ SOURCES[c.s].label }}</b><span class="spacer" />
            <span v-if="c.ok" class="small faint">{{ c.items.length }} 条 · {{ c.ms }}ms</span><span v-else class="small danger-t">失败</span></header>
          <p v-if="!c.ok" class="small danger-t gad-err"><CircleAlert :size="13" />{{ c.error }}</p>
          <p v-else-if="!c.items.length" class="small faint gad-err">没有结果</p>
          <button v-for="it in c.items" :key="it.sid" class="gad-item" @click="pick(it)">
            <span class="gad-cover" :style="it.cover ? { backgroundImage: `url(${it.cover})` } : {}" :class="{ nsfw: it.nsfw && cfg?.blur_nsfw }" />
            <span class="gad-txt">
              <b class="ellip">{{ it.title }}</b>
              <span v-if="it.original && it.original !== it.title" class="small muted ellip">{{ it.original }}</span>
              <span class="small faint ellip">{{ [year(it.date), it.developer].filter(Boolean).join(' · ') }}</span>
              <span class="row" style="gap:6px">
                <span v-if="it.score" class="badge">★ {{ it.score }}</span>
                <span v-if="it.nsfw" class="badge ai">R18</span>
                <span v-if="it.in_library" class="badge ok-b">已在库</span>
              </span>
            </span>
          </button>
        </section>
      </div>
      <p v-if="res && !total" class="muted small" style="margin:14px 0 0">都没有找到，可以换原名 / 罗马音再试，或者直接在游戏库里“手动添加”。</p>
    </div>

    <div v-else class="gad-pv">
      <button class="ghost small" @click="picked = null"><ArrowLeft :size="14" />返回结果</button>
      <div v-if="loadingPreview" class="gad-loading"><Loader2 :size="20" class="spin" />正在从各来源拉取并互相补全…</div>
      <div v-else-if="m" class="gad-merged">
        <div class="gad-big" :style="m.cover_url ? { backgroundImage: `url(${m.cover_url})` } : {}" :class="{ nsfw: m.nsfw && cfg?.blur_nsfw }" />
        <div class="grid" style="gap:10px;align-content:start">
          <div>
            <h3 style="margin:0">{{ m.title }}</h3>
            <div v-if="m.original && m.original !== m.title" class="muted">{{ m.original }}</div>
            <div class="small faint">{{ [m.developer, m.release_date, m.platforms.slice(0, 4).join(' / ')].filter(Boolean).join(' · ') }}</div>
          </div>
          <p class="small muted gad-desc">{{ m.description }}</p>
          <div class="gad-src">
            <div v-for="r in srcRows" :key="r.s" class="row">
              <i class="dot" :style="{ background: SOURCES[r.s].color }" /><b style="min-width:94px">{{ SOURCES[r.s].label }}</b>
              <template v-if="r.d"><Check :size="14" class="ok-t" /><span class="small ellip">{{ r.d.title }}</span><span class="small faint">{{ r.how }}</span>
                <span class="spacer" /><span v-if="r.d.score" class="badge">★ {{ r.d.score }}</span><a :href="r.d.url" target="_blank" rel="noopener noreferrer" class="iconbtn small" title="打开来源页面"><ExternalLink :size="13" /></a></template>
              <template v-else-if="r.err"><CircleAlert :size="14" class="danger-t" /><span class="small danger-t">{{ r.err }}</span></template>
              <template v-else><Minus :size="14" class="faint" /><span class="small faint">{{ matchFor ? '保持原样' : '没有找到同一部作品' }}</span></template>
            </div>
          </div>
          <template v-if="!matchFor">
            <div class="row" style="gap:8px"><span class="small muted">状态</span>
              <div class="seg"><button v-for="(s, k) in STATUS" :key="k" :class="{ on: opts.status === k }" @click="opts.status = k">{{ s.label }}</button></div></div>
            <label class="row small" style="gap:8px"><span class="muted">关联作品</span>
              <select v-model="opts.work" style="max-width:260px"><option value="new">新建作品（CG 档案挂在这里）</option><option v-for="w in works" :key="w.id" :value="w.id">{{ w.title }}</option><option value="none">不关联</option></select></label>
            <label class="row small" style="gap:6px"><input v-model="opts.import_characters" type="checkbox" :disabled="opts.work === 'none'" />把 {{ m.characters.length }} 个角色导入角色百科</label>
          </template>
          <label class="row small" style="gap:6px"><input v-model="opts.save_cover" type="checkbox" />把封面保存到本地</label>
          <div class="row"><span class="spacer" /><button class="primary" :disabled="busy" @click="add"><Loader2 v-if="busy" :size="15" class="spin" />{{ matchFor ? '关联这个条目' : '加入游戏库' }}</button></div>
        </div>
      </div>
    </div>
    <p class="small faint gad-foot">元数据来自 Bangumi、VNDB、月幕 Galgame 的公开接口，只在你搜索 / 添加 / 刷新时联网；Front 不提供任何游戏下载。</p>
  </Modal>
</template>

<style scoped>
.gad-bar { gap: 10px; flex-wrap: nowrap; }
.gad-q { flex: 1; display: flex; align-items: center; gap: 8px; padding: 0 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--sunken); }
.gad-q input { border: 0; background: transparent; padding: 9px 0; flex: 1; outline: none; box-shadow: none; }
.gad-cols { display: grid; gap: 12px; margin-top: 14px; max-height: 56vh; overflow: auto; }
.gad-col { display: grid; gap: 6px; align-content: start; min-width: 0; }
.gad-col header { gap: 8px; padding: 2px 4px 6px; border-bottom: 1px solid var(--line); position: sticky; top: 0; background: var(--panel); z-index: 1; }
.dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; flex: none; }
.gad-err { display: flex; gap: 6px; align-items: center; margin: 6px 4px; }
.gad-item { display: grid; grid-template-columns: 52px 1fr; gap: 10px; padding: 8px; border-radius: 12px; text-align: left; white-space: normal; background: transparent; border: 1px solid transparent; align-items: start; }
.gad-item:hover { background: var(--panel2); border-color: var(--line-strong); }
.gad-cover { width: 52px; aspect-ratio: 3 / 4; border-radius: 8px; background: var(--sunken) center / cover; }
.gad-txt { display: grid; gap: 2px; min-width: 0; }
.nsfw { filter: blur(10px) saturate(.6); }
.gad-pv { display: grid; gap: 12px; }
.gad-loading { display: flex; gap: 10px; align-items: center; padding: 50px; justify-content: center; color: var(--muted); }
.gad-merged { display: grid; grid-template-columns: 200px 1fr; gap: 20px; }
.gad-big { width: 200px; aspect-ratio: 3 / 4; border-radius: 14px; background: var(--sunken) center / cover; box-shadow: var(--shadow); }
.gad-desc { margin: 0; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; white-space: pre-line; }
.gad-src { display: grid; gap: 6px; padding: 10px 12px; border-radius: 12px; background: var(--panel2); }
.gad-src .row { gap: 8px; flex-wrap: nowrap; min-width: 0; min-height: 28px; }
.gad-src a.iconbtn { width: 26px; height: 26px; display: inline-grid; place-items: center; }
.gad-foot { margin: 14px 0 0; }
.ok-t { color: var(--ok); }
.danger-t { color: var(--danger); }
.warn { color: var(--warn); }
.ok-b { color: var(--ok); border-color: color-mix(in oklab, var(--ok) 40%, transparent); }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spin { animation: none; } }
</style>
