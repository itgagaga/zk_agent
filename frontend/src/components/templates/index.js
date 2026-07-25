import TemplateClassic from './TemplateClassic'
import TemplateModern from './TemplateModern'
import TemplateBusiness from './TemplateBusiness'
import TemplateCreative from './TemplateCreative'
import TemplateAcademic from './TemplateAcademic'

export const TEMPLATES = [
  { id: 'classic', name: '经典简约', desc: '白底黑字，简洁大方', component: TemplateClassic, color: '#141413' },
  { id: 'modern', name: '现代双栏', desc: '深色侧栏+白色内容', component: TemplateModern, color: '#1a1a2e' },
  { id: 'business', name: '商务雅致', desc: '灰蓝配色，正式稳重', component: TemplateBusiness, color: '#2c3e50' },
  { id: 'creative', name: '创意彩页', desc: '彩色横幅，活泼灵动', component: TemplateCreative, color: '#cf4500' },
  { id: 'academic', name: '学术研究', desc: '极简排版，学术风格', component: TemplateAcademic, color: '#333' },
]

export function getTemplate(id) {
  return TEMPLATES.find(t => t.id === id) || TEMPLATES[0]
}
