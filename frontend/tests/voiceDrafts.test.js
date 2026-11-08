import test from 'node:test'
import assert from 'node:assert/strict'
import {draftFromSegment,emptyVoiceDraft,draftChanged,exportContext} from '../src/voiceDrafts.js'

test('refresh comparison covers every editable field including Unicode and review',()=>{
  const saved=draftFromSegment({text:'你好😀\n下一行',speaker:'甲',profile_id:4,recipe:{language:'zh',speed:1},source:{speaker_confirmed:true}})
  assert.equal(draftChanged({...saved},saved),false)
  for (const [field,value] of Object.entries({text:'尚未保存',speaker:'乙',profile_id:5,language:'en',speed:1.2,confirm_speaker:false}))
    assert.equal(draftChanged({...saved,[field]:value},saved),true,field)
  const changed={...saved,text:'未保存的原文'}
  // Reading a newer server row does not mutate or replace the detached draft.
  draftFromSegment({text:'其他窗口的内容',speaker:'甲',profile_id:4,recipe:{},source:{}})
  assert.equal(changed.text,'未保存的原文')
})
test('empty new forms are clean, cleared profile IDs normalize, invalid edits remain dirty',()=>{
  const blank=emptyVoiceDraft()
  assert.equal(draftChanged(null,blank),false)
  assert.equal(draftChanged({...blank},blank),false)
  assert.equal(draftChanged({...blank,profile_id:''},blank),false)
  assert.equal(draftChanged({...blank,text:'新台词'},blank),true)
  assert.equal(draftChanged({...blank,speed:''},blank),true)
})
test('export context ignores refreshed object identity but tracks real scope and order changes',()=>{
  const p={uid:'a',version:2},items=[{uid:'one'},{uid:'two'}]
  assert.equal(exportContext({...p},items.map(x=>({...x}))),exportContext(p,items))
  assert.notEqual(exportContext({...p,version:3},items),exportContext(p,items))
  assert.notEqual(exportContext({uid:'b',version:2},items),exportContext(p,items))
  assert.notEqual(exportContext(p,[...items].reverse()),exportContext(p,items))
})
