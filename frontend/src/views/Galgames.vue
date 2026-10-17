<script setup>
// galgame 游戏库：“继续游玩”横幅与游玩日历、按状态 / 来源 / 品牌筛选、网格 / 列表视图、批量操作、随机挑一款、导出与分享足迹
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, ListPlus, Search, Eye, EyeOff, Pin, SquareLibrary, Clock, Star, PenLine, LayoutGrid, List, Dices, SquareCheck, Download, Share2, Trash2, X, Play, History } from 'lucide-vue-next'
import { api, Galgames } from '../api'
import { guard, toast } from '../toast'
import GalAddDialog from '../components/GalAddDialog.vue'
import GalBatchDialog from '../components/GalBatchDialog.vue'
import GalShareDialog from '../components/GalShareDialog.vue'
import GalPlayCalendar from '../components/GalPlayCalendar.vue'
import { STATUS, SOURCES, SORTS, coverUrl, fmtMinutes, tint, year } from '../galgame/defs'

const route = useRoute()
const router = useRouter()
const items = ref([])
const stats = ref(null)
const plays = ref(null)
const playing = ref([])
const cur = ref(0)
const cfg = ref(null)
const loading = ref(true)
const f = ref({ status: route.query.status || '', source: '', developer: '', sort: 'updated', q: '' })
const view = ref(localStorage.getItem('front.gal.view') || 'grid')
const adding = ref(route.query.add === '1')
const batch = ref(false)
const sharing = ref(false)
const reveal = ref(false)
const selecting = ref(false)
const picked = ref(new Set())
watch(view, (v) => localStorage.setItem('front.gal.view', v))

async function load() {
  loading.value = true
  const p = { limit: 500, sort: f.value.sort, status: f.value.status || undefined, source: f.value.source || undefined, developer: f.value.developer || undefined, q: f.value.q.trim() || undefined }
  items.value = (await Galgames.list(p)).items
  loading.value = false
}
async function loadSide() {
  ;[stats.value, plays.value, playing.value] = await Promise.all([api.get('/api/galgames/stats/summary'), api.get('/api/galgames/plays/summary'),
    Galgames.list({ status: 'playing', sort: 'updated', limit: 8 }).then((r) => r.items)])
  cur.value = Math.min(cur.value, Math.max(0, playing.value.length - 1))
}
let t
watch(() => f.value.q, () => { clearTimeout(t); t = setTimeout(load, 250) })
watch(() => [f.value.status, f.value.source, f.value.developer, f.value.sort], load)
onMounted(async () => { cfg.value = await api.get('/api/galgames/meta/settings'); await guard(() => Promise.all([load(), loadSide()])) })
const refreshAll = () => Promise.all([load(), loadSide()])

function added(g) { adding.value = false; router.push(`/galgames/${g.id}`) }
async function manual() {
  const title = prompt('游戏名（之后可以在详情页匹配元数据）')
  if (!title?.trim()) return
  const g = await guard(() => Galgames.create({ title: title.trim(), status: 'unplayed' }), '已添加')
  router.push(`/galgames/${g.id}`)
}
function random() {
  const pool = items.value.filter((g) => ['unplayed', 'wishlist'].includes(g.status))
  const list = pool.length ? pool : items.value
  if (!list.length) return
  const g = list[Math.floor(Math.random() * list.length)]
  toast(`就玩这个：${g.title}`)
  router.push(`/galgames/${g.id}`)
}
function onCard(e, g) {
  if (!selecting.value) return
  e.preventDefault()
  const s = new Set(picked.value)
  s.has(g.id) ? s.delete(g.id) : s.add(g.id)
  picked.value = s
}
function stopSelect() { selecting.value = false; picked.value = new Set() }
async function bulk(body, msg) {
  if (body.delete && !confirm(`从游戏库删除选中的 ${picked.value.size} 款？关联的作品、角色和 CG 不会被删除。`)) return
  await guard(() => api.post('/api/galgames/bulk', { ids: [...picked.value], ...body }), msg)
  stopSelect()
  refreshAll()
}
const selectAll = () => { picked.value = new Set(items.value.map((g) => g.id)) }

const blur = (g) => g.nsfw && cfg.value?.blur_nsfw !== false && !reveal.value
const tiles = computed(() => [['', '全部', stats.value?.total ?? 0, 'var(--accent)'], ...Object.entries(STATUS).map(([k, s]) => [k, s.label, stats.value?.by_status[k]?.count ?? 0, s.color])])
const hasNsfw = computed(() => items.value.some((g) => g.nsfw))
const hero = computed(() => playing.value[cur.value])
const lastPlayed = (id) => plays.value?.recent.find((p) => p.galgame_id === id)?.played_on
function closeAdd() { adding.value = false; if (route.query.add) router.replace('/galgames') }
function wheel(e) {
  if (playing.value.length < 2) return
  e.preventDefault()
  cur.value = (cur.value + (e.deltaY > 0 ? 1 : -1) + playing.value.length) % playing.value.length
}
</script>

<template>
  <div class="gl">
    <div class="gl-top">
      <section v-if="hero" class="gl-hero" @wheel="wheel">
        <Transition name="gl-fade" mode="out-in"><div :key="hero.id" class="gl-hero-bg" :style="{ backgroundImage: coverUrl(hero) && !blur(hero) ? `url(${coverUrl(hero)})` : tint(hero.title) }" /></Transition>
        <div class="gl-hero-in">
          <div class="gl-hero-txt">
            <span class="eyebrow">继续游玩 · CONTINUE</span>
            <h2 class="ellip">{{ hero.title }}</h2>
            <div class="small muted ellip">{{ [hero.developer, year(hero.release_date)].filter(Boolean).join(' · ') }}</div>
            <div class="row small" style="gap:14px;margin-top:4px"><span class="row" style="gap:5px"><Clock :size="13" />已玩 {{ fmtMinutes(hero.play_minutes) }}</span>
              <span v-if="lastPlayed(hero.id)" class="row muted" style="gap:5px"><History :size="13" />上次 {{ lastPlayed(hero.id) }}</span></div>
            <div class="row" style="gap:8px;margin-top:10px">
              <RouterLink :to="`/galgames/${hero.id}`" class="btn primary"><Play :size="14" />打开</RouterLink>
              <RouterLink :to="{ path: `/galgames/${hero.id}`, query: { tab: 'plays' } }" class="btn"><History :size="14" />记一次游玩</RouterLink>
            </div>
          </div>
          <div class="gl-strip" role="tablist" aria-label="在玩的游戏">
            <button v-for="(g, i) in playing" :key="g.id" class="gl-strip-item" :class="{ on: i === cur }" :title="g.title" :style="coverUrl(g) ? {} : { backgroundImage: tint(g.title) }" @click="cur = i">
              <img v-if="coverUrl(g)" :src="coverUrl(g)" :alt="g.title" :class="{ blur: blur(g) }" />
            </button>
          </div>
        </div>
      </section>
      <section v-else class="gl-hero gl-hero-empty"><div class="gl-hero-in"><div class="gl-hero-txt"><span class="eyebrow">继续游玩 · CONTINUE</span><h2>现在没有在玩的游戏</h2><p class="small muted">把游戏标记为“在玩”，或者记一次游玩，它就会出现在这里。</p>
        <button class="btn" style="justify-self:start" @click="random"><Dices :size="14" />随机挑一款</button></div></div></section>
      <section class="card gl-time">
        <div class="row"><b>游玩时长</b><span class="spacer" /><span class="small faint">手动记录</span></div>
        <div class="gl-time-n">
          <div><b>{{ fmtMinutes(plays?.today) }}</b><span class="small muted">今天</span></div>
          <div><b>{{ fmtMinutes(plays?.week) }}</b><span class="small muted">本周</span></div>
          <div><b>{{ fmtMinutes(plays?.month) }}</b><span class="small muted">本月</span></div>
        </div>
        <GalPlayCalendar :by-day="plays?.by_day || {}" :weeks="17" />
        <div class="row small muted" style="gap:12px"><span class="row" style="gap:5px"><Clock :size="13" />累计 {{ fmtMinutes(stats?.minutes) }}</span><span class="row" style="gap:5px"><Star :size="13" />平均评分 {{ stats?.rated ? stats.rated.toFixed(1) : '—' }}</span></div>
      </section>
    </div>

    <div class="gl-stats">
      <button v-for="[k, l, n, c] in tiles" :key="k" class="gl-stat" :class="{ on: f.status === k }" :style="{ '--c': c }" @click="f.status = k">
        <span class="gl-stat-n">{{ n }}</span><span class="small"><i class="dot" />{{ l }}</span>
      </button>
    </div>

    <div class="row gl-bar">
      <div class="gl-q"><Search :size="15" class="faint" /><input v-model="f.q" placeholder="搜索标题、原名、别名、品牌、笔记…" /></div>
      <select v-model="f.source" aria-label="来源"><option value="">全部来源</option><option v-for="(s, k) in SOURCES" :key="k" :value="k">{{ s.label }}</option><option value="none">未匹配元数据</option></select>
      <select v-model="f.developer" aria-label="品牌"><option value="">全部品牌</option><option v-for="d in stats?.developers || []" :key="d.name" :value="d.name">{{ d.name }}（{{ d.count }}）</option></select>
      <select v-model="f.sort" aria-label="排序"><option v-for="(l, k) in SORTS" :key="k" :value="k">{{ l }}</option></select>
      <div class="seg" role="tablist" aria-label="视图"><button :class="{ on: view === 'grid' }" title="网格" @click="view = 'grid'"><LayoutGrid :size="14" /></button><button :class="{ on: view === 'list' }" title="列表" @click="view = 'list'"><List :size="14" /></button></div>
      <button v-if="hasNsfw" class="iconbtn" :title="reveal ? '重新模糊 R18 封面' : '显示 R18 封面'" @click="reveal = !reveal"><EyeOff v-if="reveal" :size="15" /><Eye v-else :size="15" /></button>
      <button class="iconbtn" title="随机挑一款（优先未游玩 / 想玩）" @click="random"><Dices :size="15" /></button>
      <button class="iconbtn" :class="{ on: selecting }" title="多选" @click="selecting ? stopSelect() : (selecting = true)"><SquareCheck :size="15" /></button>
      <span class="spacer" />
      <button class="ghost" @click="sharing = true"><Share2 :size="15" />分享足迹</button>
      <a class="btn ghost" href="/api/galgames/export/file?format=csv" title="导出 CSV（JSON：/api/galgames/export/file?format=json）"><Download :size="15" />导出</a>
      <button class="ghost" @click="manual"><PenLine :size="15" />手动添加</button>
      <button @click="batch = true"><ListPlus :size="15" />批量添加</button>
      <button class="primary" @click="adding = true"><Plus :size="15" />添加游戏</button>
    </div>

    <Transition name="gl-fade">
      <div v-if="selecting" class="row gl-bulk">
        <b>已选 {{ picked.size }} 款</b><button class="small ghost" @click="selectAll">全选</button><button class="small ghost" @click="picked = new Set()">清空</button>
        <span class="spacer" />
        <span class="small muted">改为</span>
        <button v-for="(s, k) in STATUS" :key="k" class="small" :disabled="!picked.size" @click="bulk({ status: k }, `已改为“${s.label}”`)">{{ s.label }}</button>
        <button class="small" :disabled="!picked.size" @click="bulk({ pinned: true }, '已置顶')"><Pin :size="13" />置顶</button>
        <button class="small danger" :disabled="!picked.size" @click="bulk({ delete: true }, '已删除')"><Trash2 :size="13" />删除</button>
        <button class="iconbtn ghost" title="退出多选" @click="stopSelect"><X :size="15" /></button>
      </div>
    </Transition>

    <div v-if="!loading && !items.length" class="gl-empty">
      <SquareLibrary :size="34" class="faint" />
      <h3>{{ f.q || f.status || f.source || f.developer ? '没有符合条件的游戏' : '游戏库还是空的' }}</h3>
      <p class="muted small">从 Bangumi、VNDB、月幕 Galgame 搜索并添加游戏，元数据会自动互相补全；记录游玩状态、评分和时长，CG 档案挂在对应作品下。</p>
      <button class="primary" @click="adding = true"><Plus :size="15" />添加游戏</button>
    </div>

    <div v-if="view === 'grid'" v-reveal class="gl-grid">
      <RouterLink v-for="g in items" :key="g.id" :to="`/galgames/${g.id}`" class="gl-card" :class="{ sel: picked.has(g.id), selecting }" @click="onCard($event, g)">
        <div class="gl-cover" :style="coverUrl(g) ? {} : { backgroundImage: tint(g.title) }">
          <img v-if="coverUrl(g)" :src="coverUrl(g)" :alt="g.title" loading="lazy" :class="{ blur: blur(g) }" />
          <span v-else class="gl-initial">{{ g.title.replace('【示例】', '').slice(0, 1) }}</span>
          <span v-if="blur(g)" class="gl-r18">R18 · 已模糊</span>
          <span class="gl-status" :style="{ '--c': STATUS[g.status].color }">{{ STATUS[g.status].label }}</span>
          <span v-if="g.my_rating" class="gl-rate">{{ g.my_rating }}</span>
          <span class="gl-src"><i v-for="(s, k) in SOURCES" v-show="g.sources[k]" :key="k" :style="{ background: s.color }" :title="s.label" /></span>
          <span v-if="selecting" class="gl-check"><SquareCheck v-if="picked.has(g.id)" :size="18" /></span>
        </div>
        <div class="gl-meta">
          <div class="row" style="gap:5px;flex-wrap:nowrap"><Pin v-if="g.pinned" :size="12" class="accent" /><b class="ellip">{{ g.title }}</b></div>
          <div class="small muted ellip">{{ [g.developer, year(g.release_date)].filter(Boolean).join(' · ') || '未匹配元数据' }}</div>
          <div v-if="g.play_minutes" class="small faint">{{ fmtMinutes(g.play_minutes) }}</div>
        </div>
      </RouterLink>
    </div>
    <div v-else class="card gl-list">
      <RouterLink v-for="g in items" :key="g.id" :to="`/galgames/${g.id}`" class="gl-row" :class="{ sel: picked.has(g.id) }" @click="onCard($event, g)">
        <span v-if="selecting" class="gl-rcheck"><input type="checkbox" :checked="picked.has(g.id)" tabindex="-1" /></span>
        <span class="gl-rcover" :style="coverUrl(g) && !blur(g) ? { backgroundImage: `url(${coverUrl(g)})` } : { backgroundImage: tint(g.title) }" />
        <span class="gl-rtitle"><b class="ellip"><Pin v-if="g.pinned" :size="11" class="accent" /> {{ g.title }}</b><span class="small muted ellip">{{ g.original !== g.title ? g.original : '' }}</span></span>
        <span class="small muted ellip">{{ g.developer || '—' }}</span>
        <span class="small muted">{{ g.release_date || '—' }}</span>
        <span><span class="gl-pill" :style="{ '--c': STATUS[g.status].color }">{{ STATUS[g.status].label }}</span></span>
        <span class="small">{{ g.my_rating ? `★ ${g.my_rating}` : '—' }}</span>
        <span class="small muted">{{ fmtMinutes(g.play_minutes) }}</span>
        <span class="gl-rsrc"><i v-for="(s, k) in SOURCES" v-show="g.sources[k]" :key="k" :style="{ background: s.color }" :title="s.label" /></span>
      </RouterLink>
    </div>

    <GalAddDialog v-if="adding" @close="closeAdd" @added="added" />
    <GalBatchDialog v-if="batch" @close="batch = false" @done="refreshAll" />
    <GalShareDialog v-if="sharing" @close="sharing = false" />
  </div>
</template>

<style scoped>
.gl-top { display: grid; grid-template-columns: 1fr 360px; gap: 16px; margin-bottom: 16px; }
.gl-hero { position: relative; overflow: hidden; border-radius: var(--radius-lg); border: 1px solid var(--line); background: var(--panel); min-height: 250px; box-shadow: var(--shadow); }
.gl-hero-bg { position: absolute; top: 0; bottom: 0; right: 0; width: 72%; background: center 28% / cover; filter: blur(2px) saturate(1.15); opacity: .9;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 40%, #000 75%, transparent); mask-image: linear-gradient(90deg, transparent, #000 40%, #000 75%, transparent); }
.gl-hero::after { content: ''; position: absolute; inset: 0; background: linear-gradient(90deg, var(--panel) 30%, color-mix(in oklab, var(--panel) 55%, transparent) 62%, color-mix(in oklab, var(--panel) 25%, transparent)),
  linear-gradient(0deg, color-mix(in oklab, var(--panel) 70%, transparent), transparent 55%); pointer-events: none; }
.gl-hero-in { position: relative; z-index: 1; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 20px; padding: 22px 24px; height: 100%; align-items: end; }
.gl-hero-txt { display: grid; gap: 4px; align-content: end; min-width: 0; }
.gl-hero-txt h2 { margin: 2px 0 0; font-size: 26px; letter-spacing: -.01em; }
.gl-hero-empty .gl-hero-in { grid-template-columns: 1fr; }
.gl-strip { display: flex; gap: 10px; align-items: end; }
.gl-strip-item { position: relative; width: 74px; aspect-ratio: 3 / 4; padding: 0; border-radius: 10px; overflow: hidden; border: 2px solid transparent; background: center / cover; opacity: .62;
  transition: width .3s var(--ease-out), opacity .2s, border-color .2s; box-shadow: 0 10px 24px -12px rgba(0, 0, 0, .7); }
.gl-strip-item.on { width: 120px; opacity: 1; border-color: var(--accent); }
.gl-strip-item:hover { opacity: 1; }
.gl-strip-item img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.gl-strip-item img.blur { filter: blur(10px); }
.gl-time { display: grid; gap: 12px; align-content: start; }
.gl-time-n { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.gl-time-n div { display: grid; gap: 1px; padding: 8px 10px; border-radius: 10px; background: var(--panel2); }
.gl-time-n b { font-size: 14px; font-variant-numeric: tabular-nums; }
.gl-stats { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px; }
.gl-stat { display: grid; gap: 2px; justify-items: start; padding: 10px 14px; border-radius: 14px; background: var(--panel); border: 1px solid var(--line); text-align: left; box-shadow: var(--shadow); }
.gl-stat:hover { border-color: var(--line-strong); }
.gl-stat.on { border-color: var(--c); background: color-mix(in oklab, var(--c) 10%, var(--panel)); }
.gl-stat-n { font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.2; }
.gl-stat .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--c); margin-right: 6px; vertical-align: 1px; }
.gl-bar { gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.gl-bar .seg button { padding: 5px 10px; }
.gl-bar .iconbtn.on { background: var(--accent-soft); border-color: var(--accent); color: var(--accent-hi); }
.gl-q { display: flex; align-items: center; gap: 8px; padding: 0 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel); min-width: 260px; }
.gl-q input { border: 0; background: transparent; padding: 8px 0; flex: 1; outline: none; box-shadow: none; }
.gl-bar select { width: auto; max-width: 170px; }
.gl-bulk { gap: 8px; padding: 10px 14px; margin-bottom: 14px; border-radius: 14px; background: color-mix(in oklab, var(--accent) 12%, var(--panel)); border: 1px solid color-mix(in oklab, var(--accent) 40%, transparent); }
.gl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 20px 16px; }
.gl-card { display: grid; gap: 9px; color: inherit; text-decoration: none; }
.gl-cover { position: relative; aspect-ratio: 3 / 4; border-radius: 14px; overflow: hidden; background: var(--sunken) center / cover; border: 1px solid var(--line);
  box-shadow: var(--shadow); transition: transform .25s var(--ease-out), box-shadow .25s var(--ease-out), border-color .15s; display: grid; place-items: center; }
.gl-card:hover .gl-cover, .gl-card:focus-visible .gl-cover { transform: translateY(-3px); border-color: var(--accent); box-shadow: var(--shadow-pop); }
.gl-card.sel .gl-cover { border: 2px solid var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); }
.gl-card.selecting:not(.sel) .gl-cover { opacity: .78; }
.gl-check { position: absolute; left: 50%; top: 50%; translate: -50% -50%; width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; background: rgba(0, 0, 0, .5); color: #fff; border: 2px solid #fff; }
.gl-cover img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transition: filter .2s; }
.gl-cover img.blur { filter: blur(16px) saturate(.6); transform: scale(1.1); }
.gl-initial { font-size: 54px; font-weight: 700; color: rgba(255, 255, 255, .85); }
.gl-r18 { position: absolute; font-size: 12px; padding: 3px 10px; border-radius: 99px; background: rgba(0, 0, 0, .55); color: #fff; }
.gl-status { position: absolute; left: 8px; top: 8px; font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 99px; color: #fff;
  background: color-mix(in oklab, var(--c) 78%, #000); box-shadow: 0 2px 8px rgba(0, 0, 0, .3); }
.gl-rate { position: absolute; right: 8px; top: 8px; min-width: 26px; height: 26px; display: grid; place-items: center; border-radius: 8px; font-weight: 700; font-size: 13px;
  background: rgba(0, 0, 0, .55); color: #ffd36b; backdrop-filter: blur(6px); }
.gl-src { position: absolute; right: 8px; bottom: 8px; display: flex; gap: 4px; padding: 4px 6px; border-radius: 99px; background: rgba(0, 0, 0, .45); }
.gl-src i, .gl-rsrc i { width: 7px; height: 7px; border-radius: 50%; }
.gl-meta { display: grid; gap: 1px; padding: 0 2px; }
.gl-list { padding: 6px; display: grid; }
.gl-row { display: grid; grid-template-columns: auto 40px minmax(0, 2.4fr) minmax(0, 1fr) 96px 64px 52px 100px 52px; gap: 14px; align-items: center; padding: 7px 10px; border-radius: 10px; color: inherit; text-decoration: none; }
.gl-row:hover { background: var(--panel2); }
.gl-row.sel { background: var(--accent-soft); }
.gl-rcover { width: 40px; aspect-ratio: 3 / 4; border-radius: 6px; background: center / cover; }
.gl-rtitle { display: grid; min-width: 0; }
.gl-rsrc { display: flex; gap: 4px; }
.gl-pill { font-size: 11px; font-weight: 600; padding: 1px 9px; border-radius: 99px; color: var(--c); background: color-mix(in oklab, var(--c) 14%, transparent); border: 1px solid color-mix(in oklab, var(--c) 35%, transparent); }
.accent { color: var(--accent); }
.gl-empty { display: grid; justify-items: center; gap: 8px; padding: 70px 20px; text-align: center; }
.gl-empty h3 { margin: 6px 0 0; }
.gl-empty p { max-width: 460px; margin: 0 0 8px; }
.gl-fade-enter-active, .gl-fade-leave-active { transition: opacity .35s var(--ease-out); }
.gl-fade-enter-from, .gl-fade-leave-to { opacity: 0; }
@media (max-width: 1250px) { .gl-top { grid-template-columns: 1fr; } .gl-stats { grid-template-columns: repeat(4, 1fr); } }
@media (prefers-reduced-motion: reduce) { .gl-cover, .gl-strip-item { transition: none; } .gl-card:hover .gl-cover { transform: none; } .gl-fade-enter-active, .gl-fade-leave-active { transition: none; } }
</style>
