<script setup>
// 3D 模型预览：glTF / GLB / VRM / OBJ(+MTL) / FBX / PMX。模型包（zip）里的贴图通过 /entry/ 接口按需读取。
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import { MTLLoader } from 'three/examples/jsm/loaders/MTLLoader.js'
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import { RotateCw, Grid3x3, Camera, Scan, SunMoon, Play, Pause } from 'lucide-vue-next'
import { entryUrl, fileUrl } from '../api'
import { parsePMX, buildPMX } from './pmx'

const props = defineProps({ asset: { type: Object, required: true } })
const emit = defineEmits(['snapshot'])
const host = ref(null)
const status = ref('加载中…')
const note = ref('')
const info = ref(null)
const spin = ref(true)
const wire = ref(false)
const light = ref(document.documentElement.dataset.theme === 'light') // 舞台背景默认跟随主题，可手动切换
const clips = shallowRef([])
const clip = ref('')
const playing = ref(true)
let renderer, scene, camera, controls, mixer, vrm, root, raf, ro
const clock = new THREE.Clock()

const f = props.asset.meta?.file || {}
const bundle = !!f.bundle
const mainPath = bundle ? f.main : null
const ext = ((bundle ? f.main : props.asset.original_name) || '').split('.').pop().toLowerCase()
const url = bundle ? entryUrl(props.asset.id, mainPath) : fileUrl(props.asset.id)
const baseDir = bundle ? (f.main.includes('/') ? f.main.slice(0, f.main.lastIndexOf('/') + 1) : '') : ''
const rel = (p) => entryUrl(props.asset.id, normalize(baseDir + p.replace(/\\/g, '/')))
function normalize(p) { const out = []; for (const s of p.split('/')) { if (s === '..') out.pop(); else if (s && s !== '.') out.push(s) } return out.join('/') }

function setup() {
  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, alpha: true })
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  host.value.appendChild(renderer.domElement)
  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(35, 1, 0.01, 5000)
  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.autoRotate = spin.value
  controls.autoRotateSpeed = 1.2
  controls.addEventListener('start', () => { spin.value = false; controls.autoRotate = false })
  scene.add(new THREE.HemisphereLight(0xeef0ff, 0x302a40, 1.6))
  const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(3, 5, 4); scene.add(key)
  const rim = new THREE.DirectionalLight(0xb48ce6, 1.2); rim.position.set(-4, 2, -3); scene.add(rim)
  ro = new ResizeObserver(resize); ro.observe(host.value); resize()
  loop()
}
function resize() {
  const w = host.value.clientWidth, h = host.value.clientHeight
  renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix()
}
function loop() {
  raf = requestAnimationFrame(loop)
  const dt = clock.getDelta()
  if (mixer && playing.value) mixer.update(dt)
  vrm?.update(dt)
  controls.update()
  renderer.render(scene, camera)
}

function frame(obj) {
  const box = new THREE.Box3().setFromObject(obj)
  const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3())
  const r = Math.max(size.x, size.y, size.z) || 1
  obj.position.sub(new THREE.Vector3(center.x, box.min.y, center.z)) // 放到地面中心
  const grid = new THREE.GridHelper(r * 3, 24, 0x9a6ad0, 0x3a3a55); grid.material.transparent = true; grid.material.opacity = 0.35
  grid.name = 'grid'; scene.add(grid)
  camera.near = r / 200; camera.far = r * 200; camera.updateProjectionMatrix()
  controls.target.set(0, size.y * 0.5, 0)
  camera.position.set(r * 1.5, size.y * 0.7 + r * 0.3, r * 1.95)
  controls.saveState()
  let tris = 0
  obj.traverse((o) => { if (o.isMesh) { const g = o.geometry; tris += (g.index ? g.index.count : g.attributes.position.count) / 3 } })
  info.value = { tris: Math.round(tris), size: `${size.x.toFixed(2)} × ${size.y.toFixed(2)} × ${size.z.toFixed(2)}` }
}

async function load() {
  const manager = new THREE.LoadingManager()
  let obj
  if (['glb', 'gltf', 'vrm'].includes(ext)) {
    const loader = new GLTFLoader(manager)
    loader.register((p) => new VRMLoaderPlugin(p))
    let gltf
    try { gltf = await loader.loadAsync(url) } catch (e) {
      if (!/humanoid|VRM/i.test(String(e?.message))) throw e
      gltf = await new GLTFLoader(manager).loadAsync(url) // 人形骨骼不完整：按普通 glTF 显示
      note.value = 'VRM 人形骨骼不完整，按普通 glTF 模型显示'
    }
    vrm = gltf.userData.vrm || null
    if (vrm) { VRMUtils.removeUnnecessaryVertices(gltf.scene); VRMUtils.rotateVRM0(vrm) }
    obj = vrm ? vrm.scene : gltf.scene
    clips.value = gltf.animations
  } else if (ext === 'obj') {
    const loader = new OBJLoader(manager)
    const mtl = bundle && f.mtllib?.[0]
    if (mtl) {
      try { const mats = await new MTLLoader(manager).setResourcePath(rel('')).loadAsync(rel(mtl)); mats.preload(); loader.setMaterials(mats) } catch { /* 没有材质就用白模 */ }
    }
    obj = await loader.loadAsync(url)
    if (!mtl) obj.traverse((o) => { if (o.isMesh) o.material = new THREE.MeshStandardMaterial({ color: 0xd8d6e8, roughness: 0.6 }) })
  } else if (ext === 'fbx') {
    obj = await new FBXLoader(manager).loadAsync(url)
    clips.value = obj.animations || []
  } else if (ext === 'pmx') {
    const buf = await (await fetch(url)).arrayBuffer()
    obj = buildPMX(parsePMX(buf), rel)
  } else {
    throw new Error('这个格式不能在浏览器里预览')
  }
  root = obj
  scene.add(obj)
  frame(obj)
  if (clips.value.length) { mixer = new THREE.AnimationMixer(obj); clip.value = clips.value[0].name; playClip() }
  status.value = ''
}
function playClip() {
  if (!mixer) return
  mixer.stopAllAction()
  const c = clips.value.find((x) => x.name === clip.value)
  if (c) mixer.clipAction(c).play()
}
function toggleSpin() { spin.value = !spin.value; controls.autoRotate = spin.value }
function toggleWire() { wire.value = !wire.value; root?.traverse((o) => { if (o.isMesh) [].concat(o.material).forEach((m) => { m.wireframe = wire.value }) }) }
function toggleBg() { light.value = !light.value }
function reset() { controls.reset() }
function snapshot() {
  const g = scene.getObjectByName('grid'); if (g) g.visible = false
  renderer.render(scene, camera)
  renderer.domElement.toBlob((b) => { if (g) g.visible = true; emit('snapshot', b) }, 'image/png')
}

onMounted(async () => {
  setup()
  try { await load() } catch (e) { status.value = `无法预览：${e.message || e}` }
})
onBeforeUnmount(() => {
  cancelAnimationFrame(raf); ro?.disconnect(); controls?.dispose()
  scene?.traverse((o) => { o.geometry?.dispose?.(); [].concat(o.material || []).forEach((m) => { m.map?.dispose?.(); m.dispose?.() }) })
  renderer?.dispose(); renderer?.domElement.remove()
})
</script>

<template>
  <div class="mv" :class="{ light }">
    <div ref="host" class="mv-canvas" />
    <div v-if="status" class="mv-status">{{ status }}</div>
    <div class="mv-bar">
      <button class="ghost iconbtn" :class="{ on: spin }" title="自动旋转" @click="toggleSpin"><RotateCw :size="15" /></button>
      <button class="ghost iconbtn" :class="{ on: wire }" title="线框" @click="toggleWire"><Grid3x3 :size="15" /></button>
      <button class="ghost iconbtn" title="切换背景" @click="toggleBg"><SunMoon :size="15" /></button>
      <button class="ghost iconbtn" title="重置视角" @click="reset"><Scan :size="15" /></button>
      <template v-if="clips.length">
        <span class="sep" />
        <button class="ghost iconbtn" :title="playing ? '暂停动画' : '播放动画'" @click="playing = !playing"><component :is="playing ? Pause : Play" :size="15" /></button>
        <select v-model="clip" class="mv-clip" @change="playClip"><option v-for="c in clips" :key="c.name" :value="c.name">{{ c.name || '动画' }}</option></select>
      </template>
      <span class="sep" />
      <button class="ghost small" title="把当前画面设为素材封面" @click="snapshot"><Camera :size="14" />设为封面</button>
    </div>
    <div v-if="note" class="mv-note small">{{ note }}</div>
    <div v-if="info" class="mv-info mono">{{ info.tris.toLocaleString() }} 三角面 · {{ info.size }}</div>
  </div>
</template>

<style scoped>
.mv { position: relative; height: 460px; border-radius: var(--radius); overflow: hidden; border: 1px solid var(--line);
  background: radial-gradient(90% 80% at 50% 30%, #2b2846, #15151f 70%); }
.mv.light { background: radial-gradient(90% 80% at 50% 30%, #ffffff, #e4e2ee 75%); }
.mv-canvas, .mv-canvas :deep(canvas) { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.mv-status { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); font-size: 13px; padding: 20px; text-align: center; }
.mv-bar { position: absolute; left: 50%; bottom: 12px; transform: translateX(-50%); display: flex; align-items: center; gap: 2px; padding: 4px; border-radius: 999px;
  background: var(--chrome); backdrop-filter: blur(12px); border: 1px solid var(--line); }
.mv-bar .on { color: var(--accent-hi); background: var(--accent-soft); }
.mv-bar .sep { width: 1px; height: 18px; background: var(--line); margin: 0 4px; }
.mv-clip { width: auto; padding: 3px 8px; font-size: 12px; border-radius: 999px; }
.mv-note { position: absolute; top: 10px; left: 12px; font-size: 11.5px; color: var(--warn); background: var(--chrome); padding: 3px 10px; border-radius: 999px; }
.mv-info { position: absolute; top: 10px; right: 12px; font-size: 11px; color: var(--faint); background: var(--chrome); padding: 3px 8px; border-radius: 999px; }
</style>
