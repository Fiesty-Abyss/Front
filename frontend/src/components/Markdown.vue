<script setup>
// 安全的 Markdown 渲染：禁用原始 HTML；[[名称]] 渲染为站内搜索链接
import MarkdownIt from 'markdown-it'
import { computed } from 'vue'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const props = defineProps({ source: { type: String, default: '' } })
const html = computed(() => {
  const escaped = (props.source || '').replace(/\[\[([^\]\n]{1,60})\]\]/g, (_, name) => `[${name}](/search?q=${encodeURIComponent(name)})`)
  return md.render(escaped)
})
</script>
<template>
  <div class="md" v-html="html" />
</template>
<style>
.md { line-height: 1.8; }
.md h1, .md h2, .md h3 { margin: 1em 0 .5em; }
.md h1 { font-size: 20px; } .md h2 { font-size: 17px; } .md h3 { font-size: 15px; }
.md p { margin: .5em 0; }
.md a { color: #c4b5fd; text-decoration: underline; text-underline-offset: 3px; }
.md blockquote { margin: .6em 0; padding: 4px 14px; border-left: 3px solid var(--accent); color: var(--muted); background: var(--accent-soft); border-radius: 0 8px 8px 0; }
.md code { background: var(--panel2); padding: 1px 5px; border-radius: 4px; font-size: 12px; }
.md table { border-collapse: collapse; margin: .6em 0; }
.md th, .md td { border: 1px solid var(--line); padding: 5px 10px; }
.md ul, .md ol { padding-left: 1.4em; margin: .4em 0; }
</style>
