import test from 'node:test'
import assert from 'node:assert/strict'
import { designState, aliasExtensions } from '../src/cardDrafts.js'

test('malformed or future design JSON remains preserved and read-only',()=>{
  for(const raw of ['{','[]','null',JSON.stringify({front_design_v1:{schema:2}}),JSON.stringify({front_design_v1:{schema:1,aliases:'not-an-array'}}),JSON.stringify({front_design_v1:{schema:1,stars:6}})]){
    assert.equal(designState(raw).blocked,true)
    assert.equal(designState(raw).value.schema,1)
  }
})
test('portable design metadata accepts empty fields without inventing content',()=>{
  const value={schema:1,aliases:['Generated'],appearance:'',favorite:true,stars:0,preference:85}
  assert.deepEqual(designState(JSON.stringify({front_design_v1:value})),{value,blocked:false})
  assert.deepEqual(designState('{}'),{value:{schema:1},blocked:false})
})
test('unfinished alias text survives edits and commits without losing other extensions',()=>{
  const original={custom:{kept:true},front_design_v1:{schema:1,stars:4}}
  const next=aliasExtensions(JSON.stringify(original),'Generated、Archivist、')
  assert.deepEqual(next.front_design_v1.aliases,['Generated','Archivist'])
  assert.deepEqual(next.custom,original.custom)
  assert.deepEqual(aliasExtensions('{"front_design_v1":{"schema":2,"aliases":["kept"]}}','replacement'),{front_design_v1:{schema:2,aliases:['kept']}})
  assert.throws(()=>aliasExtensions('{','Generated'))
})
