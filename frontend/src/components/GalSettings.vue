<script setup>
// 设置 → 游戏库元数据：模式、来源顺序（决定合并时字段的优先级）、启用的来源、Bangumi 令牌
import { nextTick, onMounted, ref } from 'vue'
import { ArrowUp, ArrowDown } from 'lucide-vue-next'
import { api } from '../api'
import { guard } from '../toast'
import { SOURCES } from '../galgame/defs'

const cfg = ref(null)
const token = ref('')
onMounted(async () => {
  cfg.value = await api.get('/api/galgames/meta/settings')
  if (location.hash === '#galgame') { await nextTick(); document.getElementById('galgame')?.scrollIntoView({ block: 'start' }) }
})
async function save(body, msg = '已保存') { cfg.value = await guard(() => api.put('/api/galgames/meta/settings', body), msg) }
function move(i, d) {
  const o = [...cfg.value.order]
  ;[o[i], o[i + d]] = [o[i + d], o[i]]
  save({ order: o }, '来源顺序已更新')
}
const toggle = (k) => save({ enabled: { ...cfg.value.enabled, [k]: !cfg.value.enabled[k] } })
async function saveToken(clear) { await save({ bangumi_token: clear ? '' : token.value.trim() }, clear ? '已清除令牌' : '令牌已保存'); token.value = '' }
const MODES = { mixed: '混合（互相补全）', bangumi: '只用 Bangumi', vndb: '只用 VNDB', ymgal: '只用月幕' }
</script>

<template>
  <section v-if="cfg" id="galgame" class="card grid" style="gap:12px">
    <div class="row"><h2 style="margin:0">游戏库元数据</h2><span class="small muted">Bangumi · VNDB · 月幕 Galgame</span><span class="spacer" />
      <span v-if="!cfg.online" class="badge ai">已关闭联网（FRONT_GALGAME=off）</span></div>
    <div class="row" style="gap:10px"><span class="small muted" style="min-width:70px">模式</span>
      <div class="seg"><button v-for="(l, k) in MODES" :key="k" :class="{ on: cfg.mode === k }" @click="save({ mode: k })">{{ l }}</button></div></div>
    <p class="small faint" style="margin:0">混合模式会同时搜索所有启用的来源，选中一条后自动在其他来源里找同一部作品并合并；单一来源模式下，这个来源出错或没结果时按下面的顺序回退。</p>
    <div class="gs-order">
      <div v-for="(s, i) in cfg.order" :key="s" class="row gs-row" :class="{ off: !cfg.enabled[s] }">
        <span class="gs-n">{{ i + 1 }}</span><i class="dot" :style="{ background: SOURCES[s].color }" /><b>{{ SOURCES[s].label }}</b>
        <span class="small faint">{{ { bangumi: '中文名、评分排名、标签', vndb: '英文资料、时长、角色与声优', ymgal: '中文简介、汉化信息' }[s] }}</span>
        <span class="spacer" />
        <button class="iconbtn" :disabled="i === 0" title="上移" @click="move(i, -1)"><ArrowUp :size="14" /></button>
        <button class="iconbtn" :disabled="i === cfg.order.length - 1" title="下移" @click="move(i, 1)"><ArrowDown :size="14" /></button>
        <label class="row small" style="gap:6px"><input type="checkbox" :checked="cfg.enabled[s]" @change="toggle(s)" />启用</label>
      </div>
    </div>
    <p class="small faint" style="margin:0">合并时每个字段取排在前面、且有值的来源（简介优先用中文）；别名、标签、链接取并集，各来源的评分分别保留。</p>
    <div class="row" style="gap:16px">
      <label class="row small" style="gap:6px"><input type="checkbox" :checked="cfg.auto_match" @change="save({ auto_match: !cfg.auto_match })" />添加时自动匹配其他来源</label>
      <label class="row small" style="gap:6px"><input type="checkbox" :checked="cfg.fetch_characters" @change="save({ fetch_characters: !cfg.fetch_characters })" />拉取角色资料</label>
      <label class="row small" style="gap:6px"><input type="checkbox" :checked="cfg.blur_nsfw" @change="save({ blur_nsfw: !cfg.blur_nsfw })" />模糊 R18 封面</label>
    </div>
    <div class="row" style="gap:8px"><span class="small muted" style="min-width:70px">Bangumi 令牌</span>
      <input v-model="token" type="password" autocomplete="off" :placeholder="cfg.has_bangumi_token ? '已设置（不会显示）' : '可选：登录后才能搜到 R18 条目'" style="max-width:320px" />
      <button :disabled="!token.trim()" @click="saveToken(false)">保存</button><button v-if="cfg.has_bangumi_token" class="ghost" @click="saveToken(true)">清除</button>
      <a class="small" href="https://next.bgm.tv/demo/access-token" target="_blank" rel="noopener noreferrer">生成令牌 ↗</a></div>
    <p class="small faint" style="margin:0">只在你搜索、添加、刷新时联网；数据来自各站的公开接口，仅供个人非商业整理（VNDB 数据按其数据许可使用，月幕使用其公开的客户端凭证）。</p>
  </section>
</template>

<style scoped>
.gs-order { display: grid; gap: 6px; }
.gs-row { gap: 10px; padding: 8px 12px; border-radius: 12px; background: var(--panel2); border: 1px solid var(--line); flex-wrap: nowrap; }
.gs-row.off { opacity: .55; }
.gs-n { width: 20px; height: 20px; display: grid; place-items: center; border-radius: 6px; background: var(--accent-soft); color: var(--accent); font-size: 12px; font-weight: 700; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
</style>
