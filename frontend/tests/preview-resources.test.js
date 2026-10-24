import { test } from 'node:test'
import assert from 'node:assert/strict'
import * as THREE from 'three'
import { disposeTree, previewLifetime } from '../src/viewers/resources.js'

test('shared geometry, all texture maps, skeletons and shader uniforms are released', () => {
  const texture = new THREE.Texture()
  const normal = new THREE.Texture()
  const material = new THREE.MeshStandardMaterial({ map: texture, normalMap: normal })
  const shader = new THREE.ShaderMaterial({ uniforms: { maps: { value: [texture, normal] } } })
  const geometry = new THREE.BoxGeometry()
  const skeleton = new THREE.Skeleton([])
  const counts = new Map()
  for (const item of [texture, normal, material, shader, geometry, skeleton]) {
    const dispose = item.dispose.bind(item)
    item.dispose = () => { counts.set(item, (counts.get(item) || 0) + 1); dispose() }
  }
  const group = new THREE.Group()
  const a = new THREE.SkinnedMesh(geometry, material); a.skeleton = skeleton
  group.add(a, new THREE.Mesh(geometry, material), new THREE.Mesh(geometry, shader))
  disposeTree(group)
  for (const item of [texture, normal, material, shader, geometry, skeleton]) assert.equal(counts.get(item), 1)
})

test('a late loader result is disposed instead of attached after unmount', async () => {
  const lifetime = previewLifetime()
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial())
  let disposed = false
  mesh.geometry.addEventListener('dispose', () => { disposed = true })
  const result = Promise.resolve(mesh)
  lifetime.close()
  assert.equal(lifetime.accept(await result), false)
  assert.equal(disposed, true)
  assert.equal(lifetime.closed, true)
})

test('late GLTF decoded bitmaps shared by texture sources close exactly once', () => {
  let closes = 0
  const bitmap = { close() { closes++ } }
  const a = new THREE.Texture(bitmap), b = new THREE.Texture(bitmap)
  const root = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshStandardMaterial({ map: a, normalMap: b }))
  const lifetime = previewLifetime(); lifetime.close()
  assert.equal(lifetime.accept(root), false)
  assert.equal(closes, 1)
})
