<script setup>
// 设置页：浏览器查询的站点列表（名称 + 搜索网址模板，{q} 处填关键词）
import { computed, onMounted, ref } from 'vue'
import { Plus, RotateCcw, Trash2, ArrowUp, ArrowDown, ExternalLink } from 'lucide-vue-next'
import { api } from '../api'
import { guard } from '../toast'

const KIND_LABEL = { work: '作品 / 游戏', character: '角色', model: 'SD 模型', world: '世界观' }
const sites = ref([])
const dirty = ref(false)
const sample = ref('Summer Pockets')
onMounted(async () => { sites.value = (await api.get('/api/quick-search/sites')).sites })
const mark = () => { dirty.value = true }
function add() { sites.value.push({ id: Math.random().toString(36).slice(2, 10), name: '', url: 'https://', kinds: ['work', 'character'], enabled: true, match: [] }); mark() }
function move(i, d) { const a = sites.value; const j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; mark() }
function toggleKind(s, k) { s.kinds = s.kinds.includes(k) ? s.kinds.filter((x) => x !== k) : [...s.kinds, k]; mark() }
const preview = (s) => (s.url.includes('{q}') ? s.url.replace('{q}', encodeURIComponent(sample.value)) : s.url)
const valid = computed(() => sites.value.every((s) => s.name.trim() && /^https?:\/\/[^/\s]+/.test(s.url)))
async function save() {
  const body = { sites: sites.value.map((s) => ({ ...s, match: typeof s.match === 'string' ? s.match.split(/[,，]/).map((x) => x.trim()).filter(Boolean) : s.match })) }
  sites.value = (await guard(() => api.put('/api/quick-search/sites', body), '已保存站点列表')).sites
  dirty.value = false
}
async function reset() {
  if (!confirm('恢复为默认站点列表？自己添加的站点会被移除。')) return
  sites.value = (await guard(() => api.post('/api/quick-search/sites/reset'), '已恢复默认')).sites
  dirty.value = false
}
</script>

<template>
  <section class="card grid" style="gap:12px">
    <div class="row">
      <div>
        <h2 style="margin:0">浏览器查询</h2>
        <div class="small muted">在角色、作品、SD 模型页面点“浏览器查询”，用这些站点在新标签页里搜索。网址里写 <span class="mono">{q}</span> 的位置会填入关键词；不写 {q} 就只打开主页。</div>
      </div>
      <span class="spacer" />
      <label class="row small muted" style="gap:6px;flex-wrap:nowrap">试用关键词<input v-model="sample" style="width:150px" /></label>
    </div>
    <div class="notice small">Front 只生成并打开链接：不会抓取这些网站的内容，也不会替你下载任何文件。资料（名称、简介、封面）只通过 Bangumi / VNDB 等公开 API 获取。</div>
    <div class="sites">
      <div class="site head small faint"><span /><span>名称</span><span>搜索网址模板</span><span>用于</span><span /></div>
      <div v-for="(s, i) in sites" :key="s.id" class="site" :class="{ off: !s.enabled }">
        <input v-model="s.enabled" type="checkbox" title="启用" @change="mark" />
        <input v-model="s.name" placeholder="站点名称" @input="mark" />
        <div class="urlcell">
          <input v-model="s.url" class="mono" placeholder="https://example.com/search?q={q}" @input="mark" />
          <a :href="preview(s)" target="_blank" rel="noopener noreferrer" class="small faint ellip" :title="preview(s)"><ExternalLink :size="11" /> {{ preview(s) }}</a>
        </div>
        <div class="row" style="gap:4px">
          <span v-for="(l, k) in KIND_LABEL" :key="k" class="chip click" :class="{ on: s.kinds.includes(k) }" @click="toggleKind(s, k)">{{ l }}</span>
        </div>
        <div class="row" style="gap:2px;flex-wrap:nowrap">
          <button class="ghost iconbtn" title="上移" @click="move(i, -1)"><ArrowUp :size="14" /></button>
          <button class="ghost iconbtn" title="下移" @click="move(i, 1)"><ArrowDown :size="14" /></button>
          <button class="ghost iconbtn danger" title="删除" @click="sites.splice(i, 1); mark()"><Trash2 :size="14" /></button>
        </div>
      </div>
    </div>
    <div class="row">
      <button @click="add"><Plus :size="14" />添加站点</button>
      <button class="ghost" @click="reset"><RotateCcw :size="14" />恢复默认</button>
      <span class="spacer" />
      <span v-if="dirty" class="small muted">有未保存的修改</span>
      <button class="primary" :disabled="!dirty || !valid" @click="save">保存</button>
    </div>
  </section>
</template>

<style scoped>
.sites { display: grid; gap: 6px; }
.site { display: grid; grid-template-columns: 22px 180px minmax(0, 1fr) 300px 104px; gap: 10px; align-items: start; padding: 8px 10px; border-radius: 12px; background: var(--panel2); border: 1px solid var(--line); }
.site.head { background: none; border: 0; padding: 0 10px; letter-spacing: .06em; }
.site.off { opacity: .55; }
.site > input[type=checkbox] { margin-top: 10px; }
.urlcell { display: grid; gap: 3px; min-width: 0; }
.ellip { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
</style>
