// galgame 游戏库共用的标签、颜色与小工具
export const STATUS = {
  wishlist: { label: '想玩', color: '#8b93ff' },
  playing: { label: '在玩', color: '#23d2e2' },
  finished: { label: '玩过', color: '#5fd38d' },
  shelved: { label: '搁置', color: '#f2c26b' },
  dropped: { label: '弃坑', color: '#f9515c' },
}
export const SOURCES = {
  bangumi: { label: 'Bangumi', short: 'BGM', color: '#f09199' },
  vndb: { label: 'VNDB', short: 'VNDB', color: '#5b8fd8' },
  ymgal: { label: '月幕 Galgame', short: '月幕', color: '#b48ce6' },
}
export const SORTS = { updated: '最近更新', added: '最近添加', title: '标题', release: '发售日期', rating: '我的评分', playtime: '游玩时长' }

export const coverUrl = (g) => (g?.has_cover ? `/api/galgames/${g.id}/cover?v=${encodeURIComponent(g.updated_at)}` : null)

export function fmtMinutes(min) {
  if (!min) return '—'
  const h = Math.floor(min / 60)
  const m = min % 60
  return h ? (m ? `${h} 小时 ${m} 分` : `${h} 小时`) : `${m} 分钟`
}

// 没有封面时用标题生成一个稳定的渐变色
export function tint(title = '') {
  let h = 0
  for (const ch of title) h = (h * 31 + ch.codePointAt(0)) % 360
  return `linear-gradient(160deg, hsl(${h} 45% 42%), hsl(${(h + 50) % 360} 40% 18%))`
}

export const year = (d) => (d ? d.slice(0, 4) : '')
