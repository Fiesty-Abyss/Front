export const READER_THEMES = Object.freeze({
  night: ['#14151f', '#d9d6cf', '夜间'], paper: ['#f4ecd8', '#3b3226', '羊皮纸'],
  light: ['#fafafa', '#222', '白天'], green: ['#cfe3cf', '#253325', '护眼'],
})
export const DEFAULT_READER_PREFERENCES = Object.freeze({ size: 19, line: 1.9, theme: 'night', width: 760 })
export function parseReaderPreferences(raw) {
  const prefs = { ...DEFAULT_READER_PREFERENCES }
  if (typeof raw !== 'string' || raw.length > 4096) return prefs
  let saved
  try { saved = JSON.parse(raw) } catch { return prefs }
  if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return prefs
  if (Number.isFinite(saved.size)) prefs.size = Math.round(Math.min(32, Math.max(14, saved.size)))
  if (Number.isFinite(saved.width)) prefs.width = Math.round(Math.min(1600, Math.max(320, saved.width)))
  if ([1.6, 1.8, 1.9, 2.1, 2.4].includes(saved.line)) prefs.line = saved.line
  if (typeof saved.theme === 'string' && Object.prototype.hasOwnProperty.call(READER_THEMES, saved.theme)) prefs.theme = saved.theme
  return prefs
}
