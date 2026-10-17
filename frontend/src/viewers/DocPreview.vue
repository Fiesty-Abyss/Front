<script setup>
import { computed } from 'vue'
const props = defineProps({ asset: { type: Object, required: true } })
const f = computed(() => props.asset.meta?.file || {})
const ext = computed(() => f.value.ext)
const blocks = computed(() => Array.isArray(f.value.preview) ? f.value.preview : [])
</script>
<template>
  <div class="dp">
    <div v-if="f.note" class="notice small">{{ f.note }}</div>
    <div v-else-if="['xlsx', 'ods'].includes(ext) && f.preview?.rows" class="sheet">
      <div class="row small" style="gap:6px;margin-bottom:8px"><span v-for="(s, i) in f.preview.sheets" :key="s" class="chip" :class="{ on: i === 0 }">{{ s }}</span><span class="faint">只预览第一个工作表的前 40 行</span></div>
      <div class="sheet-scroll"><table><tbody><tr v-for="(r, i) in f.preview.rows" :key="i"><th>{{ i + 1 }}</th><td v-for="(c, j) in r" :key="j">{{ c }}</td></tr></tbody></table></div>
    </div>
    <div v-else-if="['pptx', 'odp'].includes(ext) && blocks.length && blocks[0].lines" class="slides">
      <div v-for="(s, i) in blocks" :key="i" class="slide"><span class="no mono">{{ i + 1 }}</span><b>{{ s.title || '（无标题）' }}</b><ul><li v-for="(l, j) in s.lines" :key="j">{{ l }}</li></ul></div>
    </div>
    <article v-else-if="blocks.length" class="paper">
      <template v-for="(b, i) in blocks" :key="i">
        <h2 v-if="b.type === 'title' || b.type === 'h1'">{{ b.text }}</h2>
        <h3 v-else-if="/^h[2-6]$/.test(b.type)">{{ b.text }}</h3>
        <p v-else>{{ b.text }}</p>
      </template>
    </article>
    <div v-else class="muted small">没有可预览的文字</div>
  </div>
</template>
<style scoped>
.paper { max-height: 520px; overflow: auto; padding: 36px 48px; border-radius: var(--radius); background: #fbfaf7; color: #26242e; line-height: 1.85; font-size: 14.5px; }
.paper h2 { font-size: 21px; margin: .2em 0 .8em; } .paper h3 { font-size: 16.5px; margin: 1.4em 0 .5em; } .paper p { margin: 0 0 .8em; text-indent: 2em; }
.slides { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; max-height: 520px; overflow: auto; }
.slide { aspect-ratio: 16 / 10; padding: 16px 18px; border-radius: 10px; background: var(--panel2); border: 1px solid var(--line); position: relative; overflow: hidden; }
.slide b { display: block; font-size: 15px; margin-bottom: 8px; } .slide ul { margin: 0; padding-left: 18px; color: var(--muted); font-size: 12.5px; }
.slide .no { position: absolute; right: 10px; top: 8px; font-size: 11px; color: var(--faint); }
.sheet-scroll { max-height: 460px; overflow: auto; border-radius: 10px; border: 1px solid var(--line); }
.sheet table { border-collapse: collapse; font-size: 12.5px; min-width: 100%; }
.sheet th, .sheet td { border: 1px solid var(--line); padding: 5px 9px; white-space: nowrap; text-align: left; }
.sheet th { background: var(--panel2); color: var(--faint); font-weight: 500; width: 36px; }
.sheet tr:first-child td { font-weight: 600; background: var(--accent-soft); }
</style>
