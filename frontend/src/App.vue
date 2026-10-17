<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  LayoutDashboard, Images, FolderInput, Gamepad2, LibraryBig, Tags, BookUser, Globe, Waypoints,
  WandSparkles, NotebookPen, Puzzle, Box, MessageCircle, IdCard, BookMarked, ScanSearch, Settings,
  Sun, Moon, PanelLeftClose, PanelLeftOpen, NotebookText, Workflow,
} from 'lucide-vue-next'
import { toastState } from './toast'
import { enterPage, enterToast, leaveToast, movePill } from './motion'

const router = useRouter()
const route = useRoute()
const q = ref('')
const searchEl = ref(null)
const go = () => q.value.trim() && router.push({ path: '/search', query: { q: q.value.trim() } })
const nav = [
  ['资料库', 'LIBRARY', [['/', LayoutDashboard, '总览'], ['/assets', Images, '素材库'], ['/notes', NotebookText, '笔记本'], ['/diagrams', Workflow, '图表画布'], ['/import', FolderInput, '批量导入'], ['/works', Gamepad2, '作品 / CG'], ['/collections', LibraryBig, '收藏集'], ['/tags', Tags, '标签']]],
  ['百科', 'WIKI', [['/characters', BookUser, '角色百科'], ['/worlds', Globe, '世界观'], ['/graph', Waypoints, '关系网']]],
  ['AI 绘画', 'DRAW', [['/generate', WandSparkles, '出图'], ['/prompts', NotebookPen, '提示词库'], ['/snippets', Puzzle, '提示词片段'], ['/models', Box, 'SD 模型库']]],
  ['AI 角色', 'ROLEPLAY', [['/chat', MessageCircle, 'AI 对话'], ['/cards', IdCard, '角色卡'], ['/lorebooks', BookMarked, '世界书'], ['/extract', ScanSearch, '抽取角色']]],
  ['系统', 'SYSTEM', [['/settings', Settings, '设置']]],
]
const groupOf = (path) => nav.find(([, , items]) => items.some(([to]) => to !== '/' && path.startsWith(to)))?.[1] ?? (path === '/' ? 'LIBRARY' : '')

// 主题与侧栏折叠记在本机
const theme = ref(localStorage.getItem('front.theme') || 'dark')
const collapsed = ref(localStorage.getItem('front.sidebar') === 'collapsed')
watch(theme, (t) => { document.documentElement.dataset.theme = t; localStorage.setItem('front.theme', t) }, { immediate: true })
watch(collapsed, (c) => { localStorage.setItem('front.sidebar', c ? 'collapsed' : 'open'); nextTick(() => placePill(true)) })

// 侧栏高亮块
const scroller = ref(null)
const pill = ref(null)
function activeLink() {
  const links = [...(scroller.value?.querySelectorAll('.nav a') ?? [])]
  const p = route.path
  return links.find((a) => a.getAttribute('href') === p) ||
    links.filter((a) => a.getAttribute('href') !== '/' && p.startsWith(a.getAttribute('href'))).sort((a, b) => b.getAttribute('href').length - a.getAttribute('href').length)[0]
}
let first = true
function placePill(instant = false) { movePill(pill.value, activeLink(), scroller.value, instant || first); first = false }
watch(() => route.path, () => nextTick(() => placePill()))

// ⌘K / Ctrl+K / “/” 聚焦搜索（键盘操作不做动画）
function onKey(e) {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable
  if (((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') || (e.key === '/' && !typing)) { e.preventDefault(); searchEl.value?.focus() }
}
onMounted(() => { window.addEventListener('keydown', onKey); window.addEventListener('resize', onResize); setTimeout(() => placePill(true), 50) })
const onResize = () => placePill(true)
onBeforeUnmount(() => { window.removeEventListener('keydown', onKey); window.removeEventListener('resize', onResize) })
const isMac = /Mac|iPhone|iPad/.test(navigator.platform)
const version = __APP_VERSION__
</script>

<template>
  <RouterView v-if="$route.meta.bare" :key="$route.fullPath" />
  <div v-else class="layout" :class="{ collapsed }">
    <aside class="sidebar">
      <div class="brand"><img src="/favicon.svg" alt="" /><div>Front<small>创作素材库 · 百科数据库</small></div></div>
      <div ref="scroller" class="navscroll">
        <div ref="pill" class="nav-pill" />
        <template v-for="[group, en, items] in nav" :key="group">
          <div class="nav-group">{{ group }} · {{ en }}</div>
          <nav class="nav">
            <RouterLink v-for="[to, icon, label] in items" :key="to" :to="to" :title="collapsed ? label : undefined">
              <component :is="icon" class="ico" :size="17" :stroke-width="1.75" /><span class="lbl">{{ label }}</span>
            </RouterLink>
          </nav>
        </template>
      </div>
      <div class="sidebar-foot">
        <button class="ghost iconbtn" :title="theme === 'dark' ? '切换到浅色' : '切换到深色'" @click="theme = theme === 'dark' ? 'light' : 'dark'">
          <Sun v-if="theme === 'dark'" :size="16" /><Moon v-else :size="16" />
        </button>
        <span class="lbl small faint">v{{ version }}</span><span class="spacer lbl" />
        <button class="ghost iconbtn" :title="collapsed ? '展开侧栏' : '收起侧栏'" @click="collapsed = !collapsed">
          <PanelLeftOpen v-if="collapsed" :size="16" /><PanelLeftClose v-else :size="16" />
        </button>
      </div>
    </aside>
    <main class="main">
      <div class="topbar">
        <div><div class="crumb">{{ groupOf($route.path) }}</div><h1>{{ $route.meta.title }}</h1></div>
        <form class="searchbox" @submit.prevent="go">
          <input ref="searchEl" v-model="q" placeholder="全文搜索：角色、世界观、小说正文、提示词…" />
          <kbd>{{ isMac ? '⌘' : 'Ctrl' }} K</kbd>
        </form>
      </div>
      <RouterView v-slot="{ Component }">
        <Transition :css="false" mode="out-in" @enter="enterPage" @leave="(el, done) => done()">
          <div :key="$route.path" class="page"><component :is="Component" /></div>
        </Transition>
      </RouterView>
    </main>
  </div>
  <Transition :css="false" @enter="enterToast" @leave="leaveToast">
    <div v-if="toastState.msg" class="toast" :class="{ err: toastState.err }">{{ toastState.msg }}</div>
  </Transition>
</template>
