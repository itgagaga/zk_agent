import test from 'node:test'
import assert from 'node:assert/strict'
import { downloadCategories, jobQuery } from './resourceViewModel.js'

test('download categories come only from response facets', () => {
  assert.deepEqual(
    downloadCategories({ facets: { categories: ['教学与教务', '就业与招聘'] } }),
    ['教学与教务', '就业与招聘'],
  )
  assert.deepEqual(downloadCategories({}), [])
})

test('job query keeps the typed kind and omits empty filters', () => {
  assert.deepEqual(jobQuery('posting', 'Python', '', 50), {
    kind: 'posting',
    keyword: 'Python',
    top_k: 50,
  })
})
