<script setup>
// 素材详情里的文件预览：按类型选择查看器，下面统一列出提取到的元数据。
import { computed, defineAsyncComponent, ref } from 'vue'
import { Download, RefreshCw, Info } from 'lucide-vue-next'
import { api, entryUrl, fileUrl, hasThumb, thumb } from '../api'
import { guard, toast } from '../toast'
import AudioPlayer from './AudioPlayer.vue'
import PdfViewer from './PdfViewer.vue'
import DocPreview from './DocPreview.vue'
const ModelViewer = defineAsyncComponent(() => import('./ModelViewer.vue'))
const CodeView = defineAsyncComponent(() => import('./CodeView.vue'))

const props = defineProps({ asset: { type: Object, required: true } })
const emit = defineEmits(['updated'])
const f = computed(() => props.asset.meta?.file || {})
const k = computed(() => props.asset.kind)
const zoom = ref(null)

const size = (n) => (n == null ? '' : n > 1 << 30 ? (n / (1 << 30)).toFixed(2) + ' GB' : n > 1 << 20 ? (n / (1 << 20)).toFixed(1) + ' MB' : (n / 1024).toFixed(1) + ' KB')
const dur = (s) => { s = Math.round(s); const h = Math.floor(s / 3600); const m = Math.floor((s % 3600) / 60); return (h ? `${h}:${String(m).padStart(2, '0')}` : m) + ':' + String(s % 60).padStart(2, '0') }
const YES = (v) => (v === true ? '是' : v === false ? '否' : v)
const PERM = { everyone: '所有人', onlyAuthor: '仅作者', onlySeparatelyLicensedPerson: '需单独授权', OnlyAuthor: '仅作者', ExplicitlyLicensedPerson: '需单独授权', Everyone: '所有人',
  personalNonProfit: '个人非营利', personalProfit: '个人营利', corporation: '法人 / 商用', Allow: '允许', Disallow: '不允许', prohibited: '禁止', allowModification: '允许修改', allowModificationRedistribution: '允许修改并再分发', required: '需要署名', unnecessary: '不需要署名' }
const LABEL = [
  ['format', '格式'], ['label', '类型'], ['generator', '导出工具'], ['application', '创建程序'], ['model_name', '模型名'], ['model_name_en', '英文名'],
  ['cubism', 'Cubism 版本'], ['pmx_version', 'PMX 版本'], ['fbx_version', 'FBX 版本'], ['encoding', '编码'], ['gltf_version', 'glTF 版本'],
  ['vertices', '顶点', (v) => v.toLocaleString()], ['triangles', '三角面', (v) => v.toLocaleString()], ['faces', '面', (v) => v.toLocaleString()],
  ['meshes', '网格'], ['materials', '材质'], ['bones', '骨骼'], ['skins', '蒙皮'], ['nodes', '节点'], ['groups', '分组', (v) => (typeof v === 'object' ? Object.entries(v).map(([a, b]) => `${a}（${b}）`).join('、') : v)],
  ['animations', '动画', (v) => v.join('、')], ['extensions', 'glTF 扩展', (v) => v.join('、')], ['physics', '物理', YES], ['pose', '姿势', YES], ['hit_areas', '点击区域', (v) => v.join('、')],
  ['title', '标题'], ['artist', '艺术家'], ['album', '专辑'], ['albumartist', '专辑艺术家'], ['composer', '作曲'], ['genre', '流派'], ['year', '年份'], ['track', '音轨', (v) => (f.value.track_total ? `${v} / ${f.value.track_total}` : v)],
  ['duration', '时长', dur], ['bitrate', '码率', (v) => `${v} kbps`], ['samplerate', '采样率', (v) => `${(v / 1000).toFixed(1)} kHz`], ['channels', '声道'], ['bitdepth', '位深', (v) => `${v} bit`],
  ['resolution', '分辨率'], ['video_codec', '视频编码'], ['fps', '帧率', (v) => `${v} fps`], ['audio_codec', '音频编码'], ['container', '封装'],
  ['author', '作者'], ['subject', '主题'], ['creator', '创建工具'], ['producer', '生成工具'], ['created', '创建时间', (v) => String(v).replace('T', ' ').replace('Z', '')],
  ['last_modified_by', '最后修改'], ['pages', '页数'], ['page_size', '页面尺寸'], ['words', '字数'], ['slides', '幻灯片'], ['chapters', '章节'], ['language', '语言'], ['lines', '行数'],
  ['count', '文件数'], ['unpacked_size', '解压后', size], ['encrypted', '加密', YES], ['files', '包内文件'],
]
const rows = computed(() => LABEL.filter(([key]) => f.value[key] != null && f.value[key] !== '' && !(Array.isArray(f.value[key]) && !f.value[key].length))
  .map(([key, label, fmt]) => [label, fmt ? fmt(f.value[key]) : f.value[key]]))
const vrm = computed(() => f.value.vrm_meta)
const VRM_LABEL = [['name', '名称'], ['model_version', '版本'], ['authors', '作者', (v) => v.join('、')], ['license', '许可'], ['license_url', '许可链接'], ['avatar_permission', '谁可以使用'],
  ['commercial_usage', '商用'], ['allow_redistribution', '再分发', YES], ['modification', '修改'], ['credit_notation', '署名'], ['allow_violent', '暴力表现', YES], ['allow_sexual', '性表现', YES], ['contact', '联系方式'], ['copyright', '版权']]
const vrmRows = computed(() => (vrm.value ? VRM_LABEL.filter(([key]) => vrm.value[key] != null && vrm.value[key] !== '').map(([key, label, fmt]) => [label, fmt ? fmt(vrm.value[key]) : PERM[vrm.value[key]] ?? vrm.value[key]]) : []))
const entries = computed(() => f.value.entries || [])
const isImg = (n) => /\.(png|jpe?g|webp|gif|bmp)$/i.test(n)

async function snapshot(blob) {
  const form = new FormData(); form.append('file', blob, 'snapshot.png')
  const a = await guard(() => api.upload(`/api/assets/${props.asset.id}/thumb`, form, 'PUT'), '已设为封面')
  emit('updated', a)
}
async function reanalyze() {
  const a = await guard(() => api.post(`/api/assets/${props.asset.id}/reanalyze`), '已重新识别')
  emit('updated', a)
}
</script>

<template>
  <div class="fp">
    <!-- 3D -->
    <template v-if="k === 'model3d'">
      <ModelViewer v-if="f.previewable && !f.error" :asset="asset" @snapshot="snapshot" />
      <div v-else class="fp-empty"><img v-if="hasThumb(asset)" :src="thumb(asset.id, asset.updated_at)" alt="" /><span>{{ f.error ? '文件无法解析' : '这个格式只显示信息' }}</span></div>
    </template>
    <!-- Live2D -->
    <div v-else-if="k === 'live2d'" class="l2d">
      <div class="l2d-tex">
        <figure v-for="t in f.textures || []" :key="t.path" class="click" @click="zoom = entryUrl(asset.id, t.path)">
          <img :src="entryUrl(asset.id, t.path)" :alt="t.path" loading="lazy" /><figcaption class="mono">{{ t.path.split('/').pop() }}<span class="faint"> · {{ t.size }}</span></figcaption>
        </figure>
        <div v-if="!(f.textures || []).length" class="fp-empty"><span>{{ f.note || '没有找到贴图' }}</span></div>
      </div>
      <div class="l2d-side">
        <div v-if="Object.keys(f.motion_files || f.motions || {}).length"><div class="eyebrow">动作</div>
          <div v-for="(n, g) in f.motions" :key="g" class="row small" style="gap:6px;margin-top:6px"><b>{{ g }}</b><span class="badge">{{ n }}</span>
            <span v-for="p in (f.motion_files?.[g] || []).slice(0, 4)" :key="p" class="chip mono">{{ p.split('/').pop().replace(/\.motion3?\.json$|\.mtn$/, '') }}</span></div></div>
        <div v-if="f.expressions?.length" style="margin-top:12px"><div class="eyebrow">表情</div><div class="row small" style="gap:6px;margin-top:6px"><span v-for="e in f.expressions" :key="e" class="chip">{{ e }}</span></div></div>
        <div v-if="f.missing?.length" class="notice small" style="margin-top:12px">包里缺少 {{ f.missing.length }} 个被引用的文件：<span class="mono">{{ f.missing.slice(0, 3).join('、') }}</span></div>
        <p class="small faint" style="margin-top:12px"><Info :size="12" style="vertical-align:-2px" /> 网页内实时预览需要 Live2D 官方的 Cubism Core（专有许可，Front 不附带）。这里展示贴图、动作和表情信息。</p>
      </div>
    </div>
    <AudioPlayer v-else-if="k === 'audio'" :asset="asset" />
    <template v-else-if="k === 'video'">
      <video v-if="f.playable" class="fp-video" :src="fileUrl(asset.id, true)" :poster="hasThumb(asset) ? thumb(asset.id, asset.updated_at) : undefined" controls preload="metadata" />
      <div v-else class="fp-empty"><img v-if="hasThumb(asset)" :src="thumb(asset.id, asset.updated_at)" alt="" /><span>浏览器不能直接播放 {{ f.ext }}，可以下载后用播放器打开</span></div>
    </template>
    <PdfViewer v-else-if="k === 'pdf' && f.pages" :asset="asset" />
    <DocPreview v-else-if="k === 'document'" :asset="asset" />
    <div v-else-if="k === 'archive'" class="arc">
      <div v-if="f.note" class="notice small">{{ f.note }}</div>
      <div v-if="f.by_ext" class="row small" style="gap:6px;margin-bottom:8px"><span v-for="(n, e) in f.by_ext" :key="e" class="chip">{{ e }} <span class="faint">{{ n }}</span></span></div>
      <div v-if="entries.length" class="arc-list">
        <div v-for="e in entries" :key="e.name" class="arc-row" :class="{ click: isImg(e.name) && f.format === 'zip' }" @click="isImg(e.name) && f.format === 'zip' && (zoom = entryUrl(asset.id, e.name))">
          <span class="mono ellip">{{ e.name }}</span><span class="faint small mono">{{ size(e.size) }}</span></div>
        <div v-if="f.count > entries.length" class="small faint" style="padding:6px 10px">… 还有 {{ f.count - entries.length }} 个文件</div>
      </div>
    </div>
    <CodeView v-else-if="k === 'code' && asset.content" :asset="asset" />

    <div class="fp-meta">
      <div class="row" style="gap:8px"><span class="eyebrow">文件信息</span><span class="spacer" />
        <button class="ghost small" title="重新读取文件信息" @click="reanalyze"><RefreshCw :size="13" />重新识别</button>
        <a class="btn ghost small" :href="fileUrl(asset.id)"><Download :size="13" />下载原文件</a></div>
      <dl class="kv">
        <template v-for="[l, v] in rows" :key="l"><dt>{{ l }}</dt><dd>{{ v }}</dd></template>
        <dt>文件</dt><dd class="mono">{{ asset.original_name }} · {{ size(asset.size) }}</dd>
      </dl>
      <div v-if="f.comment" class="small muted pre">{{ f.comment }}</div>
      <div v-if="vrmRows.length" class="vrm"><div class="eyebrow">VRM 使用条件<span class="faint">（模型作者写在文件里的许可，使用前请确认）</span></div>
        <dl class="kv"><template v-for="[l, v] in vrmRows" :key="l"><dt>{{ l }}</dt><dd>{{ v }}</dd></template></dl></div>
      <div v-if="f.note && k !== 'archive' && k !== 'live2d'" class="notice small">{{ f.note }}</div>
      <div v-if="f.error" class="notice small danger">读取失败：{{ f.error }}</div>
    </div>
    <div v-if="zoom" class="zoom" @click="zoom = null"><img :src="zoom" alt="" /></div>
  </div>
</template>

<style scoped>
.fp { display: grid; gap: 14px; }
.fp-empty { min-height: 200px; display: grid; place-items: center; gap: 10px; border-radius: var(--radius); background: var(--sunken); border: 1px solid var(--line); color: var(--muted); font-size: 13px; padding: 20px; }
.fp-empty img { max-height: 260px; border-radius: 10px; }
.fp-video { width: 100%; max-height: 520px; border-radius: var(--radius); background: #000; }
.fp-meta { display: grid; gap: 10px; padding: 14px 16px; border-radius: var(--radius); background: var(--panel2); border: 1px solid var(--line); }
.kv { display: grid; grid-template-columns: 88px minmax(0, 1fr) 88px minmax(0, 1fr); gap: 7px 14px; margin: 0; }
.kv dt { color: var(--faint); font-size: 12.5px; }
.kv dd { margin: 0; font-size: 12.5px; overflow-wrap: anywhere; }
.pre { white-space: pre-wrap; max-height: 120px; overflow: auto; }
.vrm { border-top: 1px solid var(--line); padding-top: 10px; display: grid; gap: 8px; }
.l2d { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 16px; }
.l2d-tex { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; align-content: start; }
.l2d-tex figure { margin: 0; border-radius: 10px; overflow: hidden; border: 1px solid var(--line);
  background: repeating-conic-gradient(var(--panel2) 0 25%, var(--sunken) 0 50%) 50% / 16px 16px; }
.l2d-tex img { width: 100%; aspect-ratio: 1; object-fit: contain; display: block; }
.l2d-tex figcaption { font-size: 11px; padding: 5px 8px; background: var(--panel); }
.arc-list { max-height: 360px; overflow: auto; border-radius: 10px; border: 1px solid var(--line); }
.arc-row { display: flex; justify-content: space-between; gap: 12px; padding: 5px 10px; font-size: 12.5px; }
.arc-row:nth-child(odd) { background: var(--panel2); }
.arc-row.click:hover { background: var(--accent-soft); }
.ellip { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.zoom { position: fixed; inset: 0; z-index: 80; background: var(--mask); display: grid; place-items: center; cursor: zoom-out; backdrop-filter: blur(6px); }
.zoom img { max-width: 90vw; max-height: 90vh; border-radius: 10px; background: repeating-conic-gradient(#2a2a3a 0 25%, #1c1c29 0 50%) 50% / 20px 20px; }
.danger { color: var(--danger); }
</style>
