import {test} from 'node:test'
import assert from 'node:assert/strict'
import {noteAncestry, visibleNotes} from '../src/noteAncestry.js'

test('normal crumbs root-to-parent and missing pages', () => {
  const rows=[{id:1,parent_id:null},{id:2,parent_id:1},{id:3,parent_id:2}]
  assert.deepEqual(noteAncestry(rows,3).parents.map(n=>n.id),[1,2])
  assert.equal(noteAncestry(rows,3).issue,'')
  assert.equal(noteAncestry(rows,1).parents.length,0)
  assert.deepEqual(noteAncestry(rows,999),{parents:[],issue:''})
  assert.equal(noteAncestry([{id:1,parent_id:99}],1).issue,'missing_parent')
})
test('legacy self and multi-node cycles terminate without duplicate crumbs', () => {
  assert.deepEqual(noteAncestry([{id:1,parent_id:1}],1),{parents:[],issue:'cycle'})
  const result=noteAncestry([{id:1,parent_id:2},{id:2,parent_id:3},{id:3,parent_id:2}],1)
  assert.equal(result.issue,'cycle')
  assert.deepEqual(result.parents.map(n=>n.id),[3,2])
})
test('deep valid ancestry uses an iterative traversal', () => {
  const rows=Array.from({length:10000},(_,i)=>({id:i+1,parent_id:i||null}))
  const result=noteAncestry(rows,10000)
  assert.equal(result.parents.length,9999)
  assert.equal(result.issue,'')
  assert.equal(result.parents[0].id,1)
  assert.equal(visibleNotes(rows,new Set(rows.map(row=>row.id))).length,10000)
})
test('visible rows preserve sibling order and collapsed children', () => {
  const rows=[{id:1,parent_id:null},{id:2,parent_id:1},{id:3,parent_id:1},{id:4,parent_id:2},{id:5,parent_id:null}]
  assert.deepEqual(visibleNotes(rows,new Set()).map(n=>n.id),[1,5])
  assert.deepEqual(visibleNotes(rows,new Set([1,2])).map(n=>[n.id,n.depth]),[[1,0],[2,1],[4,2],[3,1],[5,0]])
})
