<script setup>
// 分享足迹：把玩过的作品排成一张图片（只在本机生成 PNG，不上传）。可排序、逐款选择、遮盖封面
import { computed, onMounted, ref } from 'vue'
import { toPng } from 'html-to-image'
import { Download, Copy, ArrowDownWideNarrow, ArrowUpWideNarrow, Loader2 } from 'lucide-vue-next'
import { api, Galgames } from '../api'
import { guard, toast } from '../toast'
import Modal from './Modal.vue'
import { STATUS, coverUrl, fmtMinutes, tint } from '../galgame/defs'

const emit = defineEmits(['close'])
const all = ref([])
const hidden = ref(new Set())
const masked = ref(new Set())
const sort = ref('playtime')
const desc = ref(true)
const maskAll = ref(false)
const title = ref('我的游玩足迹')
const card = ref(null)
const busy = ref(false)
const cfg = ref(null)
const q = ref('')

onMounted(async () => {
  cfg.value = await api.get('/api/galgames/meta/settings')
  all.value = (await Galgames.list({ limit: 500 })).items.filter((g) => !['unplayed', 'wishlist'].includes(g.status) || g.play_minutes > 0)
  if (cfg.value.blur_nsfw) masked.value = new Set(all.value.filter((g) => g.nsfw).map((g) => g.id))
})
const KEY = { recent: (g) => g.updated_at, playtime: (g) => g.play_minutes || 0, rating: (g) => g.my_rating || 0, title: (g) => g.title, release: (g) => g.release_date || '' }
const sorted = computed(() => {
  const k = KEY[sort.value]
  return [...all.value].sort((a, b) => (k(a) > k(b) ? 1 : k(a) < k(b) ? -1 : 0) * (desc.value ? -1 : 1))
})
const listed = computed(() => sorted.value.filter((g) => !q.value || [g.title, g.original].some((t) => t?.toLowerCase().includes(q.value.toLowerCase()))))
const shown = computed(() => sorted.value.filter((g) => !hidden.value.has(g.id)))
const totals = computed(() => ({ n: shown.value.length, min: shown.value.reduce((n, g) => n + (g.play_minutes || 0), 0), done: shown.value.filter((g) => g.status === 'finished').length }))
const toggle = (set, id) => { const s = new Set(set.value); s.has(id) ? s.delete(id) : s.add(id); set.value = s }
const showCover = (g) => coverUrl(g) && !maskAll.value && !masked.value.has(g.id)

async function render() {
  const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() || '#15151f'
  return toPng(card.value, { pixelRatio: 2, backgroundColor: bg, cacheBust: true })
}
async function save() {
  busy.value = true
  try {
    const url = await guard(render)
    const a = document.createElement('a')
    a.href = url
    a.download = `front-游玩足迹-${new Date().toISOString().slice(0, 10)}.png`
    a.click()
    toast('已保存图片')
  } finally { busy.value = false }
}
async function copy() {
  busy.value = true
  try {
    const blob = await (await fetch(await guard(render))).blob()
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
    toast('已复制到剪贴板')
  } catch (e) { toast('浏览器不允许复制图片，请改用“保存 PNG”', true) } finally { busy.value = false }
}
const SORTS = { playtime: '游玩时长', recent: '最近更新', rating: '我的评分', title: '名称', release: '发售日' }
</script>

<template>
  <Modal title="分享游玩足迹" wide @close="emit('close')">
    <div class="gsh">
      <aside class="gsh-side">
        <label class="field">标题<input v-model="title" maxlength="40" /></label>
        <div class="row" style="gap:6px;flex-wrap:nowrap">
          <select v-model="sort" aria-label="排序"><option v-for="(l, k) in SORTS" :key="k" :value="k">{{ l }}</option></select>
          <button class="iconbtn" :title="desc ? '降序' : '升序'" @click="desc = !desc"><ArrowDownWideNarrow v-if="desc" :size="15" /><ArrowUpWideNarrow v-else :size="15" /></button>
        </div>
        <label class="row small" style="gap:6px"><input v-model="maskAll" type="checkbox" />全部用统一图案遮盖封面</label>
        <input v-model="q" placeholder="按名称 / 原名查找…" />
        <div class="gsh-list">
          <div v-for="g in listed" :key="g.id" class="row gsh-row">
            <input type="checkbox" :checked="!hidden.has(g.id)" :aria-label="`展示 ${g.title}`" @change="toggle(hidden, g.id)" />
            <span class="ellip" style="flex:1">{{ g.title }}</span>
            <button class="small ghost" :class="{ on: masked.has(g.id) }" @click="toggle(masked, g.id)">{{ masked.has(g.id) ? '已遮盖' : '遮盖' }}</button>
          </div>
        </div>
        <p class="small faint" style="margin:0">只算玩过的作品（有时长，或状态是在玩 / 玩过 / 搁置 / 弃坑）。图片在本机生成，不会上传。</p>
      </aside>
      <div class="gsh-stage">
        <div ref="card" class="gsh-card">
          <header><div><div class="gsh-eyebrow">FRONT · GALGAME</div><h2>{{ title }}</h2></div>
            <div class="gsh-tot"><b>{{ totals.n }}</b><span>部</span><b>{{ totals.done }}</b><span>通关</span><b>{{ Math.round(totals.min / 60) }}</b><span>小时</span></div></header>
          <div class="gsh-grid">
            <div v-for="g in shown" :key="g.id" class="gsh-item">
              <div class="gsh-cover" :style="showCover(g) ? { backgroundImage: `url(${coverUrl(g)})` } : { backgroundImage: tint(g.title) }">
                <span v-if="!showCover(g)" class="gsh-mask">{{ g.title.replace('【示例】', '').slice(0, 1) }}</span>
                <span class="gsh-st" :style="{ background: STATUS[g.status].color }">{{ STATUS[g.status].label }}</span>
                <span v-if="g.my_rating" class="gsh-rt">{{ g.my_rating }}</span>
              </div>
              <b class="ellip">{{ g.title }}</b>
              <span v-if="g.original && g.original !== g.title" class="ellip gsh-orig">{{ g.original }}</span>
              <span class="gsh-time">{{ fmtMinutes(g.play_minutes) }}</span>
            </div>
          </div>
          <footer>由 Front 生成 · {{ new Date().toLocaleDateString('zh-CN') }}</footer>
        </div>
      </div>
    </div>
    <div class="row" style="margin-top:14px"><span class="small faint">{{ shown.length }} 部作品</span><span class="spacer" />
      <button :disabled="busy || !shown.length" @click="copy"><Copy :size="15" />复制图片</button>
      <button class="primary" :disabled="busy || !shown.length" @click="save"><Loader2 v-if="busy" :size="15" class="spin" /><Download v-else :size="15" />保存 PNG</button></div>
  </Modal>
</template>

<style scoped>
.gsh { display: grid; grid-template-columns: 250px 1fr; gap: 16px; min-height: 0; }
.gsh-side { display: grid; gap: 10px; align-content: start; }
.gsh-list { display: grid; gap: 2px; max-height: 300px; overflow: auto; border: 1px solid var(--line); border-radius: 10px; padding: 4px; }
.gsh-row { gap: 8px; flex-wrap: nowrap; padding: 4px 6px; font-size: 13px; }
.gsh-row button.on { color: var(--warn); }
.gsh-stage { max-height: 62vh; overflow: auto; border-radius: 14px; background: var(--sunken); padding: 14px; }
.gsh-card { width: 720px; margin: 0 auto; padding: 26px; border-radius: 18px; background: linear-gradient(160deg, color-mix(in oklab, var(--accent) 18%, var(--panel)), var(--panel) 45%); color: var(--text); }
.gsh-card header { display: flex; justify-content: space-between; align-items: end; margin-bottom: 18px; }
.gsh-card h2 { margin: 2px 0 0; font-size: 24px; }
.gsh-eyebrow { font-size: 11px; letter-spacing: .18em; color: var(--accent-hi); font-weight: 700; }
.gsh-tot { display: flex; align-items: baseline; gap: 4px; }
.gsh-tot b { font-size: 22px; margin-left: 10px; font-variant-numeric: tabular-nums; }
.gsh-tot span { font-size: 12px; color: var(--muted); }
.gsh-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px 12px; }
.gsh-item { display: grid; gap: 2px; min-width: 0; font-size: 12px; }
.gsh-cover { position: relative; aspect-ratio: 3 / 4; border-radius: 10px; background: center / cover; margin-bottom: 4px; display: grid; place-items: center; overflow: hidden; }
.gsh-mask { font-size: 32px; font-weight: 700; color: rgba(255, 255, 255, .8); }
.gsh-st { position: absolute; left: 6px; top: 6px; font-size: 10px; padding: 1px 7px; border-radius: 99px; color: #10101a; font-weight: 700; }
.gsh-rt { position: absolute; right: 6px; top: 6px; font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 6px; background: rgba(0, 0, 0, .6); color: #ffd36b; }
.gsh-orig { color: var(--muted); font-size: 11px; }
.gsh-time { color: var(--accent-hi); font-size: 11px; font-weight: 600; }
.gsh-card footer { margin-top: 18px; font-size: 11px; color: var(--faint); text-align: right; }
.spin { animation: spin 1s linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }
</style>
