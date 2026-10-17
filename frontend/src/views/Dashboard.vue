<script setup>
import AssetThumb from '../components/AssetThumb.vue'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Images, BookUser, Globe, NotebookPen, Box, IdCard, Gamepad2, Upload, FolderInput, WandSparkles, MessageCircle, ScanSearch, ArrowRight, NotebookText } from 'lucide-vue-next'
import { api, Assets, LABELS, thumb } from '../api'
import { countUp, gsap, reduced } from '../motion'

const router = useRouter()
const stats = ref(null)
const recent = ref([])
const timeline = ref([])
const act = ref(null)
const q = ref('')
const numEls = ref({})

const hour = new Date().getHours()
const greeting = hour < 5 ? '夜深了，还在创作吗？' : hour < 11 ? '早上好，今天画点什么？' : hour < 14 ? '中午好，休息一下也不错' : hour < 18 ? '下午好，灵感还在吗？' : hour < 23 ? '晚上好，继续今天的创作' : '夜深了，还在创作吗？'

const cards = [
  ['assets', '素材', '/assets', Images], ['characters', '角色', '/characters', BookUser], ['worlds', '世界观', '/worlds', Globe],
  ['notes', '笔记', '/notes', NotebookText], ['prompts', '提示词', '/prompts', NotebookPen], ['sd_models', 'SD 模型', '/models', Box],
  ['cards', '角色卡', '/cards', IdCard], ['works', '作品', '/works', Gamepad2],
]
const actions = [
  ['写笔记', '/notes', NotebookText], ['上传素材', '/assets', Upload], ['批量导入', '/import', FolderInput], ['出图', '/generate', WandSparkles],
  ['AI 对话', '/chat', MessageCircle], ['抽取角色', '/extract', ScanSearch],
]

// 热力图：列 = 周，行 = 周一…周日
const weeks = computed(() => {
  if (!act.value) return []
  const out = []
  act.value.days.forEach((d, i) => { (out[Math.floor(i / 7)] ??= []).push(d) })
  return out
})
const level = (n) => { const mx = act.value?.max || 1; return n === 0 ? 0 : Math.min(4, Math.ceil((n / mx) * 4)) }
const months = computed(() => weeks.value.map((w, i) => {
  const m = w[0].date.slice(5, 7)
  return i === 0 || weeks.value[i - 1][0].date.slice(5, 7) !== m ? `${+m}月` : ''
}))
const tip = (d) => `${d.date}：${d.count} 条${Object.keys(d.by).length ? '（' + Object.entries(d.by).map(([k, v]) => `${LABELS.activity?.[k] ?? k} ${v}`).join('、') + '）' : ''}`
const heat = ref(null)

onMounted(async () => {
  const [s, r, rows, a] = await Promise.all([
    api.get('/api/stats'), Assets.list({ limit: 8 }), api.get('/api/assets/stats/timeline'), api.get('/api/stats/activity?weeks=53'),
  ])
  stats.value = s
  recent.value = r.items
  const byMonth = {}
  for (const row of rows) (byMonth[row.month] ??= {})[row.kind] = row.count
  timeline.value = Object.entries(byMonth).slice(0, 8)
  act.value = a
  await nextTick()
  for (const [k] of cards) countUp(numEls.value[k], s[k])
  if (heat.value && !reduced()) gsap.from(heat.value.querySelectorAll('.wk'), { autoAlpha: 0, duration: 0.3, stagger: 0.012, clearProps: 'opacity,visibility' })
})
const search = () => q.value.trim() && router.push({ path: '/search', query: { q: q.value.trim(), mode: 'hybrid' } })
</script>

<template>
  <div v-if="stats" class="dash">
    <section class="hero">
      <div class="eyebrow">FRONT · 创作工作台</div>
      <h2 class="greet">{{ greeting }}</h2>
      <p class="muted sub">资料库里有 {{ stats.assets }} 份素材、{{ stats.characters }} 个角色、{{ stats.worlds }} 个世界观。</p>
      <form class="ask" @submit.prevent="search">
        <input v-model="q" placeholder="找点什么？例如“守在雾里灯塔的女孩”——关键词与语义一起检索" />
        <button class="primary iconbtn" aria-label="搜索"><ArrowRight :size="16" /></button>
      </form>
      <div class="seg actions">
        <RouterLink v-for="[label, to, icon] in actions" :key="to" :to="to" class="btn ghost"><component :is="icon" :size="14" />{{ label }}</RouterLink>
      </div>
    </section>

    <section v-if="act" class="card activity">
      <div ref="heat" class="heat">
        <div class="months" :style="{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }"><span v-for="(m, i) in months" :key="i">{{ m }}</span></div>
        <div class="cells" :style="{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }">
          <div v-for="(w, i) in weeks" :key="i" class="wk">
            <i v-for="d in w" :key="d.date" :class="'l' + level(d.count)" :title="tip(d)" />
          </div>
        </div>
      </div>
      <div class="act-side">
        <div class="eyebrow">最近 {{ act.weeks }} 周</div>
        <div class="streak"><b>{{ act.streak }}</b> 天</div>
        <div class="muted small">{{ act.streak ? '连续创作中' : '今天还没有新记录' }} · 共 {{ act.total }} 条记录，{{ act.active_days }} 天有活动</div>
        <div class="legend small faint">少 <i class="l0" /><i class="l1" /><i class="l2" /><i class="l3" /><i class="l4" /> 多</div>
      </div>
    </section>

    <div class="card stats">
      <RouterLink v-for="[k, label, to, icon] in cards" :key="k" :to="to" class="stat">
        <span class="row muted small" style="gap:6px"><component :is="icon" :size="14" />{{ label }}</span>
        <b :ref="(el) => (numEls[k] = el)">0</b>
      </RouterLink>
    </div>

    <div class="grid lower">
      <div class="card">
        <div class="row"><h2 style="margin:0">最近入库</h2><span class="spacer" /><RouterLink to="/assets" class="muted small">全部 →</RouterLink></div>
        <div v-reveal class="thumbgrid gallery recent">
          <RouterLink v-for="a in recent" :key="a.id" :to="{ path: '/assets', query: { open: a.id } }" class="tile">
            <AssetThumb :asset="a" />
            <div class="meta"><div class="title">{{ a.title }}</div><span class="badge">{{ LABELS.assetKind[a.kind] }}</span></div>
          </RouterLink>
        </div>
      </div>
      <div class="card">
        <h2 style="margin-top:0">按月份</h2>
        <table>
          <tr v-for="[month, kinds] in timeline" :key="month">
            <td class="mono">
              <RouterLink :to="{ path: '/assets', query: { month } }">{{ month }}</RouterLink>
            </td>
            <td><span v-for="(n, k) in kinds" :key="k" class="badge" style="margin:0 4px 4px 0;display:inline-block">{{ LABELS.assetKind[k] }} {{ n }}</span></td>
          </tr>
        </table>
        <p class="small faint">数据目录：<span class="mono">{{ stats.data_dir }}</span></p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dash { display: grid; gap: 18px; }
.hero { padding: 26px 4px 6px; max-width: 760px; }
.greet { font-size: 34px; font-weight: 750; letter-spacing: -.02em; margin: 8px 0 6px; line-height: 1.2; }
.sub { margin: 0 0 18px; }
.ask { position: relative; }
.ask input { padding: 14px 54px 14px 18px; border-radius: 16px; font-size: 15px; background: var(--panel); box-shadow: var(--shadow); }
.ask button { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); width: 36px; height: 36px; }
.ask button:active { transform: translateY(-50%) scale(.95); }
.actions { margin-top: 12px; flex-wrap: wrap; }
.actions .btn { padding: 5px 14px; color: var(--muted); }
.actions .btn:hover { color: var(--text); }
.activity { display: grid; grid-template-columns: minmax(0, 1fr) 240px; gap: 32px; align-items: center; padding: 22px 24px; }
.heat { overflow-x: auto; }
.heat { min-width: 0; }
.months { display: grid; column-gap: 4px; font-size: 10.5px; color: var(--faint); height: 18px; white-space: nowrap; }
.cells { display: grid; gap: 4px; }
.wk { display: grid; grid-template-rows: repeat(7, auto); gap: 4px; }
.heat i { display: block; aspect-ratio: 1; border-radius: 4px; background: var(--panel2); }
.legend i { display: block; width: 11px; height: 11px; border-radius: 3px; background: var(--panel2); }
.l1 { background: color-mix(in oklab, var(--accent) 30%, var(--panel2)) !important; }
.l2 { background: color-mix(in oklab, var(--accent) 55%, var(--panel2)) !important; }
.l3 { background: color-mix(in oklab, var(--accent) 80%, var(--panel2)) !important; }
.l4 { background: var(--accent-hi) !important; }
.streak { font-size: 15px; margin: 4px 0; } .streak b { font-size: 34px; font-weight: 750; letter-spacing: -.02em; }
.legend { display: flex; gap: 3px; align-items: center; margin-top: 10px; }
.stats { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); padding: 6px; }
.stats .stat { padding: 12px 16px; border-radius: 10px; transition: background-color .15s var(--ease-out); }
.stats .stat + .stat { box-shadow: -1px 0 0 var(--line); }
.stats .stat:hover { background: var(--accent-soft); }
.stats .stat b { font-size: 24px; }
@media (max-width: 1300px) { .stats { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
.lower { grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); }
.recent { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 12px; }
@media (max-width: 1100px) { .activity, .lower { grid-template-columns: 1fr; } }
</style>
