// Vue component behavior in an in-memory renderer. This is not native dialog / GUI acceptance.
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {createRequire} from 'node:module'
import {pathToFileURL} from 'node:url'
import {parse,compileScript} from '@vue/compiler-sfc'
import {createRenderer,h,nextTick,reactive} from 'vue'

const require=createRequire(import.meta.url)
const source=await readFile(new URL('../src/components/LocalPathField.vue',import.meta.url),'utf8')
const {descriptor}=parse(source)
let code=compileScript(descriptor,{id:'path-test',inlineTemplate:true}).content
code=code.replace(/from (['"])vue\1/g,`from '${pathToFileURL(require.resolve('vue/dist/vue.runtime.esm-bundler.js')).href}'`)
code=code.replace("from '../desktopPaths'",`from '${new URL('../src/desktopPaths.js',import.meta.url).href}'`)
const Field=(await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)).default
const renderer=createRenderer({
  createElement:type=>({type,children:[],props:{}}),createText:text=>({type:'text',text}),createComment:()=>({type:'comment'}),
  setText:(node,text)=>{node.text=text},setElementText:(node,text)=>{node.text=text},
  patchProp:(node,key,old,value)=>{node.props[key]=value},
  insert:(node,parent)=>{node.parent=parent;parent.children.push(node)},
  remove:node=>{node.parent.children=node.parent.children.filter(n=>n!==node)},
  parentNode:node=>node.parent,nextSibling:()=>null,
})
function fixture({desktop=true,...props}={}) {
  let finish,calls=0
  globalThis.window=desktop?{__TAURI_INTERNALS__:{invoke:()=>{calls++;return new Promise(resolve=>{finish=resolve})}}}:{}
  const state=reactive({modelValue:'old generated directory',label:'测试目录',purpose:'asset_folder',...props})
  const values=[],root={children:[]}
  const app=renderer.createApp({render:()=>h(Field,{...state,'onUpdate:modelValue':value=>values.push(value)})})
  app.mount(root)
  const find=type=>{const walk=n=>n.type===type?n:n.children?.map(walk).find(Boolean);return walk(root)}
  return {app,state,values,find,get calls(){return calls},finish:value=>finish(value)}
}
test('web input remains manual with no native invocation',()=>{
  const f=fixture({desktop:false});assert.equal(f.find('button'),undefined)
  f.find('input').props.onInput({target:{value:'manual change'}})
  assert.deepEqual(f.values,['manual change']);assert.equal(f.calls,0);f.app.unmount()
})
test('Enter belongs to the path input; native button keyboard activation cannot scan',()=>{
  let scans=0
  const f=fixture({onEnter:()=>scans++})
  f.find('input').props.onKeyup({key:'Enter'})
  assert.equal(scans,1)
  assert.equal(f.find('button').props.onKeyup,undefined)
  assert.equal(f.find('button').props.type,'button');assert.equal(f.calls,0)
  f.app.unmount()
})
test('native open is explicit, cancellation leaves input unchanged and permits retry',async()=>{
  const f=fixture();assert.equal(f.calls,0)
  const first=f.find('button').props.onClick();await new Promise(setImmediate)
  assert.equal(f.calls,1);await nextTick();assert.equal(f.find('button').props.disabled,true)
  f.finish(null);await first;await nextTick();assert.deepEqual(f.values,[])
  const second=f.find('button').props.onClick();await new Promise(setImmediate);f.finish('E:/generated/中文 & space');await second
  assert.deepEqual(f.values,['E:/generated/中文 & space']);f.app.unmount()
})
test('typing while picker is open prevents a late replacement',async()=>{
  const f=fixture();const pending=f.find('button').props.onClick();await new Promise(setImmediate)
  f.state.modelValue='new manual value';await nextTick();f.finish('E:/old pick');await pending
  assert.deepEqual(f.values,[]);f.app.unmount()
})
test('leaving the component or disabling the operation prevents late replacement',async()=>{
  for(const leave of [true,false]) {
    const f=fixture();const pending=f.find('button').props.onClick();await new Promise(setImmediate)
    if(leave)f.app.unmount();else {f.state.disabled=true;await nextTick()}
    f.finish('E:/old pick');await pending;assert.deepEqual(f.values,[]);if(!leave)f.app.unmount()
  }
})
