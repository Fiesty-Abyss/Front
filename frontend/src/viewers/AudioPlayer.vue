<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { Play, Pause, Volume2, VolumeX, Download } from 'lucide-vue-next'
import { fileUrl, hasThumb, thumb } from '../api'
import KindIcon from '../components/KindIcon.vue'

const props = defineProps({ asset: { type: Object, required: true } })
const el = ref(null)
const playing = ref(false)
const t = ref(0)
const dur = ref(props.asset.meta?.file?.duration || 0)
const muted = ref(false)
const f = computed(() => props.asset.meta?.file || {})
const fmt = (s) => { s = Math.max(0, Math.floor(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` }
function toggle() { el.value.paused ? el.value.play() : el.value.pause() }
function seek(e) { el.value.currentTime = Number(e.target.value) }
onBeforeUnmount(() => el.value?.pause())
</script>
<template>
  <div class="ap">
    <div class="cover">
      <img v-if="hasThumb(asset)" :src="thumb(asset.id, asset.updated_at)" alt="" />
      <KindIcon v-else :asset="asset" :size="44" />
    </div>
    <div class="body">
      <div class="eyebrow">{{ [f.genre, f.year].filter(Boolean).join(' · ') || '音频' }}</div>
      <h3>{{ f.title || asset.title }}</h3>
      <div class="muted">{{ [f.artist, f.album].filter(Boolean).join(' — ') || '未知艺术家' }}</div>
      <div class="ctl">
        <button class="primary play" :aria-label="playing ? '暂停' : '播放'" @click="toggle"><component :is="playing ? Pause : Play" :size="18" /></button>
        <span class="mono small">{{ fmt(t) }}</span>
        <input class="seek" type="range" min="0" :max="dur || 0" step="0.1" :value="t" :style="{ '--p': dur ? (t / dur) * 100 + '%' : '0%' }" @input="seek" />
        <span class="mono small faint">{{ fmt(dur) }}</span>
        <button class="ghost iconbtn" :aria-label="muted ? '取消静音' : '静音'" @click="muted = !muted"><component :is="muted ? VolumeX : Volume2" :size="16" /></button>
        <a class="ghost iconbtn btn" :href="fileUrl(asset.id)" title="下载原文件"><Download :size="16" /></a>
      </div>
    </div>
    <audio ref="el" :src="fileUrl(asset.id, true)" preload="metadata" :muted="muted" @play="playing = true" @pause="playing = false"
      @timeupdate="t = $event.target.currentTime" @loadedmetadata="dur = $event.target.duration || dur" @ended="playing = false" />
  </div>
</template>
<style scoped>
.ap { display: grid; grid-template-columns: 168px 1fr; gap: 22px; align-items: center; padding: 18px; border-radius: var(--radius-lg);
  background: radial-gradient(120% 140% at 0% 0%, var(--accent-soft), transparent 60%), var(--panel2); border: 1px solid var(--line); }
.cover { width: 168px; aspect-ratio: 1; border-radius: 14px; overflow: hidden; box-shadow: 0 18px 40px -18px rgba(0, 0, 0, .7); }
.cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
h3 { margin: 4px 0 2px; font-size: 20px; }
.ctl { display: flex; align-items: center; gap: 10px; margin-top: 18px; }
.play { width: 44px; height: 44px; border-radius: 50%; padding: 0; justify-content: center; flex: none; }
.seek { flex: 1; -webkit-appearance: none; appearance: none; height: 4px; border-radius: 4px; padding: 0; border: 0;
  background: linear-gradient(to right, var(--accent) var(--p), var(--line-strong) var(--p)); }
.seek::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; border-radius: 50%; background: var(--text); }
</style>
