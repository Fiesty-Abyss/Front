<script setup>
// 浏览器查询：在新标签页打开各站点的搜索结果。只是链接——Front 不抓取、不下载任何内容。
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Globe, ExternalLink, Settings2 } from 'lucide-vue-next'
import { api } from '../api'
import { gsap, reduced } from '../motion'

const props = defineProps({ q: { type: String, required: true }, kind: { type: String, default: '' }, alts: { type: Array, default: () => [] }, small: Boolean })
const open = ref(false)
const term = ref(props.q)
const links = ref([])
const loading = ref(false)
const root = ref(null)
const pop = ref(null)
const terms = computed(() => [...new Set([props.q, ...props.alts].map((s) => (s || '').trim()).filter(Boolean))])
watch(() => props.q, (v) => { term.value = v })

async function load() {
  if (!term.value.trim()) return
  loading.value = true
  try { links.value = await api.get('/api/quick-search', { q: term.value, kind: props.kind }) } finally { loading.value = false }
}
async function toggle() {
  open.value = !open.value
  if (!open.value) return
  await load()
  await nextTick()
  if (pop.value && !reduced()) gsap.fromTo(pop.value, { autoAlpha: 0, y: -4, scale: 0.98 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.2, transformOrigin: 'top right', clearProps: 'transform,opacity,visibility' })
}
const outside = (e) => { if (open.value && root.value && !root.value.contains(e.target)) open.value = false }
document.addEventListener('mousedown', outside)
onBeforeUnmount(() => document.removeEventListener('mousedown', outside))
watch(term, () => open.value && load())
</script>

<template>
  <span ref="root" class="qs">
    <button :class="{ ghost: small }" type="button" title="在浏览器中搜索（只打开链接）" @click.stop="toggle" @keydown.esc="open = false">
      <Globe :size="14" />浏览器查询
    </button>
    <div v-if="open" ref="pop" class="qs-pop" @keydown.esc="open = false">
      <div class="row" style="flex-wrap:nowrap;gap:6px">
        <input v-model.lazy="term" class="qs-term" aria-label="搜索关键词" />
      </div>
      <div v-if="terms.length > 1" class="row qs-alts">
        <span v-for="t in terms" :key="t" class="chip click" :class="{ on: t === term }" @click="term = t">{{ t }}</span>
      </div>
      <div class="qs-list">
        <a v-for="l in links" :key="l.id" :href="l.url" target="_blank" rel="noopener noreferrer nofollow" class="qs-item">
          <span class="qs-ico">{{ l.name.slice(0, 1) }}</span>
          <span class="qs-txt"><b>{{ l.name }}</b><small>{{ l.search ? l.host : l.host + ' · 主页' }}</small></span>
          <ExternalLink :size="13" class="faint" />
        </a>
        <div v-if="!loading && !links.length" class="small muted" style="padding:8px">没有适用的站点，可以在设置里添加</div>
      </div>
      <RouterLink to="/settings#quick-search" class="small faint qs-foot"><Settings2 :size="12" />管理站点 · 只打开链接，不抓取、不下载</RouterLink>
    </div>
  </span>
</template>

<style scoped>
.qs { position: relative; display: inline-block; }
.qs-pop { position: absolute; right: 0; top: calc(100% + 8px); z-index: 40; width: 300px; padding: 10px; border-radius: 14px; background: var(--panel); border: 1px solid var(--line-strong); box-shadow: var(--shadow-pop); }
.qs-term { padding: 6px 10px; }
.qs-alts { gap: 4px; margin-top: 8px; }
.qs-list { display: grid; gap: 2px; margin: 8px 0 6px; max-height: 320px; overflow: auto; }
.qs-item { display: flex; align-items: center; gap: 10px; padding: 7px 8px; border-radius: 10px; transition: background-color .12s var(--ease-out); }
.qs-item:hover { background: var(--accent-soft); }
.qs-ico { width: 26px; height: 26px; border-radius: 8px; display: grid; place-items: center; background: var(--panel2); color: var(--accent-hi); font-weight: 700; font-size: 12px; flex: none; }
.qs-txt { display: grid; flex: 1; min-width: 0; line-height: 1.3; }
.qs-txt small { color: var(--faint); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.qs-foot { display: flex; gap: 5px; align-items: center; padding: 6px 4px 0; border-top: 1px solid var(--line); }
</style>
