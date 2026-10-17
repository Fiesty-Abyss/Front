async function request(method, url, body, isForm = false) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    if (isForm) opts.body = body
    else { opts.body = JSON.stringify(body); opts.headers['Content-Type'] = 'application/json' }
  }
  const res = await fetch(url, opts)
  if (res.status === 204) return null
  const data = res.headers.get('content-type')?.includes('json') ? await res.json() : await res.text()
  if (!res.ok) {
    const d = data?.detail
    const msg = typeof d === 'string' ? d : d?.message ?? (Array.isArray(d) ? d.map((x) => x.msg).join('; ') : res.statusText)
    throw Object.assign(new Error(msg), { status: res.status, data })
  }
  return data
}

function qs(params = {}) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x))
    else sp.append(k, v)
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const api = {
  get: (url, params) => request('GET', url + qs(params)),
  post: (url, body) => request('POST', url, body),
  patch: (url, body) => request('PATCH', url, body),
  del: (url) => request('DELETE', url),
  upload: (url, form) => request('POST', url, form, true),
}

export function resource(base) {
  return {
    list: (params) => api.get(base, params),
    get: (id) => api.get(`${base}/${id}`),
    create: (body) => api.post(base, body),
    update: (id, body) => api.patch(`${base}/${id}`, body),
    remove: (id) => api.del(`${base}/${id}`),
  }
}

export const Tags = resource('/api/tags')
export const Assets = resource('/api/assets')
export const Characters = resource('/api/characters')
export const Worlds = resource('/api/worlds')
export const Works = resource('/api/works')
export const Relations = resource('/api/relations')
export const Prompts = resource('/api/prompts')
export const SDModels = resource('/api/sd-models')
export const Generations = resource('/api/generations')
export const Cards = resource('/api/cards')
export const Collections = resource('/api/collections')

export const thumb = (id) => `/api/assets/${id}/thumb`
export const fileUrl = (id) => `/api/assets/${id}/file`

export const LABELS = {
  assetKind: { drawing: '我的画', ai_image: 'AI 生成', material: '绘画素材', novel: '小说', cg: 'CG', reference: '参考', other: '其他' },
  gender: { male: '男', female: '女', other: '其他', unknown: '未知' },
  workKind: { anime: '动漫', game: '游戏', galgame: 'Galgame', novel: '小说', manga: '漫画', original: '原创', other: '其他' },
  modelKind: { checkpoint: 'Checkpoint', lora: 'LoRA', lycoris: 'LyCORIS', vae: 'VAE', embedding: 'Embedding', controlnet: 'ControlNet', upscaler: '放大', other: '其他' },
  tagCategory: { gender: '性别', medium: '媒介', source: '来源作品', style: '画风', type: '类型', custom: '自定义' },
}
