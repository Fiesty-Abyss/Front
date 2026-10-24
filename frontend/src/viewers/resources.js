// Dispose an owned preview tree, including non-diffuse maps and shared resources once.
export function disposeTree(root) {
  const seen = new Set()
  const bitmaps = new Set()
  const closeBitmap = (image) => {
    if (!image || bitmaps.has(image)) return
    bitmaps.add(image)
    if (Array.isArray(image)) image.forEach(closeBitmap)
    else image.close?.() // GLTF ImageBitmapLoader: texture.dispose() does not close decoded pixels.
  }
  const release = (value) => {
    if (!value || seen.has(value)) return
    seen.add(value)
    if (value.isTexture) { closeBitmap(value.image); closeBitmap(value.source?.data) }
    value.dispose?.()
  }
  root?.traverse((node) => {
    release(node.geometry)
    release(node.skeleton)
    for (const material of [].concat(node.material || [])) {
      if (seen.has(material)) continue
      for (const value of Object.values(material)) if (value?.isTexture) release(value)
      for (const uniform of Object.values(material.uniforms || {})) {
        for (const value of [].concat(uniform.value || [])) if (value?.isTexture) release(value)
      }
      release(material)
    }
  })
}

// Async loaders can finish after unmount, including loaders without abort support.
export function previewLifetime() {
  let closed = false
  return {
    get closed() { return closed },
    close() { closed = true },
    accept(root) { if (closed) { disposeTree(root); return false }; return true },
  }
}
