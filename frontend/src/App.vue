<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { toastState } from './toast'

const router = useRouter()
const q = ref('')
const go = () => q.value.trim() && router.push({ path: '/search', query: { q: q.value.trim() } })
const nav = [
  ['资料库', [['/', '◎', '总览'], ['/assets', '▦', '素材库'], ['/import', '⇪', '批量导入'], ['/works', '❖', '作品 / CG'], ['/collections', '❒', '收藏集'], ['/tags', '#', '标签']]],
  ['百科', [['/characters', '☺', '角色百科'], ['/worlds', '◍', '世界观'], ['/graph', '◈', '关系网']]],
  ['AI 绘画', [['/generate', '✦', '出图'], ['/prompts', '✎', '提示词库'], ['/snippets', '❏', '提示词片段'], ['/models', '⬡', 'SD 模型库']]],
  ['AI 角色', [['/chat', '✉', 'AI 对话'], ['/cards', '▤', '角色卡'], ['/lorebooks', '❧', '世界书'], ['/extract', '⌕', '抽取角色']]],
  ['系统', [['/settings', '⚙', '设置']]],
]
</script>

<template>
  <RouterView v-if="$route.meta.bare" :key="$route.fullPath" />
  <div v-else class="layout">
    <aside class="sidebar">
      <div class="brand"><img src="/favicon.svg" alt="" /><div>Front<small>创作素材库 · 百科数据库</small></div></div>
      <template v-for="[group, items] in nav" :key="group">
        <div class="nav-group">{{ group }}</div>
        <nav class="nav">
          <RouterLink v-for="[to, icon, label] in items" :key="to" :to="to"><span>{{ icon }}</span>{{ label }}</RouterLink>
        </nav>
      </template>
    </aside>
    <main class="main">
      <div class="topbar">
        <h1>{{ $route.meta.title }}</h1>
        <form class="searchbox" @submit.prevent="go"><input v-model="q" placeholder="全文搜索：角色、世界观、小说正文、提示词…" /></form>
      </div>
      <RouterView :key="$route.path" />
    </main>
  </div>
  <div v-if="toastState.msg" class="toast" :class="{ err: toastState.err }">{{ toastState.msg }}</div>
</template>
