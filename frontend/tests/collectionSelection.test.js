import test from 'node:test'
import assert from 'node:assert/strict'
import { reorderPage, toggleSelection } from '../src/collectionSelection.js'

test('selection persists explicit IDs across unrelated pages and is bounded', () => {
  let ids = toggleSelection([], 2)
  ids = toggleSelection(ids, 71)
  assert.deepEqual(ids, [2, 71])
  assert.deepEqual(toggleSelection(ids, 2), [71])
  const full = Array.from({ length: 1000 }, (_, i) => i)
  assert.throws(() => toggleSelection(full, 1001), /1000/)
  assert.equal(toggleSelection(full, 1).length, 999)
})
test('drag reorders only supplied page, does not mutate input or invent IDs', () => {
  const original = [61, 62, 63]
  assert.deepEqual(reorderPage(original, 2, 0), [63, 61, 62])
  assert.deepEqual(original, [61, 62, 63])
  assert.deepEqual(reorderPage(original, -1, 0), original)
})
