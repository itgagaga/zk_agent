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
