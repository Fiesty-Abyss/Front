export const memoryKinds = {
  core: '核心设定', episode: '情节记忆', relationship: '已确认关系', summary: '对话摘要',
  suggestion: '待审建议', fictional_state: '虚构状态', world: '世界观引用',
}
export const linkKinds = {
  character: '角色百科', card: '角色卡', oc: 'OC', chat: '聊天会话', voice_profile: '声线',
  live2d: 'Live2D 档案', asset: '素材 / 3D / VRM', lore: '世界书条目',
}
export const reviewNames = { pending: '待审核', approved: '已确认', rejected: '已拒绝' }
export const scopeNames = { character: '角色共享（跨会话）', session: '仅此会话', branch: '仅此分支及其后续' }
export function sourceLink(source) {
  const id = source?.ref?.id
  if (!Number.isInteger(id) || id < 1) return null
  if (source.kind === 'message' && Number.isInteger(source.session?.id) && source.session.id > 0) return `/chat?session=${source.session.id}`
  const bases = { character: '/characters/', card: '/cards?id=', oc: '/oc?id=', asset: '/assets?id=',
    voice_profile: '/voice', live2d: '/live2d', lore: '/lorebooks' }
  const base = bases[source.kind]
  return base ? base + (['/voice', '/live2d', '/lorebooks'].includes(base) ? '' : id) : null
}
export function sourcePayload(value, messageId, note) {
  if (value === 'manual') return { kind: 'manual', note }
  if (value === 'message') return { kind: 'message', id: Number(messageId), note }
  const [kind, id] = value.split(':')
  return { kind, id: Number(id), note }
}
