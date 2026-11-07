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
