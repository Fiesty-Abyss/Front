<script setup>
// galgame 游戏库：按游玩状态 / 来源筛选、排序、搜索（含原名与别名），NSFW 封面默认模糊
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, ListPlus, Search, Eye, EyeOff, Pin, SquareLibrary, Clock, Star, PenLine } from 'lucide-vue-next'
import { api, Galgames } from '../api'
import { guard } from '../toast'
import GalAddDialog from '../components/GalAddDialog.vue'
import GalBatchDialog from '../components/GalBatchDialog.vue'
import { STATUS, SOURCES, SORTS, coverUrl, fmtMinutes, tint, year } from '../galgame/defs'

const route = useRoute()
const router = useRouter()
const items = ref([])
const total = ref(0)
const stats = ref(null)
const cfg = ref(null)
const loading = ref(true)
const f = ref({ status: route.query.status || '', source: '', sort: 'updated', q: '' })
const adding = ref(route.query.add === '1')
const batch = ref(false)
const reveal = ref(false)

async function load() {
  loading.value = true
  const p = { limit: 500, sort: f.value.sort, status: f.value.status || undefined, source: f.value.source || undefined, q: f.value.q.trim() || undefined }
  const r = await Galgames.list(p)
  items.value = r.items
  total.value = r.total
  loading.value = false
}
async function loadStats() { stats.value = await api.get('/api/galgames/stats/summary') }
let t
watch(() => f.value.q, () => { clearTimeout(t); t = setTimeout(load, 250) })
watch(() => [f.value.status, f.value.source, f.value.sort], load)
onMounted(async () => { cfg.value = await api.get('/api/galgames/meta/settings'); await guard(() => Promise.all([load(), loadStats()])) })

function added(g) { adding.value = false; router.push(`/galgames/${g.id}`) }
async function manual() {
  const title = prompt('游戏名（之后可以在详情页匹配元数据）')
  if (!title?.trim()) return
  const g = await guard(() => Galgames.create({ title: title.trim() }), '已添加')
  router.push(`/galgames/${g.id}`)
}
const blur = (g) => g.nsfw && cfg.value?.blur_nsfw !== false && !reveal.value
const tiles = computed(() => [['', '全部', stats.value?.total ?? 0, 'var(--accent)'], ...Object.entries(STATUS).map(([k, s]) => [k, s.label, stats.value?.by_status[k]?.count ?? 0, s.color])])
const hasNsfw = computed(() => items.value.some((g) => g.nsfw))
function closeAdd() { adding.value = false; if (route.query.add) router.replace('/galgames') }
</script>

<template>
  <div class="gl">
    <div class="gl-stats">
      <button v-for="[k, l, n, c] in tiles" :key="k" class="gl-stat" :class="{ on: f.status === k }" :style="{ '--c': c }" @click="f.status = k">
        <span class="gl-stat-n">{{ n }}</span><span class="small"><i class="dot" />{{ l }}</span>
      </button>
      <div class="gl-stat gl-sum">
        <span class="row small muted" style="gap:6px"><Clock :size="13" />总游玩 {{ fmtMinutes(stats?.minutes) }}</span>
        <span class="row small muted" style="gap:6px"><Star :size="13" />平均评分 {{ stats?.rated ? stats.rated.toFixed(1) : '—' }}</span>
      </div>
    </div>

    <div class="row gl-bar">
      <div class="gl-q"><Search :size="15" class="faint" /><input v-model="f.q" placeholder="搜索标题、原名、别名、品牌、笔记…" /></div>
      <select v-model="f.source" aria-label="来源"><option value="">全部来源</option><option v-for="(s, k) in SOURCES" :key="k" :value="k">{{ s.label }}</option><option value="none">未匹配元数据</option></select>
      <select v-model="f.sort" aria-label="排序"><option v-for="(l, k) in SORTS" :key="k" :value="k">{{ l }}</option></select>
      <button v-if="hasNsfw" class="iconbtn" :title="reveal ? '重新模糊 R18 封面' : '显示 R18 封面'" @click="reveal = !reveal"><EyeOff v-if="reveal" :size="15" /><Eye v-else :size="15" /></button>
      <span class="spacer" />
      <button class="ghost" @click="manual"><PenLine :size="15" />手动添加</button>
      <button @click="batch = true"><ListPlus :size="15" />批量添加</button>
      <button class="primary" @click="adding = true"><Plus :size="15" />添加游戏</button>
    </div>

    <div v-if="!loading && !items.length" class="gl-empty">
      <SquareLibrary :size="34" class="faint" />
      <h3>{{ f.q || f.status || f.source ? '没有符合条件的游戏' : '游戏库还是空的' }}</h3>
      <p class="muted small">从 Bangumi、VNDB、月幕 Galgame 搜索并添加游戏，元数据会自动互相补全；记录游玩状态、评分和时长，CG 档案挂在对应作品下。</p>
      <button class="primary" @click="adding = true"><Plus :size="15" />添加游戏</button>
    </div>

    <div v-reveal class="gl-grid">
      <RouterLink v-for="g in items" :key="g.id" :to="`/galgames/${g.id}`" class="gl-card">
        <div class="gl-cover" :style="coverUrl(g) ? {} : { backgroundImage: tint(g.title) }">
          <img v-if="coverUrl(g)" :src="coverUrl(g)" :alt="g.title" loading="lazy" :class="{ blur: blur(g) }" />
          <span v-else class="gl-initial">{{ g.title.replace('【示例】', '').slice(0, 1) }}</span>
          <span v-if="blur(g)" class="gl-r18">R18 · 已模糊</span>
          <span class="gl-status" :style="{ '--c': STATUS[g.status].color }">{{ STATUS[g.status].label }}</span>
          <span v-if="g.my_rating" class="gl-rate">{{ g.my_rating }}</span>
          <span class="gl-src"><i v-for="(s, k) in SOURCES" v-show="g.sources[k]" :key="k" :style="{ background: s.color }" :title="s.label" /></span>
        </div>
        <div class="gl-meta">
          <div class="row" style="gap:5px;flex-wrap:nowrap"><Pin v-if="g.pinned" :size="12" class="accent" /><b class="ellip">{{ g.title }}</b></div>
          <div class="small muted ellip">{{ [g.developer, year(g.release_date)].filter(Boolean).join(' · ') || '未匹配元数据' }}</div>
          <div v-if="g.play_minutes" class="small faint">{{ fmtMinutes(g.play_minutes) }}</div>
        </div>
      </RouterLink>
    </div>

    <GalAddDialog v-if="adding" @close="closeAdd" @added="added" />
    <GalBatchDialog v-if="batch" @close="batch = false" @done="load(); loadStats()" />
  </div>
</template>

<style scoped>
.gl-stats { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)) 1.4fr; gap: 10px; margin-bottom: 16px; }
.gl-stat { display: grid; gap: 2px; justify-items: start; padding: 12px 14px; border-radius: 14px; background: var(--panel); border: 1px solid var(--line); text-align: left; box-shadow: var(--shadow); }
.gl-stat:hover { border-color: var(--line-strong); }
.gl-stat.on { border-color: var(--c); background: color-mix(in oklab, var(--c) 10%, var(--panel)); }
.gl-stat-n { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.2; }
.gl-stat .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--c); margin-right: 6px; vertical-align: 1px; }
.gl-sum { align-content: center; gap: 6px; cursor: default; }
.gl-bar { gap: 10px; margin-bottom: 18px; flex-wrap: wrap; }
.gl-q { display: flex; align-items: center; gap: 8px; padding: 0 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel); min-width: 300px; }
.gl-q input { border: 0; background: transparent; padding: 8px 0; flex: 1; outline: none; box-shadow: none; }
.gl-bar select { width: auto; }
.gl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 20px 16px; }
.gl-card { display: grid; gap: 9px; color: inherit; text-decoration: none; }
.gl-cover { position: relative; aspect-ratio: 3 / 4; border-radius: 14px; overflow: hidden; background: var(--sunken) center / cover; border: 1px solid var(--line);
  box-shadow: var(--shadow); transition: transform .25s var(--ease-out), box-shadow .25s var(--ease-out), border-color .15s; display: grid; place-items: center; }
.gl-card:hover .gl-cover, .gl-card:focus-visible .gl-cover { transform: translateY(-3px); border-color: var(--accent); box-shadow: var(--shadow-pop); }
.gl-cover img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transition: filter .2s; }
.gl-cover img.blur { filter: blur(16px) saturate(.6); transform: scale(1.1); }
.gl-initial { font-size: 54px; font-weight: 700; color: rgba(255, 255, 255, .85); }
.gl-r18 { position: absolute; font-size: 12px; padding: 3px 10px; border-radius: 99px; background: rgba(0, 0, 0, .55); color: #fff; }
.gl-status { position: absolute; left: 8px; top: 8px; font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 99px; color: #fff;
  background: color-mix(in oklab, var(--c) 78%, #000); box-shadow: 0 2px 8px rgba(0, 0, 0, .3); }
.gl-rate { position: absolute; right: 8px; top: 8px; min-width: 26px; height: 26px; display: grid; place-items: center; border-radius: 8px; font-weight: 700; font-size: 13px;
  background: rgba(0, 0, 0, .55); color: #ffd36b; backdrop-filter: blur(6px); }
.gl-src { position: absolute; right: 8px; bottom: 8px; display: flex; gap: 4px; padding: 4px 6px; border-radius: 99px; background: rgba(0, 0, 0, .45); }
.gl-src i { width: 7px; height: 7px; border-radius: 50%; }
.gl-meta { display: grid; gap: 1px; padding: 0 2px; }
.accent { color: var(--accent); }
.gl-empty { display: grid; justify-items: center; gap: 8px; padding: 70px 20px; text-align: center; }
.gl-empty h3 { margin: 6px 0 0; }
.gl-empty p { max-width: 460px; margin: 0 0 8px; }
@media (max-width: 1100px) { .gl-stats { grid-template-columns: repeat(3, 1fr); } }
@media (prefers-reduced-motion: reduce) { .gl-cover { transition: none; } .gl-card:hover .gl-cover { transform: none; } }
</style>
