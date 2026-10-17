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
  put: (url, body) => request('PUT', url, body),
  del: (url) => request('DELETE', url),
  upload: (url, form, method = 'POST') => request(method, url, form, true),
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
export const WorldEntries = resource('/api/world-entries')
export const Appearances = resource('/api/appearances')
export const Snippets = resource('/api/prompt-snippets')

export const thumb = (id, v) => `/api/assets/${id}/thumb${v ? `?v=${encodeURIComponent(v)}` : ''}`
export const fileUrl = (id, inline) => `/api/assets/${id}/file${inline ? '?inline=1' : ''}`
export const entryUrl = (id, path) => `/api/assets/${id}/entry/${path.split('/').map(encodeURIComponent).join('/')}`
export const FILE_KINDS = ['model3d', 'live2d', 'audio', 'video', 'pdf', 'document', 'archive', 'code']
// 有可显示的缩略图：图片本身，或识别文件时提取 / 截下的封面
export const hasThumb = (a) => !!(a?.width || a?.meta?.file?.thumb)
export const Notes = resource('/api/notes')
export const Diagrams = resource('/api/diagrams')
export const Galgames = resource('/api/galgames')

export const LABELS = {
  assetKind: { drawing: '我的画', ai_image: 'AI 生成', material: '绘画素材', novel: '小说', cg: 'CG', reference: '参考', model3d: '3D 模型', live2d: 'Live2D', audio: '音频', video: '视频', pdf: 'PDF', document: '文档', archive: '压缩包', code: '代码 / 脚本', other: '其他' },
  activity: { assets: '素材', characters: '角色', world_entries: '百科条目', prompts: '提示词', generations: '出图', chat: '对话', cards: '角色卡', lore: '世界书', notes: '笔记', diagrams: '图表', galgames: '游戏库' },
  gender: { male: '男', female: '女', other: '其他', unknown: '未知' },
  workKind: { anime: '动漫', game: '游戏', galgame: 'Galgame', novel: '小说', manga: '漫画', original: '原创', other: '其他' },
  modelKind: { checkpoint: 'Checkpoint', lora: 'LoRA', lycoris: 'LyCORIS', vae: 'VAE', embedding: 'Embedding', controlnet: 'ControlNet', upscaler: '放大', hypernetwork: 'Hypernetwork', text_encoder: '文本编码器', other: '其他' },
  snippetCategory: { quality: '质量', style: '画风', character: '角色', clothing: '服装', pose: '动作', composition: '构图', background: '背景', lighting: '光影', negative: '负面', other: '其他' },
  param: { model: '模型', sampler: '采样器', scheduler: '调度器', steps: '步数', cfg: 'CFG', seed: '种子', size: '尺寸', clip_skip: 'Clip skip', denoise: '重绘幅度', vae: 'VAE', loras: 'LoRA', prompt_sr: '提示词替换', lora_weight: 'LoRA 权重' },
  entryKind: { location: '地点', organization: '组织', event: '事件', item: '物品', concept: '概念' },
  tagCategory: { gender: '性别', medium: '媒介', source: '来源作品', style: '画风', type: '类型', custom: '自定义' },
}

/** 轮询后台任务直到结束；onUpdate 每次拿到最新状态。 */
export async function waitJob(id, onUpdate, interval = 800) {
  for (;;) {
    const j = await api.get(`/api/jobs/${id}`)
    onUpdate?.(j)
    if (!['queued', 'running'].includes(j.status)) return j
    await new Promise((r) => setTimeout(r, interval))
  }
}

/** 与后端 compose_prompt 相同的规则：逗号分隔、去重（不区分大小写），权重 ≠ 1 时整段包成 (片段:权重)。 */
export function composePrompt(base, parts) {
  const seen = new Set()
  const out = []
  const push = (chunk) => {
    if (!chunk) return
    if (chunk.startsWith('(') && chunk.endsWith(')')) { if (!seen.has(chunk.toLowerCase())) { seen.add(chunk.toLowerCase()); out.push(chunk) } return }
    for (const t of chunk.split(/[,\n]/).map((x) => x.trim()).filter(Boolean)) if (!seen.has(t.toLowerCase())) { seen.add(t.toLowerCase()); out.push(t) }
  }
  push(base)
  for (const [text, w] of parts) {
    const t = (text || '').trim().replace(/^,+|,+$/g, '').trim()
    push(t && Math.abs((w ?? 1) - 1) > 1e-6 ? `(${t}:${+(+w).toFixed(2)})` : t)
  }
  return out.join(', ')
}

export const Lorebooks = resource('/api/lorebooks')

/** POST 并按 Server-Sent Events 解析流式响应：onEvent(event, data)。 */
export async function streamPost(url, body, onEvent, signal) {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })
  if (!res.ok) {
    const data = res.headers.get('content-type')?.includes('json') ? await res.json() : { detail: await res.text() }
    throw Object.assign(new Error(typeof data.detail === 'string' ? data.detail : res.statusText), { status: res.status, data })
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i)
      buf = buf.slice(i + 2)
      let event = 'message'
      const data = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).trim())
      }
      if (data.length) onEvent(event, JSON.parse(data.join('\n')))
    }
  }
}

