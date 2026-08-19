export function downloadCategories(response) {
  const values = response?.facets?.categories
  return Array.isArray(values) ? values.filter(Boolean) : []
}

export function jobQuery(kind, keyword, company, topK = 50) {
  const params = { kind, top_k: topK }
  if (keyword.trim()) params.keyword = keyword.trim()
  if (company.trim()) params.company = company.trim()
  return params
}
