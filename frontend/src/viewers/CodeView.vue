<script setup>
import { onMounted, ref } from 'vue'
import hljs from 'highlight.js/lib/common'
const props = defineProps({ asset: { type: Object, required: true } })
const html = ref('')
onMounted(() => {
  const src = (props.asset.content || '').slice(0, 200000)
  const lang = props.asset.meta?.file?.language
  try { html.value = lang && lang !== 'plaintext' && hljs.getLanguage(lang) ? hljs.highlight(src, { language: lang }).value : hljs.highlightAuto(src).value } catch { html.value = src.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]) }
})
const lines = (props.asset.content || '').split('\n').length
</script>
<template>
  <div class="cv">
    <pre class="gutter mono" aria-hidden="true">{{ Array.from({ length: Math.min(lines, 20000) }, (_, i) => i + 1).join('\n') }}</pre>
    <pre class="code mono hljs"><code v-html="html" /></pre>
  </div>
</template>
<style scoped>
.cv { display: flex; max-height: 520px; overflow: auto; border-radius: var(--radius); background: var(--sunken); border: 1px solid var(--line); font-size: 12.5px; line-height: 1.6; }
.gutter { margin: 0; padding: 14px 10px 14px 14px; text-align: right; color: var(--faint); user-select: none; border-right: 1px solid var(--line); position: sticky; left: 0; background: var(--sunken); }
.code { margin: 0; padding: 14px 16px; flex: 1; background: none; }
.code :deep(.hljs-keyword), .code :deep(.hljs-built_in) { color: #c39cf0; }
.code :deep(.hljs-string) { color: #8fd6a8; } .code :deep(.hljs-number), .code :deep(.hljs-literal) { color: #f2c26b; }
.code :deep(.hljs-comment) { color: var(--faint); font-style: italic; } .code :deep(.hljs-title), .code :deep(.hljs-attr) { color: #7cc4f5; }
:root[data-theme="light"] .code :deep(.hljs-keyword) { color: #7c4dbd; } :root[data-theme="light"] .code :deep(.hljs-string) { color: #23854a; }
:root[data-theme="light"] .code :deep(.hljs-number) { color: #a86a00; } :root[data-theme="light"] .code :deep(.hljs-title), :root[data-theme="light"] .code :deep(.hljs-attr) { color: #1f6fb2; }
</style>
