// Bounded ancestry traversal for legacy cycles and missing-parent references.
export function noteAncestry(rows, id) {
  const byId = new Map(rows.map(row => [row.id, row]))
  const parents = [], seen = new Set([id])
  let node = byId.get(id)
  while (node?.parent_id != null) {
    if (seen.has(node.parent_id)) return { parents: parents.reverse(), issue: 'cycle' }
    const parent = byId.get(node.parent_id)
    if (!parent) return { parents: parents.reverse(), issue: 'missing_parent' }
    parents.push(parent); seen.add(parent.id); node = parent
  }
  return { parents: parents.reverse(), issue: '' }
}

export function visibleNotes(rows, open) {
  const children = new Map(), out = [], seen = new Set()
  for (const row of rows) {
    const parent = row.parent_id ?? 0
    if (!children.has(parent)) children.set(parent, [])
    children.get(parent).push(row)
  }
  const stack = (children.get(0) || []).map(row => ({row, depth:0})).reverse()
  while (stack.length) {
    const {row, depth} = stack.pop()
    if (seen.has(row.id)) continue
    seen.add(row.id)
    const kids = children.get(row.id) || []
    out.push({...row, depth, kids:kids.length})
    if (open.has(row.id)) for (let i=kids.length-1;i>=0;i--) stack.push({row:kids[i],depth:depth+1})
  }
  return out
}
