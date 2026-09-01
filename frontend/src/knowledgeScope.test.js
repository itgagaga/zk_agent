import test from 'node:test'
import assert from 'node:assert/strict'
import {
  KNOWLEDGE_SCOPE_OPTIONS,
  KNOWLEDGE_SCOPE_STORAGE_KEY,
  isKnowledgeScope,
  persistKnowledgeScope,
  readKnowledgeScope,
} from './knowledgeScope.js'

test('scope labels are concise and explain their meaning through metadata', () => {
  assert.deepEqual(
    KNOWLEDGE_SCOPE_OPTIONS.map((option) => option.label),
    ['标准', '增强', '私有']
  )
  assert.equal(KNOWLEDGE_SCOPE_OPTIONS[1].description, '标准资料加上个人知识库')
})

function createStorage(initial = {}) {
  const values = { ...initial }
  return {
    getItem(key) { return values[key] ?? null },
    setItem(key, value) { values[key] = String(value) },
  }
}

test('scope values are limited to the three supported modes', () => {
  assert.equal(isKnowledgeScope('auto'), true)
  assert.equal(isKnowledgeScope('with_personal'), true)
  assert.equal(isKnowledgeScope('personal_only'), true)
  assert.equal(isKnowledgeScope('private'), false)
})

test('logged-out users always resolve to auto', () => {
  const storage = createStorage({ [KNOWLEDGE_SCOPE_STORAGE_KEY]: 'personal_only' })
  assert.equal(readKnowledgeScope(storage, false), 'auto')
})

test('scope persists independently from chat history and invalid values reset to auto', () => {
  const storage = createStorage()
  assert.equal(persistKnowledgeScope(storage, 'with_personal'), 'with_personal')
  assert.equal(readKnowledgeScope(storage, true), 'with_personal')
  assert.equal(persistKnowledgeScope(storage, 'not-supported'), 'auto')
  assert.equal(readKnowledgeScope(storage, true), 'auto')
})
