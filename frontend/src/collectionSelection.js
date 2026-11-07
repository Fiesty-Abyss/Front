// Explicit IDs only: page changes never reinterpret a selection as "all".
export const selectionLimit = 1000
export function toggleSelection(selected, id) {
  if (selected.includes(id)) return selected.filter((value) => value !== id)
  if (selected.length >= selectionLimit) throw new Error('一次最多选择 1000 项，请分批处理')
  return [...selected, id]
}
export function reorderPage(items, from, to) {
  if (from < 0 || to < 0 || from >= items.length || to >= items.length) return [...items]
  const result = [...items]
  result.splice(to, 0, ...result.splice(from, 1))
  return result
}
