import test from 'node:test'
import assert from 'node:assert/strict'
import { streamPost } from '../src/api.js'

const enc=new TextEncoder()
async function withFetch(body,fn){
  const before=globalThis.fetch
  globalThis.fetch=async()=>new Response(body,{headers:{'content-type':'text/event-stream'}})
  try{return await fn()}finally{globalThis.fetch=before}
}

test('SSE parser retains UTF8 pieces and releases its reader on terminal success',async()=>{
  const bytes=enc.encode('event: start\ndata: {"token":"generated"}\n\nevent: delta\ndata: {"text":"生成"}\n\nevent: done\ndata: {}\n\n')
  const body=new ReadableStream({start(c){for(let i=0;i<bytes.length;i+=3)c.enqueue(bytes.slice(i,i+3));c.close()}})
  const events=[]
  await withFetch(body,()=>streamPost('/generated',{},(ev,d)=>events.push([ev,d])))
  assert.deepEqual(events.map(e=>e[0]),['start','delta','done'])
  assert.equal(events[1][1].text,'生成');assert.equal(body.locked,false)
})

for(const prefix of ['', 'event: start\ndata: {}\n\n', 'event: start\ndata: {}\n\nevent: delta\ndata: {"text":"partial"}\n\n']){
  test('EOF without a terminal event rejects instead of pretending success: '+prefix.length,async()=>{
    const body=new ReadableStream({start(c){c.enqueue(enc.encode(prefix));c.close()}})
    await withFetch(body,()=>assert.rejects(streamPost('/generated',{},()=>{}),/连接在结束事件前中断/))
    assert.equal(body.locked,false)
  })
}

test('abort during a response releases the reader and preserves an AbortError',async()=>{
  const abort=new AbortController();let controller
  const body=new ReadableStream({start(c){controller=c;c.enqueue(enc.encode('event: start\ndata: {}\n\n'))}})
  const before=globalThis.fetch
  globalThis.fetch=async(url,options)=>{
    options.signal.addEventListener('abort',()=>controller.error(new DOMException('generated cancel','AbortError')))
    return new Response(body)
  }
  try{await assert.rejects(streamPost('/generated',{},()=>abort.abort(),abort.signal),e=>e.name==='AbortError')}
  finally{globalThis.fetch=before}
  assert.equal(body.locked,false)
})

test('malformed event JSON cancels the response reader',async()=>{
  let cancelled=false
  const body=new ReadableStream({start(c){c.enqueue(enc.encode('event: delta\ndata: not-json\n\n'))},cancel(){cancelled=true}})
  await withFetch(body,()=>assert.rejects(streamPost('/generated',{},()=>{}),SyntaxError))
  assert.equal(cancelled,true);assert.equal(body.locked,false)
})
