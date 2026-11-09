// Real Vue component + generated API responses in memory, not browser/AI acceptance.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick } from 'vue'
import { sourceLink, sourcePayload } from '../src/soulDisplay.js'

const require = createRequire(import.meta.url)
const source = await readFile(new URL('../src/views/SoulStudio.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
let code = compileScript(descriptor, { id: 'soul-test', inlineTemplate: true }).content
code = code.replace(/from (['"])vue\1/g, `from '${pathToFileURL(require.resolve('vue/dist/vue.runtime.esm-bundler.js')).href}'`)
code = code.replace("import { onBeforeRouteLeave } from 'vue-router'", 'const onBeforeRouteLeave = fn => { globalThis.soulLeaveGuard = fn }')
code = code.replace("from '../api'", `from '${new URL('../src/api.js', import.meta.url).href}'`)
code = code.replace("from '../soulDisplay'", `from '${new URL('../src/soulDisplay.js', import.meta.url).href}'`)
const Workspace = (await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)).default
globalThis.Document = class {}
globalThis.ShadowRoot = class {}
const renderer = createRenderer({
  createElement: type => ({ type, tagName: type.toUpperCase(), value: '', children: [], props: {},
    addEventListener() {}, removeEventListener() {}, getRootNode: () => ({}),
    get options() { return this.children.filter(x => x.type === 'option') } }),
  createText: text => ({ type: 'text', text }), createComment: () => ({ type: 'comment' }),
  setText: (n, text) => { n.text = text }, setElementText: (n, text) => { n.text = text; n.children = [] },
  patchProp: (n, key, old, value) => { n.props[key] = value; if (['value', 'checked', 'multiple', 'selected'].includes(key)) { n[key] = value; if (key === 'value') n._value = value } },
  insert: (n, p, anchor) => { if (n.parent) n.parent.children = n.parent.children.filter(x => x !== n); n.parent = p; const i = p.children.indexOf(anchor); p.children.splice(i < 0 ? p.children.length : i, 0, n) },
  remove: n => { if (n.parent) n.parent.children = n.parent.children.filter(x => x !== n) },
  parentNode: n => n.parent, nextSibling: () => null,
})
const textOf = n => (n.text || '') + (n.children || []).map(textOf).join('')
const walk = n => [n, ...(n.children || []).flatMap(walk)]
async function until(fn) { for (let i = 0; i < 80; i++) { await new Promise(resolve => setImmediate(resolve)); await nextTick(); if (fn()) return } assert.fail('expected component state did not settle') }
function fixture(handler) {
  const calls = [], root = { children: [] }
  globalThis.window = { addEventListener() {}, removeEventListener() {}, confirm: () => true }
  globalThis.fetch = async (url, opts) => {
    const body = opts.body ? JSON.parse(opts.body) : undefined
    calls.push({ url, method: opts.method, body })
    const result = await handler(url, opts.method, body)
    return new Response(JSON.stringify(result.body ?? result), { status: result.status || 200, headers: { 'content-type': 'application/json' } })
  }
  const app = renderer.createApp({ render: () => h(Workspace) })
  app.component('RouterLink', { props: ['to'], render() { return h('a', { href: this.to }, this.$slots.default?.()) } })
  app.mount(root)
  return { root, app, calls, find: (type, text = '') => walk(root).find(n => n.type === type && textOf(n).includes(text)), all: type => walk(root).filter(n => n.type === type) }
}
const identity = { id: 1, uid: 'generated-stable-identity', name: '生成角色', world_ref: {}, revision: 1, active: true, notes: '', links: [] }
function standard(url) {
  if (url.startsWith('/api/worlds')) return { items: [] }
  if (url.startsWith('/api/souls/1/memories')) return { items: [], total: 0 }
  if (url === '/api/souls/1') return identity
  return { items: [identity], total: 1 }
}

test('opening a memory workspace is local and creates no inference/media engines', async () => {
  const f = fixture(standard)
  await until(() => f.find('button', '生成角色'))
  await f.find('button', '生成角色').props.onClick(); await until(() => f.find('h2', '记录记忆'))
  assert.ok(f.calls.every(x => x.url.startsWith('/api/souls') || x.url.startsWith('/api/worlds')))
  assert.equal(f.all('audio').length, 0); assert.equal(f.all('canvas').length, 0)
  assert.ok(textOf(f.root).includes('尚不自动发送给 AI'))
  f.app.unmount()
})

test('failed save keeps fictional draft and blocks silent navigation loss', async () => {
  const f = fixture((url, method) => method === 'POST' && url.endsWith('/memories') ? { status: 409, body: { detail: '生成测试：来源变化' } } : standard(url))
  await until(() => f.find('button', '生成角色')); await f.find('button', '生成角色').props.onClick()
  await until(() => f.find('h2', '记录记忆'))
  const content = f.find('label', '记忆内容').children.find(x => x.type === 'textarea')
  content.props['onUpdate:modelValue']('虚构待审草稿，不应丢失'); await nextTick()
  const submit = f.find('section', '记录记忆').children.find(x => x.type === 'form')
  await submit.props.onSubmit({ preventDefault() {} }); await nextTick()
  assert.ok(textOf(f.root).includes('生成测试：来源变化'))
  assert.equal(content.value, '虚构待审草稿，不应丢失')
  globalThis.window.confirm = () => false
  assert.equal(globalThis.soulLeaveGuard(), false)
  f.app.unmount()
})

test('late initial responses do not populate an unmounted workspace', async () => {
  let finish
  const pending = new Promise(resolve => { finish = resolve })
  const f = fixture(async url => url.startsWith('/api/worlds') ? pending : standard(url))
  await until(() => f.calls.length === 1); f.app.unmount(); finish({ items: [] })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(f.root.children.length, 0)
})

test('source navigation uses stable source IDs and never accepts an arbitrary URL', () => {
  assert.equal(sourceLink({ kind: 'message', ref: { id: 7 }, session: { id: 3 } }), '/chat?session=3')
  assert.equal(sourceLink({ kind: 'card', ref: { id: 5 } }), '/cards?id=5')
  assert.equal(sourceLink({ kind: 'https://invalid.example', ref: { id: 1 } }), null)
  assert.equal(sourceLink({ kind: 'card', ref: { id: '../bad' } }), null)
  assert.deepEqual(sourcePayload('card:5', '', '生成测试'), { kind: 'card', id: 5, note: '生成测试' })
})
