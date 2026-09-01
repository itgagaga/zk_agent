import test from 'node:test'
import assert from 'node:assert/strict'
import { getPersonalScopeStatus, mergeRetrievalMeta } from './retrievalSummary.js'

test('personal retrieval status maps to a user-visible badge', () => {
  assert.deepEqual(
    getPersonalScopeStatus({
      knowledge_scope: 'with_personal',
      personal_documents_status: 'retrieved',
      personal_documents_used: true,
    }),
    { tone: 'success', symbol: '✓', label: '已使用个人资料' }
  )
  assert.deepEqual(
    getPersonalScopeStatus({
      knowledge_scope: 'with_personal',
      personal_documents_status: 'failed',
      personal_documents_used: false,
    }),
    { tone: 'warning', symbol: '!', label: '个人资料检索失败' }
  )
  assert.equal(getPersonalScopeStatus({ knowledge_scope: 'auto' }), null)
})

test('keeps source and attachment metadata when retrieval summary arrives', () => {
  const result = mergeRetrievalMeta(
    { sources: [{ title: '缓考申请表', url: '/file.pdf' }], attachments: [] },
    { retrieval_summary: { retrievers: ['download_search', 'campus_rag'], coverage: 1 } },
  )
  assert.equal(result.sources.length, 1)
  assert.equal(result.retrieval_summary.coverage, 1)
})
