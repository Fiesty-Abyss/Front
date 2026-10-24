import test from 'node:test'
import assert from 'node:assert/strict'
import { DEFAULT_READER_PREFERENCES as defaults, parseReaderPreferences } from '../src/readerPreferences.js'

test('corrupt, oversized and non-object stored preferences preserve a readable default', () => {
  for (const raw of [null, '', '{', 'null', '[]', '7', 'x'.repeat(4097)]) {
    assert.deepEqual(parseReaderPreferences(raw), defaults)
  }
})
test('unknown themes, inherited names and invalid numeric fields cannot break rendering', () => {
  for (const theme of ['missing', '__proto__', 'constructor']) {
    assert.deepEqual(parseReaderPreferences(JSON.stringify({ theme, size: '32', line: 999, width: null })), defaults)
  }
  assert.deepEqual(parseReaderPreferences('{"size":-99,"width":99999,"line":2.1}'), { ...defaults, size:14, width:1600, line:2.1 })
})
test('valid existing preferences survive and callers never share mutable defaults', () => {
  const valid={size:23,line:2.4,theme:'green',width:900}
  assert.deepEqual(parseReaderPreferences(JSON.stringify(valid)),valid)
  const first=parseReaderPreferences(null);first.theme='paper'
  assert.deepEqual(parseReaderPreferences(null),defaults)
})
