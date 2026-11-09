import test from 'node:test'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {parse,compileScript} from '@vue/compiler-sfc'
import {h} from 'vue'
import {renderToString} from '@vue/server-renderer'
import {bookRecordKind,editionLabels,metadataSearchBody} from '../src/metadataDisplay.js'

test('Open Library work and edition identities stay distinct and fail closed',()=>{
  assert.equal(bookRecordKind({provider:'openlibrary',sid:'OL1M',record_type:'edition'}),'具体版次')
  assert.equal(bookRecordKind({source:'openlibrary',sid:'OL1W'}),'作品条目（非具体版次）')
  assert.match(bookRecordKind({provider:'openlibrary',sid:'OL1M'}),/未确认/)
  assert.equal(bookRecordKind({provider:'vndb',sid:'OL1M',record_type:'edition'}),null)
  assert.equal(bookRecordKind({provider:'openlibrary',kind:'model',sid:'OL1M',record_type:'edition'}),null)
  assert.equal(bookRecordKind(null),null)
  for(const key of ['record_type','isbn_10','isbn_13','languages','work_ids','edition_name','publish_date'])assert.ok(editionLabels[key])
})
test('year is optional and strictly bounded; hidden book filters never leak into model queries',()=>{
  const base={kind:'book',title:'ISBN: 9780140328721',author:'',year:'',providers:['openlibrary']}
  assert.equal(metadataSearchBody(base).year,null)
  assert.equal(metadataSearchBody({...base,year:'1988'}).year,1988)
  for(const year of ['bad','0','10000','1988.5'])assert.throws(()=>metadataSearchBody({...base,year}),/年份/)
  const model=metadataSearchBody({...base,kind:'model',title:'a'.repeat(64),author:'previous book author',year:'bad',providers:['civitai']})
  assert.equal(model.author,null);assert.equal(model.year,null)
  assert.deepEqual(base.providers,['openlibrary'])
})
const source=await readFile(new URL('../src/components/BookRecordSummary.vue',import.meta.url),'utf8')
const {descriptor}=parse(source)
let code=compileScript(descriptor,{id:'edition-test',inlineTemplate:true}).content
code=code.replace(/from (['"])vue\1/g,`from '${import.meta.resolve('vue')}'`)
code=code.replace("from '../metadataDisplay'",`from '${new URL('../src/metadataDisplay.js',import.meta.url).href}'`)
const Summary=(await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)).default
test('summary displays exact source edition fields without a selected target or external image request',async()=>{
  const html=await renderToString(h(Summary,{item:{provider:'openlibrary',kind:'book',sid:'OL42M',record_type:'edition',isbn_13:['9780140328721'],languages:['eng'],work_ids:['OL99W'],edition_name:'Generated edition',publish_date:'1988',covers:['https://example.invalid/private-cover']}}))
  for(const value of ['图书版次核对','具体版次','OL42M','9780140328721','eng','OL99W','Generated edition','来源未提供'])assert.ok(html.includes(value))
  assert.doesNotMatch(html,/<img|private-cover|src=/)
})
test('untrusted source strings render as text, with no inferred translator or author',async()=>{
  const html=await renderToString(h(Summary,{item:{provider:'openlibrary',sid:'OL3M',record_type:'edition',edition_name:'<img src=x onerror=alert(1)>',authors:[]}}))
  assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img/)
  assert.match(html,/作者姓名/);assert.match(html,/来源未提供/)
  const absent=await renderToString(h(Summary,{item:{provider:'civitai',sid:'123'}}))
  assert.equal(absent.replace(/<!--[\s\S]*?-->/g,'').trim(),'')
})
