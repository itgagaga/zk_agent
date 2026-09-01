export const KNOWLEDGE_SCOPE_STORAGE_KEY = 'zhku_knowledge_scope'

export const KNOWLEDGE_SCOPE_OPTIONS = [
  { value: 'auto', label: '标准', tone: 'standard', description: '校园公开资料与平台工具' },
  { value: 'with_personal', label: '增强', tone: 'enhanced', description: '标准资料加上个人知识库' },
  { value: 'personal_only', label: '私有', tone: 'private', description: '仅使用个人知识库' },
]

const KNOWLEDGE_SCOPE_VALUES = new Set(KNOWLEDGE_SCOPE_OPTIONS.map(option => option.value))

export function isKnowledgeScope(value) {
  return KNOWLEDGE_SCOPE_VALUES.has(value)
}

export function readKnowledgeScope(storage, authenticated) {
  if (!authenticated) return 'auto'
  try {
    const value = storage.getItem(KNOWLEDGE_SCOPE_STORAGE_KEY)
    return isKnowledgeScope(value) ? value : 'auto'
  } catch {
    return 'auto'
  }
}

export function persistKnowledgeScope(storage, value) {
  const scope = isKnowledgeScope(value) ? value : 'auto'
  try {
    storage.setItem(KNOWLEDGE_SCOPE_STORAGE_KEY, scope)
  } catch {
    // ignore unavailable/private storage
  }
  return scope
}
