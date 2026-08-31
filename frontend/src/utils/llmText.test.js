import test from 'node:test'
import assert from 'node:assert/strict'
import { extractTextContent } from './llmText.js'

test('extractTextContent normalizes strings and structured content blocks', () => {
  assert.equal(extractTextContent('普通文本'), '普通文本')
  assert.equal(
    extractTextContent([
      { type: 'text', text: '第一段' },
      { content: '第二段' },
    ]),
    '第一段第二段',
  )
})

test('extractTextContent returns empty text for nullish content', () => {
  assert.equal(extractTextContent(null), '')
  assert.equal(extractTextContent(undefined), '')
})
