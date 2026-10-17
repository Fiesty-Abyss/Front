<script setup>
// CG 鉴赏模式：← → 切换 CG，↑ ↓ / 数字键切换差分，空格自动播放，Esc 退出
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fileUrl, thumb } from '../api'

const props = defineProps({ groups: { type: Array, required: true }, start: { type: Number, default: 0 }, title: String })
const emit = defineEmits(['close'])
const gi = ref(props.start)
const vi = ref(0)
const playing = ref(false)
const showUi = ref(true)
let timer = null

const group = computed(() => props.groups[gi.value])
const item = computed(() => group.value?.items[vi.value])
const flat = computed(() => props.groups.flatMap((g, a) => g.items.map((_, b) => [a, b])))
const pos = computed(() => flat.value.findIndex(([a, b]) => a === gi.value && b === vi.value))

function goGroup(d) { gi.value = (gi.value + d + props.groups.length) % props.groups.length; vi.value = 0 }
function goVariant(d) { const n = group.value.items.length; vi.value = (vi.value + d + n) % n }
function step() { const [a, b] = flat.value[(pos.value + 1) % flat.value.length]; gi.value = a; vi.value = b }
function toggle() { playing.value = !playing.value }
watch(playing, (p) => { clearInterval(timer); if (p) timer = setInterval(step, 3000) })
watch(item, () => {
  // 预加载下一张
  const next = flat.value[(pos.value + 1) % flat.value.length]
  if (next) new Image().src = fileUrl(props.groups[next[0]].items[next[1]].id)
})
function onKey(e) {
  const k = e.key
  if (k === 'Escape') emit('close')
  else if (k === 'ArrowRight') goGroup(1)
  else if (k === 'ArrowLeft') goGroup(-1)
  else if (k === 'ArrowDown') goVariant(1)
  else if (k === 'ArrowUp') goVariant(-1)
  else if (k === ' ') { e.preventDefault(); toggle() }
  else if (k === 'h') showUi.value = !showUi.value
  else if (/^[1-9]$/.test(k) && Number(k) <= group.value.items.length) vi.value = Number(k) - 1
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => { window.removeEventListener('keydown', onKey); clearInterval(timer) })
</script>
<template>
  <div class="viewer" @click.self="showUi = !showUi">
    <img v-if="item" :key="item.id" class="viewer-img" :src="fileUrl(item.id)" :alt="item.title" @click="showUi = !showUi" />
    <template v-if="showUi">
      <div class="viewer-top">
        <b>{{ title }}</b><span class="muted">· {{ group.key }}</span>
        <span class="badge">CG {{ gi + 1 }} / {{ groups.length }}</span>
        <span class="badge">差分 {{ vi + 1 }} / {{ group.items.length }}{{ item?.variant ? ` · ${item.variant}` : '' }}</span>
        <span class="badge">{{ group.size }}</span>
        <span class="spacer" />
        <button @click="toggle">{{ playing ? '❚❚ 暂停' : '▶ 自动播放' }}</button>
        <button @click="$emit('close')">✕ 退出</button>
      </div>
      <button class="viewer-nav left" @click="goGroup(-1)">‹</button>
      <button class="viewer-nav right" @click="goGroup(1)">›</button>
      <div class="viewer-strip">
        <div v-for="(it, i) in group.items" :key="it.id" class="viewer-thumb" :class="{ on: i === vi }" :style="{ backgroundImage: `url(${thumb(it.id)})` }" @click="vi = i"><span>{{ it.variant || i + 1 }}</span></div>
      </div>
      <div class="viewer-help small">← → 切换 CG · ↑ ↓ / 1-9 切换差分 · 空格 自动播放 · H 隐藏界面 · Esc 退出</div>
    </template>
  </div>
</template>
<style scoped>
.viewer { position: fixed; inset: 0; background: #000; z-index: 80; display: flex; align-items: center; justify-content: center; }
.viewer-img { max-width: 100vw; max-height: 100vh; object-fit: contain; user-select: none; }
.viewer-top { position: absolute; top: 0; left: 0; right: 0; display: flex; gap: 10px; align-items: center; padding: 12px 18px; background: linear-gradient(#000c, #0000); }
.viewer-nav { position: absolute; top: 50%; transform: translateY(-50%); font-size: 40px; background: #0006; border: none; width: 56px; height: 96px; justify-content: center; }
.viewer-nav.left { left: 12px; } .viewer-nav.right { right: 12px; }
.viewer-strip { position: absolute; bottom: 34px; left: 50%; transform: translateX(-50%); display: flex; gap: 8px; padding: 8px; background: #000a; border-radius: 12px; }
.viewer-thumb { width: 96px; height: 54px; border-radius: 6px; background: center/cover; border: 2px solid transparent; cursor: pointer; position: relative; }
.viewer-thumb.on { border-color: var(--accent2); }
.viewer-thumb span { position: absolute; right: 4px; bottom: 2px; font-size: 11px; text-shadow: 0 0 3px #000; }
.viewer-help { position: absolute; bottom: 8px; left: 0; right: 0; text-align: center; color: #fff9; }
</style>
