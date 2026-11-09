import {test} from 'node:test'
import assert from 'node:assert/strict'
import {hasNativePaths,pickLocalPath,pathPickerMessage} from '../src/desktopPaths.js'

test('web mode never loads IPC or requests a directory automatically',async()=>{
  assert.equal(hasNativePaths(),false)
  await assert.rejects(pickLocalPath('asset_folder'),/unsupported/)
})
test('a pick is one narrow command and returns a Unicode path without reading it',async()=>{
  const calls=[]
  const result=await pickLocalPath('project_folder',async(...args)=>{calls.push(args);return 'E:\\generated-only\\中文 & space'})
  assert.equal(result,'E:\\generated-only\\中文 & space')
  assert.deepEqual(calls,[['desktop_pick_path',{purpose:'project_folder'}]])
})
test('cancel stays null, no empty replacement and no automatic scan',async()=>{
  let calls=0
  assert.equal(await pickLocalPath('audio_folder',async()=>{calls++;return null}),null)
  assert.equal(calls,1)
  await assert.rejects(pickLocalPath('asset_folder',async()=>''),/invalid/)
})
test('unknown purpose is rejected before invoking native code',async()=>{
  let calls=0
  await assert.rejects(pickLocalPath('shell',async()=>{calls++}),/invalid/)
  assert.equal(calls,0)
})
test('errors do not leak native paths or replace input',async()=>{
  assert.match(pathPickerMessage('path_picker_busy'),/尚未关闭/)
  assert.doesNotMatch(pathPickerMessage('private native failure E:/secret'),/secret/)
  await assert.rejects(pickLocalPath('model_file',async()=>{throw new Error('denied')}),/denied/)
})
