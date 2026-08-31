// 统一处理模型响应，兼容字符串、结构化内容块和内容块数组。
export function extractTextContent(value) {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(extractTextContent).join('')
  if (value && typeof value === 'object') {
    return extractTextContent(value.text ?? value.content ?? '')
  }
  return value == null ? '' : String(value)
}
