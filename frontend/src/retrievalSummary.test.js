import test from 'node:test'
import assert from 'node:assert/strict'
import { mergeRetrievalMeta } from './retrievalSummary.js'

test('keeps source and attachment metadata when retrieval summary arrives', () => {
  const result = mergeRetrievalMeta(
    { sources: [{ title: '缓考申请表', url: '/file.pdf' }], attachments: [] },
    { retrieval_summary: { retrievers: ['download_search', 'campus_rag'], coverage: 1 } },
  )
  assert.equal(result.sources.length, 1)
  assert.equal(result.retrieval_summary.coverage, 1)
})
