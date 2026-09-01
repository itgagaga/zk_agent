// 新检索编排的元数据合并；保留旧 SSE 字段，避免迁移期间丢失来源。
export function mergeRetrievalMeta(previous = {}, incoming = {}) {
  return {
    ...previous,
    ...incoming,
    sources: incoming.sources ?? previous.sources ?? [],
    attachments: incoming.attachments ?? previous.attachments ?? [],
    tools_used: incoming.tools_used ?? previous.tools_used ?? [],
    confidence: incoming.confidence ?? previous.confidence,
  }
}

export function getPersonalScopeStatus(summary = {}) {
  if (!summary || summary.knowledge_scope === 'auto') return null

  if (summary.personal_documents_used) {
    return { tone: 'success', symbol: '✓', label: '已使用个人资料' }
  }

  const labels = {
    no_hit: { tone: 'neutral', symbol: '⌕', label: '个人资料未命中' },
    failed: { tone: 'warning', symbol: '!', label: '个人资料检索失败' },
    empty_library: { tone: 'neutral', symbol: '∅', label: '个人知识库为空' },
    skipped: { tone: 'neutral', symbol: '–', label: '个人资料未执行' },
    retrieved: { tone: 'neutral', symbol: '·', label: '个人资料已检索，未作为回答依据' },
  }
  return labels[summary.personal_documents_status] || null
}
