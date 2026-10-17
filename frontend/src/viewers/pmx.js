// 极简 PMX 2.0 / 2.1 读取器：只取静态网格（顶点、法线、UV、面、材质与贴图），不处理骨骼动画与表情。
// 按公开的 PMX 格式说明从头实现；three.js 新版本已移除 MMDLoader。
import * as THREE from 'three'

class R {
  constructor(buf) { this.v = new DataView(buf); this.o = 0; this.u8 = new Uint8Array(buf) }
  i8() { return this.v.getInt8(this.o++) }
  u8_() { return this.v.getUint8(this.o++) }
  i16() { const x = this.v.getInt16(this.o, true); this.o += 2; return x }
  u16() { const x = this.v.getUint16(this.o, true); this.o += 2; return x }
  i32() { const x = this.v.getInt32(this.o, true); this.o += 4; return x }
  f32() { const x = this.v.getFloat32(this.o, true); this.o += 4; return x }
  skip(n) { this.o += n }
  idx(size, unsigned) {
    if (size === 1) return unsigned ? this.u8_() : this.i8()
    if (size === 2) return unsigned ? this.u16() : this.i16()
    return this.i32()
  }
}

export function parsePMX(buffer) {
  const r = new R(buffer)
  const magic = String.fromCharCode(...r.u8.slice(0, 4)); r.skip(4)
  if (magic !== 'PMX ') throw new Error('不是 PMX 文件')
  const version = r.f32()
  const g = []; const n = r.u8_(); for (let i = 0; i < n; i++) g.push(r.u8_())
  const [encoding, addUV, vsz, tsz, , bsz] = g
  const dec = new TextDecoder(encoding === 0 ? 'utf-16le' : 'utf-8')
  const text = () => { const len = r.i32(); const s = dec.decode(r.u8.subarray(r.o, r.o + len)); r.skip(len); return s }
  const name = text(); text(); const comment = text(); text()

  const nv = r.i32()
  const pos = new Float32Array(nv * 3), nrm = new Float32Array(nv * 3), uv = new Float32Array(nv * 2)
  for (let i = 0; i < nv; i++) {
    pos[i * 3] = r.f32(); pos[i * 3 + 1] = r.f32(); pos[i * 3 + 2] = -r.f32() // MMD 是左手坐标系
    nrm[i * 3] = r.f32(); nrm[i * 3 + 1] = r.f32(); nrm[i * 3 + 2] = -r.f32()
    uv[i * 2] = r.f32(); uv[i * 2 + 1] = 1 - r.f32()
    r.skip(16 * addUV)
    const w = r.u8_()
    r.skip({ 0: bsz, 1: bsz * 2 + 4, 2: bsz * 4 + 16, 3: bsz * 2 + 4 + 36, 4: bsz * 4 + 16 }[w])
    r.skip(4)
  }
  const ni = r.i32()
  const index = new Uint32Array(ni)
  for (let i = 0; i < ni; i += 3) { // 翻转 z 之后需要反转绕序
    index[i] = r.idx(vsz, vsz < 4); index[i + 2] = r.idx(vsz, vsz < 4); index[i + 1] = r.idx(vsz, vsz < 4)
  }
  const textures = []; const nt = r.i32(); for (let i = 0; i < nt; i++) textures.push(text().replace(/\\/g, '/'))
  const materials = []; const nm = r.i32()
  for (let i = 0; i < nm; i++) {
    const mname = text(); text()
    const diffuse = [r.f32(), r.f32(), r.f32(), r.f32()]
    r.skip(12 + 4 + 12)
    const flags = r.u8_()
    r.skip(16 + 4)
    const tex = r.idx(tsz, false); r.idx(tsz, false); r.skip(1)
    const shared = r.u8_(); if (shared) r.skip(1); else r.idx(tsz, false)
    text()
    const count = r.i32()
    materials.push({ name: mname, diffuse, doubleSided: !!(flags & 1), texture: tex >= 0 ? textures[tex] : null, count })
  }
  return { version, name, comment, pos, nrm, uv, index, textures, materials }
}

/** 生成 three.js 网格；resolve(相对路径) 返回贴图 URL。 */
export function buildPMX(data, resolve) {
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(data.pos, 3))
  geo.setAttribute('normal', new THREE.BufferAttribute(data.nrm, 3))
  geo.setAttribute('uv', new THREE.BufferAttribute(data.uv, 2))
  geo.setIndex(new THREE.BufferAttribute(data.index, 1))
  const loader = new THREE.TextureLoader()
  const cache = {}
  let start = 0
  const mats = data.materials.map((m, i) => {
    geo.addGroup(start, m.count, i); start += m.count
    const mat = new THREE.MeshToonMaterial({ color: new THREE.Color(m.diffuse[0], m.diffuse[1], m.diffuse[2]), transparent: m.diffuse[3] < 1, opacity: m.diffuse[3], side: m.doubleSided ? THREE.DoubleSide : THREE.FrontSide })
    if (m.texture && !/\.(tga|dds)$/i.test(m.texture)) {
      const t = cache[m.texture] ||= loader.load(resolve(m.texture))
      t.colorSpace = THREE.SRGBColorSpace
      mat.map = t; mat.color.set(0xffffff); mat.transparent = true; mat.alphaTest = 0.05
    }
    return mat
  })
  return new THREE.Mesh(geo, mats)
}
