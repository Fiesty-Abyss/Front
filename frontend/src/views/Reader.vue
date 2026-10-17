<script setup>
// 小说阅读模式：目录、翻章、字号 / 行距 / 主题，阅读进度保存在本机浏览器
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)
const toc = ref(null)
const ch = ref(null)
const showToc = ref(true)
const page = ref(null)
const PREF_KEY = 'front.reader.prefs'
const prefs = reactive({ size: 19, line: 1.9, theme: 'night', width: 760, ...JSON.parse(localStorage.getItem(PREF_KEY) || '{}') })
watch(prefs, () => localStorage.setItem(PREF_KEY, JSON.stringify(prefs)))
const THEMES = { night: ['#14151f', '#d9d6cf', '夜间'], paper: ['#f4ecd8', '#3b3226', '羊皮纸'], light: ['#fafafa', '#222', '白天'], green: ['#cfe3cf', '#253325', '护眼'] }
const theme = computed(() => THEMES[prefs.theme])
const progressKey = `front.reader.progress.${id}`

async function open(index) {
  ch.value = await api.get(`/api/assets/${id}/chapters/${index}`)
  localStorage.setItem(progressKey, String(index))
  page.value?.scrollTo(0, 0)
  document.title = `${ch.value.title} · ${ch.value.book_title}`
}
onMounted(async () => {
  toc.value = await api.get(`/api/assets/${id}/chapters`)
  const saved = Number(route.query.ch ?? localStorage.getItem(progressKey) ?? 0)
  open(saved < toc.value.chapters.length ? saved : 0)
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
function onKey(e) {
  if (e.target.tagName === 'INPUT') return
  if (e.key === 'ArrowRight' && ch.value?.next != null) open(ch.value.next)
  if (e.key === 'ArrowLeft' && ch.value?.prev != null) open(ch.value.prev)
}
const paragraphs = computed(() => (ch.value?.content ?? '').split(/\n+/).map((p) => p.trim()).filter(Boolean))
const pct = computed(() => (toc.value && ch.value ? Math.round(((ch.value.index + 1) / ch.value.total) * 100) : 0))
</script>
<template>
  <div class="reader" :style="{ background: theme[0], color: theme[1] }">
    <header class="reader-bar">
      <button class="ghost" @click="router.back()">← 返回</button>
      <button class="ghost" @click="showToc = !showToc">☰ 目录</button>
      <button class="ghost" title="用 AI 从这篇小说里抽取角色" @click="router.push(`/extract?asset=${route.params.id}`)"><Ico g="⌕" />抽取角色</button>
      <b v-if="toc">{{ toc.title }}</b><span v-if="toc" class="small" style="opacity:.6">共 {{ toc.chapters.length }} 章 · {{ toc.words.toLocaleString() }} 字</span>
      <span class="spacer" />
      <span class="small" style="opacity:.6">字号</span><button class="ghost" @click="prefs.size = Math.max(14, prefs.size - 1)">A-</button><span class="small">{{ prefs.size }}</span><button class="ghost" @click="prefs.size = Math.min(32, prefs.size + 1)">A+</button>
      <span class="small" style="opacity:.6">行距</span><select v-model.number="prefs.line" style="width:70px"><option v-for="l in [1.6, 1.8, 1.9, 2.1, 2.4]" :key="l" :value="l">{{ l }}</option></select>
      <span v-for="(t, k) in THEMES" :key="k" class="swatch" :class="{ on: prefs.theme === k }" :style="{ background: t[0], color: t[1] }" :title="t[2]" @click="prefs.theme = k">文</span>
    </header>
    <div class="reader-body">
      <aside v-if="showToc && toc" class="reader-toc">
        <a v-for="c in toc.chapters" :key="c.index" :class="{ on: ch?.index === c.index }" @click="open(c.index)">{{ c.title }}<span>{{ c.words }}</span></a>
      </aside>
      <main ref="page" class="reader-page">
        <article v-if="ch" :style="{ fontSize: prefs.size + 'px', lineHeight: prefs.line, maxWidth: prefs.width + 'px' }">
          <h1>{{ ch.title }}</h1>
          <p v-for="(p, i) in paragraphs" :key="i">{{ p }}</p>
          <nav class="reader-nav">
            <button :disabled="ch.prev == null" @click="open(ch.prev)">← 上一章</button>
            <span class="small" style="opacity:.6">{{ ch.index + 1 }} / {{ ch.total }} · 本章 {{ ch.words }} 字 · 进度 {{ pct }}%</span>
            <button :disabled="ch.next == null" @click="open(ch.next)">下一章 →</button>
          </nav>
        </article>
      </main>
    </div>
  </div>
</template>
<style scoped>
.reader { height: 100vh; display: flex; flex-direction: column; font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", SimSun, serif; }
.reader-bar { display: flex; align-items: center; gap: 10px; padding: 10px 18px; border-bottom: 1px solid #8884; font-family: "Noto Sans SC", system-ui, sans-serif; }
.reader-bar button, .reader-bar select { color: inherit; border-color: #8886; background: transparent; }
.reader-body { flex: 1; display: flex; min-height: 0; }
.reader-toc { width: 260px; overflow: auto; border-right: 1px solid #8884; padding: 10px; font-family: "Noto Sans SC", system-ui, sans-serif; }
.reader-toc a { display: flex; justify-content: space-between; gap: 8px; padding: 7px 10px; border-radius: 8px; cursor: pointer; font-size: 14px; }
.reader-toc a span { opacity: .45; font-size: 12px; }
.reader-toc a.on, .reader-toc a:hover { background: #8883; }
.reader-page { flex: 1; overflow: auto; padding: 30px 40px 60px; }
.reader-page article { margin: 0 auto; }
.reader-page h1 { font-size: 1.5em; margin: .4em 0 1.2em; text-align: center; letter-spacing: .05em; }
.reader-page p { margin: 0 0 .9em; text-indent: 2em; text-align: justify; }
.reader-nav { display: flex; justify-content: space-between; align-items: center; margin-top: 48px; font-family: "Noto Sans SC", system-ui, sans-serif; font-size: 14px; }
.reader-nav button { color: inherit; background: transparent; border-color: #8886; }
.swatch { width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; cursor: pointer; border: 2px solid #8886; }
.swatch.on { border-color: var(--accent2); }
</style>
