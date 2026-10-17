<script setup>
// galgame 详情：游玩记录（状态、评分、时长、日期、笔记）、多来源元数据、角色导入、关联作品的 CG 档案
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, RefreshCw, Link2, PenLine, Trash2, Pin, PinOff, ExternalLink, ImageDown, ImageUp, ImageOff, Users, Images, Database, BookOpen, Play, UserPlus, Check, Clock, Undo2, Unlink, FolderPlus } from 'lucide-vue-next'
import { api, Galgames, thumb } from '../api'
import { guard, toast } from '../toast'
import Modal from '../components/Modal.vue'
import TagChips from '../components/TagChips.vue'
import TagPicker from '../components/TagPicker.vue'
import QuickSearch from '../components/QuickSearch.vue'
import CGViewer from '../components/CGViewer.vue'
import GalAddDialog from '../components/GalAddDialog.vue'
import { STATUS, SOURCES, coverUrl, fmtMinutes, tint } from '../galgame/defs'

const route = useRoute()
const router = useRouter()
const g = ref(null)
const cfg = ref(null)
const tab = ref(route.query.tab || 'overview')
const cg = ref([])
const workChars = ref([])
const viewing = ref(null)
const matching = ref(false)
const editing = ref(null)
const busy = ref('')
const reveal = ref(false)
const notes = ref('')
const coverInput = ref(null)

async function load() {
  const id = Number(route.params.id)
  ;[g.value, cfg.value] = await Promise.all([Galgames.get(id), api.get('/api/galgames/meta/settings')])
  notes.value = g.value.notes || ''
  await loadWork()
}
async function loadWork() {
  if (!g.value.work_id) { cg.value = []; workChars.value = []; return }
  const [c, w] = await Promise.all([api.get(`/api/works/${g.value.work_id}/cg`), api.get(`/api/works/${g.value.work_id}/characters`)])
  cg.value = c.groups
  workChars.value = w
}
watch(() => route.params.id, (id) => id && guard(load), { immediate: true })

async function patch(body, msg) { g.value = await guard(() => Galgames.update(g.value.id, body), msg) }
function setStatus(k) {
  const today = new Date().toISOString().slice(0, 10)
  const body = { status: k }
  if (k === 'playing' && !g.value.started_on) body.started_on = today
  if (k === 'finished' && !g.value.finished_on) body.finished_on = today
  patch(body, `已标记为“${STATUS[k].label}”`)
}
const rate = (n) => patch({ my_rating: g.value.my_rating === n ? null : n })
const addTime = (min) => patch({ play_minutes: Math.max(0, (g.value.play_minutes || 0) + min) }, `游玩时长 ${fmtMinutes(Math.max(0, (g.value.play_minutes || 0) + min))}`)
const hours = computed({ get: () => Math.floor((g.value?.play_minutes || 0) / 60), set: (h) => patch({ play_minutes: Math.max(0, h | 0) * 60 + ((g.value.play_minutes || 0) % 60) }) })
const mins = computed({ get: () => (g.value?.play_minutes || 0) % 60, set: (m) => patch({ play_minutes: Math.floor((g.value.play_minutes || 0) / 60) * 60 + Math.min(59, Math.max(0, m | 0)) }) })
function saveNotes() { if (notes.value !== (g.value.notes || '')) patch({ notes: notes.value || null }, '笔记已保存') }

async function act(key, fn, msg) {
  busy.value = key
  try { const r = await guard(fn, msg); if (r && r.id === g.value.id) g.value = r; return r } finally { busy.value = '' }
}
const refresh = (reset = false) => act('refresh', () => api.post(`/api/galgames/${g.value.id}/refresh`, { reset_overrides: reset }), reset ? '已恢复为来源数据' : '元数据已刷新')
const refreshOne = (s) => act(`r-${s}`, () => api.post(`/api/galgames/${g.value.id}/refresh`, { sources: [s] }), `已刷新 ${SOURCES[s].label}`)
const unlink = (s) => confirm(`解除与 ${SOURCES[s].label} 的关联？已有的资料会保留。`) && act(`u-${s}`, () => api.del(`/api/galgames/${g.value.id}/sources/${s}`), '已解除关联')
const saveCover = () => act('cover', () => api.post(`/api/galgames/${g.value.id}/cover`), '封面已保存到本地')
const dropCover = () => act('cover', () => api.del(`/api/galgames/${g.value.id}/cover`), '已移除本地封面')
async function uploadCover(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  const form = new FormData()
  form.append('file', file)
  await act('cover', () => api.upload(`/api/galgames/${g.value.id}/cover`, form, 'PUT'), '封面已更新')
}
async function makeWork() { await act('work', () => api.post(`/api/galgames/${g.value.id}/work`), '已新建作品'); loadWork() }
async function importChars(indexes) {
  const r = await act('chars', () => api.post(`/api/galgames/${g.value.id}/import-characters`, indexes ? { indexes } : {}))
  toast(r.created.length ? `已导入 ${r.created.length} 个角色${r.skipped.length ? `，${r.skipped.length} 个已存在` : ''}` : '这些角色都已经在角色百科里了')
  g.value = await Galgames.get(g.value.id)
  loadWork()
}
async function remove() {
  if (!confirm(`从游戏库删除“${g.value.title}”？关联的作品、角色和 CG 不会被删除。`)) return
  await guard(() => Galgames.remove(g.value.id), '已删除')
  router.push('/galgames')
}
function edit() {
  const x = g.value
  editing.value = { title: x.title, title_cn: x.title_cn, original: x.original, aliases: x.aliases.join('\n'), developer: x.developer,
    release_date: x.release_date, platforms: x.platforms.join('、'), description: x.description, nsfw: x.nsfw, tag_ids: x.tags.map((t) => t.id) }
}
async function saveEdit() {
  const e = editing.value
  const split = (s, re) => (s || '').split(re).map((v) => v.trim()).filter(Boolean)
  await patch({ ...e, aliases: split(e.aliases, /\n|,|，/), platforms: split(e.platforms, /、|,|，|\//), release_date: e.release_date || null, title_cn: e.title_cn || null, original: e.original || null, developer: e.developer || null }, '已保存')
  editing.value = null
}
function matched(gal) { matching.value = false; g.value = gal; loadWork() }

const inWiki = (name) => workChars.value.find((c) => c.name === name)
const srcList = computed(() => (cfg.value?.order || Object.keys(SOURCES)).filter((s) => g.value?.sources[s]).map((s) => ({ s, ...g.value.sources[s] })))
const hasLinked = computed(() => srcList.value.length > 0)
const blurred = computed(() => g.value?.nsfw && cfg.value?.blur_nsfw !== false && !reveal.value)
const cgTotal = computed(() => cg.value.reduce((n, x) => n + x.count, 0))
const FIELD = { title: '标题', title_cn: '中文名', original: '原名', aliases: '别名', description: '简介', developer: '品牌', release_date: '发售日期', platforms: '平台', source_tags: '来源标签', nsfw: 'R18 标记' }
const when = (s) => (s ? new Date(s).toLocaleString('zh-CN', { year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '')
const hoursLong = (m) => (m ? `约 ${Math.round(m / 60)} 小时` : '')
const TABS = computed(() => [['overview', '概览', BookOpen], ['chars', `角色 · ${g.value?.characters?.length || 0}`, Users], ['cg', `CG 档案 · ${cgTotal.value}`, Images], ['meta', '元数据来源', Database]])
</script>

<template>
  <div class="gd">
    <template v-if="g">
    <section class="gd-hero card">
      <div class="gd-bg" :style="coverUrl(g) ? { backgroundImage: `url(${coverUrl(g)})` } : { backgroundImage: tint(g.title) }" :class="{ blur: blurred }" />
      <div class="gd-hero-in">
        <div class="gd-cover" :style="coverUrl(g) ? {} : { backgroundImage: tint(g.title) }" @click="blurred && (reveal = true)">
          <img v-if="coverUrl(g)" :src="coverUrl(g)" :alt="g.title" :class="{ blur: blurred }" />
          <span v-else class="gd-initial">{{ g.title.replace('【示例】', '').slice(0, 1) }}</span>
          <span v-if="blurred" class="gd-r18">R18 · 点击显示</span>
        </div>
        <div class="gd-info">
          <div class="row" style="gap:8px"><RouterLink to="/galgames" class="btn ghost small"><ArrowLeft :size="14" />游戏库</RouterLink><span class="eyebrow">GALGAME</span><Pin v-if="g.pinned" :size="13" class="accent" /></div>
          <h1 class="gd-title">{{ g.title }}</h1>
          <div v-if="g.original && g.original !== g.title" class="gd-orig">{{ g.original }}</div>
          <div class="small muted">{{ [g.developer, g.release_date, g.platforms.slice(0, 5).join(' / ')].filter(Boolean).join(' · ') || '还没有匹配元数据' }}</div>
          <div v-if="g.aliases.length" class="row gd-alias"><span v-for="a in g.aliases.slice(0, 8)" :key="a" class="badge">{{ a }}</span></div>
          <div class="row gd-scores">
            <a v-for="x in srcList" :key="x.s" :href="x.url" target="_blank" rel="noopener noreferrer" class="gd-score" :style="{ '--c': SOURCES[x.s].color }">
              <i class="dot" /><b>{{ SOURCES[x.s].label }}</b><span v-if="x.score" class="gd-score-n">★ {{ x.score }}</span><span v-if="x.rank" class="faint">#{{ x.rank }}</span><span v-if="x.length_minutes" class="faint">{{ hoursLong(x.length_minutes) }}</span><ExternalLink :size="12" class="faint" />
            </a>
            <button v-if="!hasLinked" class="primary small" @click="matching = true"><Link2 :size="14" />匹配元数据</button>
          </div>

          <div class="gd-track">
            <div class="seg" role="tablist" aria-label="游玩状态">
              <button v-for="(s, k) in STATUS" :key="k" :class="{ on: g.status === k }" :style="g.status === k ? { background: s.color, color: '#10101a' } : {}" @click="setStatus(k)">{{ s.label }}</button>
            </div>
            <div class="gd-rate" role="group" aria-label="我的评分">
              <button v-for="n in 10" :key="n" :class="{ on: g.my_rating && n <= g.my_rating }" :title="`${n} 分`" @click="rate(n)">{{ n }}</button>
              <span class="small faint">{{ g.my_rating ? `${g.my_rating} / 10` : '未评分' }}</span>
            </div>
            <div class="row gd-time">
              <Clock :size="14" class="faint" />
              <input :value="hours" type="number" min="0" aria-label="小时" @change="hours = $event.target.valueAsNumber" /><span class="small muted">小时</span>
              <input :value="mins" type="number" min="0" max="59" aria-label="分钟" @change="mins = $event.target.valueAsNumber" /><span class="small muted">分</span>
              <button class="small" @click="addTime(30)">+30 分</button><button class="small" @click="addTime(60)">+1 小时</button>
              <span class="spacer" />
              <label class="small muted row" style="gap:6px">开始<input type="date" :value="g.started_on" @change="patch({ started_on: $event.target.value || null })" /></label>
              <label class="small muted row" style="gap:6px">通关<input type="date" :value="g.finished_on" @change="patch({ finished_on: $event.target.value || null })" /></label>
            </div>
          </div>

          <div class="row gd-actions">
            <button v-if="hasLinked" :disabled="busy === 'refresh'" @click="refresh()"><RefreshCw :size="14" :class="{ spin: busy === 'refresh' }" />刷新元数据</button>
            <button v-if="hasLinked" @click="matching = true"><Link2 :size="14" />重新匹配</button>
            <QuickSearch :q="g.title" kind="work" :alts="[g.original, g.title_cn, ...g.aliases].filter(Boolean)" />
            <button @click="edit"><PenLine :size="14" />编辑</button>
            <span class="spacer" />
            <button class="iconbtn" :title="g.pinned ? '取消置顶' : '置顶'" @click="patch({ pinned: !g.pinned })"><PinOff v-if="g.pinned" :size="15" /><Pin v-else :size="15" /></button>
            <button v-if="g.cover_url && !g.has_cover" class="iconbtn" title="把封面保存到本地" :disabled="busy === 'cover'" @click="saveCover"><ImageDown :size="15" /></button>
            <button class="iconbtn" title="上传封面" @click="coverInput.click()"><ImageUp :size="15" /></button>
            <button v-if="g.has_cover" class="iconbtn" title="移除本地封面" @click="dropCover"><ImageOff :size="15" /></button>
            <input ref="coverInput" type="file" accept="image/*" hidden @change="uploadCover" />
            <button class="iconbtn danger" title="从游戏库删除" @click="remove"><Trash2 :size="15" /></button>
          </div>
        </div>
      </div>
    </section>

    <nav class="gd-tabs" role="tablist">
      <button v-for="[k, l, icon] in TABS" :key="k" :class="{ on: tab === k }" role="tab" @click="tab = k"><component :is="icon" :size="15" />{{ l }}</button>
    </nav>

    <section v-if="tab === 'overview'" class="gd-ov">
      <div class="card grid" style="gap:12px;align-content:start">
        <h3 class="gd-h">简介</h3>
        <p class="gd-desc">{{ g.description || '还没有简介。' }}</p>
        <div v-if="g.source_tags.length" class="row" style="gap:6px"><span v-for="t in g.source_tags.slice(0, 24)" :key="t" class="badge">{{ t }}</span></div>
        <TagChips v-if="g.tags.length" :tags="g.tags" show-cat />
        <div v-if="g.links.length" class="gd-links">
          <a v-for="l in g.links" :key="l.url" :href="l.url" target="_blank" rel="noopener noreferrer" class="btn small ghost"><ExternalLink :size="13" />{{ l.title }}</a>
        </div>
      </div>
      <div class="card grid" style="gap:10px;align-content:start">
        <div class="row"><h3 class="gd-h">游玩笔记</h3><span class="spacer" /><span class="small faint">离开输入框自动保存</span></div>
        <textarea v-model="notes" rows="9" placeholder="路线顺序、喜欢的角色、通关感想……（Markdown）" @blur="saveNotes" />
        <div class="small muted">已玩 {{ fmtMinutes(g.play_minutes) }}<template v-if="g.started_on"> · {{ g.started_on }} 开始</template><template v-if="g.finished_on"> · {{ g.finished_on }} 通关</template></div>
        <RouterLink v-if="g.work_id" :to="`/works?id=${g.work_id}`" class="small">在“作品 / CG”里打开关联作品 →</RouterLink>
      </div>
    </section>

    <section v-else-if="tab === 'chars'" class="card">
      <div class="row" style="margin-bottom:12px"><h3 class="gd-h">登场角色</h3><span class="small faint">来自 {{ srcList.map((x) => SOURCES[x.s].label).join(' / ') || '—' }}</span><span class="spacer" />
        <button v-if="g.characters?.length" class="primary" :disabled="busy === 'chars'" @click="importChars()"><UserPlus :size="15" />全部导入角色百科</button></div>
      <div v-if="!g.characters?.length" class="empty">来源里没有角色资料</div>
      <div v-reveal class="gd-chars">
        <div v-for="(c, i) in g.characters" :key="i" class="gd-char">
          <span class="gd-char-img" :style="c.image ? { backgroundImage: `url(${c.image})` } : {}" />
          <div class="grid" style="gap:2px;min-width:0">
            <div class="row" style="gap:6px;flex-wrap:nowrap"><b class="ellip">{{ c.name }}</b><span class="badge" :class="{ main: c.role === 'main' }">{{ c.role === 'main' ? '主角' : '配角' }}</span></div>
            <span v-if="c.original" class="small muted ellip">{{ c.original }}</span>
            <span v-if="c.cv" class="small faint ellip">CV {{ c.cv }}</span>
            <div class="row" style="gap:6px;margin-top:4px">
              <RouterLink v-if="inWiki(c.name)" :to="`/characters/${inWiki(c.name).id}`" class="small ok-t row" style="gap:3px"><Check :size="13" />已在角色百科</RouterLink>
              <button v-else class="small ghost" @click="importChars([i])"><UserPlus :size="13" />导入</button>
              <a v-if="c.url" :href="c.url" target="_blank" rel="noopener noreferrer" class="small faint">来源 ↗</a>
            </div>
          </div>
        </div>
      </div>
      <p class="small faint" style="margin:12px 0 0">导入只写入名字、原名、配音和来源链接；角色立绘不会被下载。</p>
    </section>

    <section v-else-if="tab === 'cg'" class="card">
      <template v-if="g.work_id">
        <div class="row" style="margin-bottom:12px"><h3 class="gd-h">CG 档案 · {{ cg.length }} 组 / {{ cgTotal }} 张</h3><span class="spacer" />
          <button v-if="cg.length" class="primary" @click="viewing = 0"><Play :size="14" />鉴赏模式</button>
          <RouterLink class="btn" :to="`/works?id=${g.work_id}`">在作品页管理</RouterLink><RouterLink class="btn" to="/import">批量导入 CG</RouterLink></div>
        <div v-reveal class="thumbgrid" style="grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))">
          <div v-for="(x, i) in cg" :key="x.key" class="tile" @click="viewing = i">
            <div class="img" style="aspect-ratio:16/9;position:relative" :style="{ backgroundImage: `url(${thumb(x.cover_id)})` }"><span v-if="x.count > 1" class="badge" style="position:absolute;right:8px;top:8px;background:#000a;color:#fff">差分 × {{ x.count }}</span></div>
            <div class="meta"><div class="title">{{ x.key }}</div><div class="small muted">{{ x.size }}</div></div>
          </div>
        </div>
        <div v-if="!cg.length" class="empty">这个作品下还没有 CG，可以用“批量导入”把 CG 文件夹导进来（勾选 CG 模式并选择这个作品）。</div>
      </template>
      <div v-else class="gl-empty-sm">
        <p class="muted">CG 档案挂在“作品”下。这个游戏还没有关联作品。</p>
        <button class="primary" :disabled="busy === 'work'" @click="makeWork"><FolderPlus :size="15" />新建作品</button>
      </div>
    </section>

    <section v-else class="card grid" style="gap:14px">
      <div class="row"><h3 class="gd-h">元数据来源</h3><span class="small faint">模式：{{ cfg?.mode === 'mixed' ? '混合（互相补全）' : SOURCES[cfg?.mode]?.label }} · 顺序 {{ cfg?.order.map((s) => SOURCES[s].short).join(' → ') }}</span><span class="spacer" />
        <RouterLink to="/settings#galgame" class="small">修改设置</RouterLink><button class="primary small" @click="matching = true"><Link2 :size="14" />匹配 / 添加来源</button></div>
      <table class="gd-table">
        <thead><tr><th>来源</th><th>条目</th><th>评分</th><th>排名 / 票数</th><th>更新于</th><th /></tr></thead>
        <tbody>
          <tr v-for="(s, k) in SOURCES" :key="k">
            <td><span class="row" style="gap:6px"><i class="dot" :style="{ background: s.color }" />{{ s.label }}</span></td>
            <template v-if="g.sources[k]">
              <td><a :href="g.sources[k].url" target="_blank" rel="noopener noreferrer">{{ g.sources[k].title || g.sources[k].id }} ↗</a><div class="small faint mono">{{ g.sources[k].id }}</div></td>
              <td>{{ g.sources[k].score ?? '—' }}</td>
              <td class="small muted">{{ [g.sources[k].rank && `#${g.sources[k].rank}`, g.sources[k].votes && `${g.sources[k].votes} 票`].filter(Boolean).join(' · ') || '—' }}</td>
              <td class="small muted">{{ when(g.sources[k].fetched_at) }}</td>
              <td><div class="row" style="gap:4px;justify-content:flex-end;flex-wrap:nowrap"><button class="iconbtn" title="只刷新这个来源" :disabled="busy === `r-${k}`" @click="refreshOne(k)"><RefreshCw :size="14" :class="{ spin: busy === `r-${k}` }" /></button><button class="iconbtn" title="解除关联" @click="unlink(k)"><Unlink :size="14" /></button></div></td>
            </template>
            <template v-else><td colspan="4" class="small faint">未关联</td><td /></template>
          </tr>
        </tbody>
      </table>
      <div class="gd-ovr">
        <div class="row"><b>手动修改过的字段</b><span class="small faint">刷新元数据时保留你的修改</span><span class="spacer" />
          <button v-if="g.overrides.length && hasLinked" class="small" @click="refresh(true)"><Undo2 :size="13" />全部恢复为来源数据</button></div>
        <div class="row" style="gap:6px;margin-top:6px"><span v-for="o in g.overrides" :key="o" class="chip">{{ FIELD[o] || o }}</span><span v-if="!g.overrides.length" class="small faint">没有</span></div>
      </div>
      <p class="small faint" style="margin:0">数据来自 Bangumi（bgm.tv）、VNDB（vndb.org，按其数据许可使用）与月幕 Galgame（ymgal.games）的公开接口，仅供个人整理，非商业用途。</p>
    </section>

    <CGViewer v-if="viewing !== null && cg.length" :groups="cg" :start="viewing" :title="g.title" @close="viewing = null" />
    <GalAddDialog v-if="matching" :match-for="g" @close="matching = false" @added="matched" />
    <Modal v-if="editing" title="编辑游戏资料" @close="editing = null">
      <div class="grid">
        <div class="grid cols-3">
          <label class="field" style="grid-column: span 3">显示标题<input v-model="editing.title" /></label>
          <label class="field">中文名<input v-model="editing.title_cn" /></label>
          <label class="field" style="grid-column: span 2">原名<input v-model="editing.original" /></label>
          <label class="field">品牌<input v-model="editing.developer" /></label>
          <label class="field">发售日期<input v-model="editing.release_date" placeholder="2025-03-14" /></label>
          <label class="field">平台<input v-model="editing.platforms" placeholder="PC、Switch" /></label>
        </div>
        <label class="field">别名（每行一个）<textarea v-model="editing.aliases" rows="3" /></label>
        <label class="field">简介<textarea v-model="editing.description" rows="5" /></label>
        <label class="row small" style="gap:6px"><input v-model="editing.nsfw" type="checkbox" />R18（封面默认模糊）</label>
        <TagPicker v-model="editing.tag_ids" />
        <p class="small faint" style="margin:0">改过的字段会被记住，之后刷新元数据不会覆盖（可在“元数据来源”里恢复）。</p>
        <div class="row"><span class="spacer" /><button class="primary" @click="saveEdit">保存</button></div>
      </div>
    </Modal>
    </template>
  </div>
</template>

<style scoped>
.gd { display: grid; gap: 16px; }
.gd-hero { position: relative; overflow: hidden; padding: 0; }
.gd-bg { position: absolute; inset: -40px; background: center / cover; filter: blur(48px) saturate(1.3); opacity: .32; }
.gd-bg.blur { filter: blur(80px) saturate(.6); opacity: .2; }
.gd-hero::after { content: ''; position: absolute; inset: 0; background: linear-gradient(90deg, color-mix(in oklab, var(--panel) 30%, transparent), var(--panel) 75%); pointer-events: none; }
.gd-hero-in { position: relative; z-index: 1; display: grid; grid-template-columns: 230px 1fr; gap: 28px; padding: 24px; }
.gd-cover { position: relative; aspect-ratio: 3 / 4; border-radius: 16px; overflow: hidden; background: center / cover; box-shadow: 0 24px 50px -20px rgba(0, 0, 0, .7), 0 0 0 1px var(--line); display: grid; place-items: center; }
.gd-cover img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.gd-cover img.blur { filter: blur(18px) saturate(.6); transform: scale(1.1); cursor: pointer; }
.gd-r18 { position: absolute; padding: 4px 12px; border-radius: 99px; background: rgba(0, 0, 0, .6); color: #fff; font-size: 12px; cursor: pointer; }
.gd-initial { font-size: 80px; font-weight: 700; color: rgba(255, 255, 255, .85); }
.gd-info { display: grid; gap: 8px; align-content: start; min-width: 0; }
.gd-title { margin: 2px 0 0; font-size: 28px; line-height: 1.25; letter-spacing: -.01em; }
.gd-orig { color: var(--muted); font-size: 15px; }
.gd-alias { gap: 6px; }
.gd-scores { gap: 8px; margin-top: 4px; }
.gd-score { display: inline-flex; align-items: center; gap: 7px; padding: 5px 12px; border-radius: 999px; background: color-mix(in oklab, var(--c) 12%, var(--panel2)); border: 1px solid color-mix(in oklab, var(--c) 35%, transparent); color: var(--text); text-decoration: none; font-size: 13px; }
.gd-score:hover { border-color: var(--c); }
.gd-score .dot, .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; background: var(--c); flex: none; }
.gd-score-n { font-weight: 700; color: var(--warn); }
.gd-track { display: grid; gap: 10px; margin-top: 8px; padding: 14px; border-radius: 14px; background: color-mix(in oklab, var(--panel2) 80%, transparent); border: 1px solid var(--line); }
.gd-rate { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.gd-rate button { width: 30px; height: 28px; padding: 0; justify-content: center; border-radius: 8px; font-variant-numeric: tabular-nums; color: var(--muted); }
.gd-rate button.on { background: color-mix(in oklab, var(--warn) 20%, var(--panel2)); border-color: color-mix(in oklab, var(--warn) 55%, transparent); color: var(--warn); font-weight: 600; }
.gd-rate .small { margin-left: 8px; }
.gd-time { gap: 8px; }
.gd-time input[type=number] { width: 64px; }
.gd-time input[type=date] { width: auto; }
.gd-actions { gap: 8px; margin-top: 4px; }
.gd-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); }
.gd-tabs button { border: 0; border-radius: 10px 10px 0 0; background: transparent; color: var(--muted); padding: 9px 16px; border-bottom: 2px solid transparent; margin-bottom: -1px; }
.gd-tabs button.on { color: var(--text); border-bottom-color: var(--accent); }
.gd-tabs button:hover:not(.on) { color: var(--text); background: var(--accent-soft); }
.gd-h { margin: 0; font-size: 15px; }
.gd-ov { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
.gd-desc { margin: 0; white-space: pre-line; line-height: 1.75; color: var(--muted); }
.gd-links { display: flex; flex-wrap: wrap; gap: 4px; }
.gd-chars { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; }
.gd-char { display: grid; grid-template-columns: 64px 1fr; gap: 12px; padding: 10px; border-radius: 12px; background: var(--panel2); border: 1px solid var(--line); }
.gd-char-img { width: 64px; aspect-ratio: 3 / 4; border-radius: 9px; background: var(--sunken) center top / cover; }
.badge.main { color: var(--accent-hi); border-color: color-mix(in oklab, var(--accent) 45%, transparent); }
.gd-table { width: 100%; border-collapse: collapse; }
.gd-table th { text-align: left; font-size: 12px; color: var(--faint); font-weight: 500; padding: 6px 10px; border-bottom: 1px solid var(--line); }
.gd-table td { padding: 10px; border-bottom: 1px solid var(--line); vertical-align: middle; }
.gd-ovr { padding: 12px 14px; border-radius: 12px; background: var(--panel2); }
.gd-ovr .row { gap: 8px; }
.gl-empty-sm { display: grid; justify-items: center; gap: 8px; padding: 40px; }
.accent { color: var(--accent); }
.ok-t { color: var(--ok); }
.spin { animation: spin 1s linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 1000px) { .gd-hero-in { grid-template-columns: 160px 1fr; } .gd-ov { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { .spin { animation: none; } }
</style>
