import { useRef, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { TEMPLATES, getTemplate } from './templates'

// 与 ResumePage 中保持一致的默认值
const DEFAULTS = {
  basic: { name: '张三', phone: '138****0000', email: 'example@email.com', address: '广东省广州市', website: '' },
  education: [{ school: '仲恺农业工程学院', major: '计算机科学与技术', degree: '本科', start: '2022.09', end: '2026.06' }],
  target_position: '软件开发工程师',
}

function fillDefaults(data) {
  const basic = { ...data.basic }
  for (const [k, v] of Object.entries(DEFAULTS.basic)) {
    if (!basic[k]) basic[k] = v
  }
  const education = data.education.map(e => {
    const filled = { ...e }
    for (const [k, v] of Object.entries(DEFAULTS.education[0])) {
      if (!filled[k]) filled[k] = v
    }
    return filled
  })
  return { ...data, basic, education }
}

export default function ResumePreview({ data, templateId, onTemplateChange, onEnhance, enhancing }) {
  const previewRef = useRef(null)
  const tpl = getTemplate(templateId)
  const TemplateComponent = tpl.component

  // 预览时用默认值补齐空字段
  const displayData = useMemo(() => fillDefaults(data), [data])

  // 检查是否已有 LLM 优化结果（自我介绍/技能/项目有内容）
  const hasEnhanced = !!(data.intro || (data.skills.length > 0 && data.skills[0].category) || (data.projects.length > 0 && data.projects[0].name && data.projects[0].description))

  /**
   * 在隐藏容器中以 1:1 原始尺寸渲染简历，用于 html2canvas 截图。
   * 这样可以避免 CSS transform: scale() 导致的截断问题。
   */
  function renderForExport() {
    // 创建隐藏容器
    const container = document.createElement('div')
    container.style.cssText = 'position:fixed;left:-9999px;top:0;width:210mm;z-index:-1;'
    document.body.appendChild(container)

    // 渲染模板
    const inner = document.createElement('div')
    inner.className = 'rp-preview-page'
    inner.style.cssText = 'background:white;width:210mm;min-height:297mm;'
    container.appendChild(inner)

    const root = createRoot(inner)
    root.render(<TemplateComponent data={displayData} />)

    return { container, root }
  }

  async function handleExportPDF() {
    // 导出前如果没有优化过，先自动优化
    if (!hasEnhanced && onEnhance) {
      await onEnhance()
      await new Promise(r => setTimeout(r, 100))
    }

    const html2pdf = (await import('html2pdf.js')).default

    // 用隐藏容器 1:1 渲染，避免 scale 截断
    const { container, root } = renderForExport()

    // 等待渲染完成
    await new Promise(r => setTimeout(r, 300))

    const element = container.querySelector('.rp-preview-page')
    const opt = {
      margin: [10, 10, 10, 10],
      filename: `${displayData.basic.name || '简历'}_${tpl.name}.pdf`,
      image: { type: 'jpeg', quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true, width: element.scrollWidth, windowWidth: element.scrollWidth },
      jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
    }

    try {
      await html2pdf().set(opt).from(element).save()
    } finally {
      // 清理隐藏容器
      root.unmount()
      document.body.removeChild(container)
    }
  }

  function printResume() {
    const printWin = window.open('', '_blank')
    if (!printWin || !previewRef.current) return
    printWin.document.write(`
      <html><head><title>简历 - ${data.basic.name || ''}</title>
      <style>
        body { margin: 0; padding: 20px; font-family: sans-serif; }
        @media print { body { padding: 0; } }
      </style>
      </head><body>${previewRef.current.innerHTML}</body></html>
    `)
    printWin.document.close()
    printWin.print()
  }

  return (
    <div className="resume-preview">
      {/* 模板选择 */}
      <div className="rp-template-bar">
        <span className="rp-template-label">选择模板</span>
        <div className="rp-template-options">
          {TEMPLATES.map(t => (
            <button
              key={t.id}
              className={`rp-template-btn ${templateId === t.id ? 'active' : ''}`}
              onClick={() => onTemplateChange(t.id)}
              title={t.desc}
            >
              <span className="rp-template-dot" style={{ background: t.color }} />
              {t.name}
            </button>
          ))}
        </div>
      </div>

      {/* 简历预览 */}
      <div className="rp-preview-wrap">
        <div className="rp-preview-scaler">
          <div ref={previewRef} className="rp-preview-page">
            <TemplateComponent data={displayData} />
          </div>
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="rp-actions">
        <button className="btn-primary" onClick={handleExportPDF} disabled={enhancing}>
          {enhancing ? <><span className="rf-spinner" /> AI 优化中...</> : <>📄 导出 PDF</>}
        </button>
        <button className="btn-secondary" onClick={printResume}>
          🖨️ 打印
        </button>
      </div>
    </div>
  )
}
