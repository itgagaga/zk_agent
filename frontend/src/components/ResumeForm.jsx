import { useState } from 'react'

const EMPTY_EDUCATION = { school: '', major: '', degree: '', start: '', end: '' }
const EMPTY_SKILL = { category: '', items: '' }
const EMPTY_PROJECT = { name: '', role: '', start: '', end: '', description: '', tech_stack: '' }

export default function ResumeForm({ data, onChange, onEnhance, enhancing }) {
  const [openSections, setOpenSections] = useState({
    basic: true, education: true, skills: true, projects: true, intro: true,
  })

  function toggle(key) {
    setOpenSections(prev => ({ ...prev, [key]: !prev[key] }))
  }

  function updateBasic(field, value) {
    onChange({ ...data, basic: { ...data.basic, [field]: value } })
  }

  function handlePhotoUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    // 限制文件大小 2MB
    if (file.size > 2 * 1024 * 1024) {
      alert('照片大小不能超过 2MB')
      return
    }
    const reader = new FileReader()
    reader.onload = (ev) => {
      updateBasic('photo', ev.target.result)
    }
    reader.readAsDataURL(file)
  }

  function removePhoto() {
    updateBasic('photo', '')
  }

  function updateEducation(index, field, value) {
    const list = [...data.education]
    list[index] = { ...list[index], [field]: value }
    onChange({ ...data, education: list })
  }

  function addEducation() {
    onChange({ ...data, education: [...data.education, { ...EMPTY_EDUCATION }] })
  }

  function removeEducation(index) {
    onChange({ ...data, education: data.education.filter((_, i) => i !== index) })
  }

  function updateSkill(index, field, value) {
    const list = [...data.skills]
    list[index] = { ...list[index], [field]: value }
    onChange({ ...data, skills: list })
  }

  function addSkill() {
    onChange({ ...data, skills: [...data.skills, { ...EMPTY_SKILL }] })
  }

  function removeSkill(index) {
    onChange({ ...data, skills: data.skills.filter((_, i) => i !== index) })
  }

  function updateProject(index, field, value) {
    const list = [...data.projects]
    list[index] = { ...list[index], [field]: value }
    onChange({ ...data, projects: list })
  }

  function addProject() {
    onChange({ ...data, projects: [...data.projects, { ...EMPTY_PROJECT }] })
  }

  function removeProject(index) {
    onChange({ ...data, projects: data.projects.filter((_, i) => i !== index) })
  }

  return (
    <div className="resume-form">
      {/* 基本情况 */}
      <div className="rf-section">
        <button className="rf-section-toggle" onClick={() => toggle('basic')}>
          <span className={`rf-toggle-icon ${openSections.basic ? 'open' : ''}`}>▸</span>
          基本情况
        </button>
        {openSections.basic && (
          <div className="rf-section-body">
            {/* 个人照片上传 */}
            <div className="rf-photo-upload">
              <div className="rf-photo-preview">
                {data.basic.photo ? (
                  <>
                    <img src={data.basic.photo} alt="个人照片" className="rf-photo-img" />
                    <button className="rf-photo-remove" onClick={removePhoto}>✕</button>
                  </>
                ) : (
                  <label className="rf-photo-placeholder">
                    <span>📷</span>
                    <span>上传照片</span>
                    <input type="file" accept="image/*" onChange={handlePhotoUpload} hidden />
                  </label>
                )}
              </div>
              <div className="rf-photo-hint">建议上传1寸证件照<br/>支持 JPG/PNG，2MB以内</div>
            </div>
            <div className="rf-field">
              <label>姓名</label>
              <input value={data.basic.name || ''} onChange={e => updateBasic('name', e.target.value)} placeholder="张三" />
            </div>
            <div className="rf-row-2">
              <div className="rf-field">
                <label>手机</label>
                <input value={data.basic.phone || ''} onChange={e => updateBasic('phone', e.target.value)} placeholder="13800138000" />
              </div>
              <div className="rf-field">
                <label>邮箱</label>
                <input value={data.basic.email || ''} onChange={e => updateBasic('email', e.target.value)} placeholder="zhangsan@example.com" />
              </div>
            </div>
            <div className="rf-row-2">
              <div className="rf-field">
                <label>地址</label>
                <input value={data.basic.address || ''} onChange={e => updateBasic('address', e.target.value)} placeholder="广东省广州市" />
              </div>
              <div className="rf-field">
                <label>个人网站/GitHub</label>
                <input value={data.basic.website || ''} onChange={e => updateBasic('website', e.target.value)} placeholder="github.com/zhangsan" />
              </div>
            </div>
            <div className="rf-field">
              <label>目标职位</label>
              <input value={data.target_position || ''} onChange={e => onChange({ ...data, target_position: e.target.value })} placeholder="前端开发工程师" />
            </div>
          </div>
        )}
      </div>

      {/* 教育背景 */}
      <div className="rf-section">
        <button className="rf-section-toggle" onClick={() => toggle('education')}>
          <span className={`rf-toggle-icon ${openSections.education ? 'open' : ''}`}>▸</span>
          教育背景
        </button>
        {openSections.education && (
          <div className="rf-section-body">
            {data.education.map((edu, i) => (
              <div key={i} className="rf-repeat-item">
                <div className="rf-repeat-header">
                  <span>教育经历 {i + 1}</span>
                  <button className="rf-remove-btn" onClick={() => removeEducation(i)}>✕</button>
                </div>
                <div className="rf-row-2">
                  <div className="rf-field">
                    <label>学校</label>
                    <input value={edu.school} onChange={e => updateEducation(i, 'school', e.target.value)} placeholder="仲恺农业工程学院" />
                  </div>
                  <div className="rf-field">
                    <label>专业</label>
                    <input value={edu.major} onChange={e => updateEducation(i, 'major', e.target.value)} placeholder="计算机科学与技术" />
                  </div>
                </div>
                <div className="rf-row-3">
                  <div className="rf-field">
                    <label>学历</label>
                    <select value={edu.degree} onChange={e => updateEducation(i, 'degree', e.target.value)}>
                      <option value="">请选择</option>
                      <option>本科</option>
                      <option>硕士</option>
                      <option>博士</option>
                      <option>大专</option>
                    </select>
                  </div>
                  <div className="rf-field">
                    <label>开始时间</label>
                    <input value={edu.start} onChange={e => updateEducation(i, 'start', e.target.value)} placeholder="2022.09" />
                  </div>
                  <div className="rf-field">
                    <label>结束时间</label>
                    <input value={edu.end} onChange={e => updateEducation(i, 'end', e.target.value)} placeholder="2026.06" />
                  </div>
                </div>
              </div>
            ))}
            <button className="rf-add-btn" onClick={addEducation}>+ 添加教育经历</button>
          </div>
        )}
      </div>

      {/* 专业技能 */}
      <div className="rf-section">
        <button className="rf-section-toggle" onClick={() => toggle('skills')}>
          <span className={`rf-toggle-icon ${openSections.skills ? 'open' : ''}`}>▸</span>
          专业技能
        </button>
        {openSections.skills && (
          <div className="rf-section-body">
            {data.skills.map((sg, i) => (
              <div key={i} className="rf-repeat-item">
                <div className="rf-repeat-header">
                  <span>技能分组 {i + 1}</span>
                  <button className="rf-remove-btn" onClick={() => removeSkill(i)}>✕</button>
                </div>
                <div className="rf-row-2">
                  <div className="rf-field">
                    <label>分类</label>
                    <input value={sg.category} onChange={e => updateSkill(i, 'category', e.target.value)} placeholder="前端开发" />
                  </div>
                  <div className="rf-field">
                    <label>技能列表（逗号分隔）</label>
                    <input value={sg.items} onChange={e => updateSkill(i, 'items', e.target.value)} placeholder="React, Vue, TypeScript" />
                  </div>
                </div>
              </div>
            ))}
            <button className="rf-add-btn" onClick={addSkill}>+ 添加技能分组</button>
          </div>
        )}
      </div>

      {/* 项目经历 */}
      <div className="rf-section">
        <button className="rf-section-toggle" onClick={() => toggle('projects')}>
          <span className={`rf-toggle-icon ${openSections.projects ? 'open' : ''}`}>▸</span>
          项目经历
        </button>
        {openSections.projects && (
          <div className="rf-section-body">
            {data.projects.map((proj, i) => (
              <div key={i} className="rf-repeat-item">
                <div className="rf-repeat-header">
                  <span>项目 {i + 1}</span>
                  <button className="rf-remove-btn" onClick={() => removeProject(i)}>✕</button>
                </div>
                <div className="rf-row-2">
                  <div className="rf-field">
                    <label>项目名称</label>
                    <input value={proj.name} onChange={e => updateProject(i, 'name', e.target.value)} placeholder="校园智能问答系统" />
                  </div>
                  <div className="rf-field">
                    <label>角色</label>
                    <input value={proj.role} onChange={e => updateProject(i, 'role', e.target.value)} placeholder="全栈开发" />
                  </div>
                </div>
                <div className="rf-row-3">
                  <div className="rf-field">
                    <label>开始时间</label>
                    <input value={proj.start} onChange={e => updateProject(i, 'start', e.target.value)} placeholder="2025.03" />
                  </div>
                  <div className="rf-field">
                    <label>结束时间</label>
                    <input value={proj.end} onChange={e => updateProject(i, 'end', e.target.value)} placeholder="2025.07" />
                  </div>
                  <div className="rf-field">
                    <label>技术栈</label>
                    <input value={proj.tech_stack} onChange={e => updateProject(i, 'tech_stack', e.target.value)} placeholder="React, FastAPI" />
                  </div>
                </div>
                <div className="rf-field">
                  <label>项目描述</label>
                  <textarea
                    value={proj.description}
                    onChange={e => updateProject(i, 'description', e.target.value)}
                    placeholder="负责前端开发，实现了智能问答界面和实时对话功能；设计了RAG检索增强架构，提高了回答准确率..."
                    rows={3}
                  />
                </div>
              </div>
            ))}
            <button className="rf-add-btn" onClick={addProject}>+ 添加项目经历</button>
          </div>
        )}
      </div>

      {/* 自我介绍 */}
      <div className="rf-section">
        <button className="rf-section-toggle" onClick={() => toggle('intro')}>
          <span className={`rf-toggle-icon ${openSections.intro ? 'open' : ''}`}>▸</span>
          自我介绍
        </button>
        {openSections.intro && (
          <div className="rf-section-body">
            <div className="rf-field">
              <label>关键词/短句（AI 将帮你扩展为完整段落）</label>
              <textarea
                value={data.intro_keywords}
                onChange={e => onChange({ ...data, intro_keywords: e.target.value })}
                placeholder="有3年前端开发经验；擅长React生态；对用户体验有追求；有团队协作经验；持续学习新技术"
                rows={3}
              />
            </div>
          </div>
        )}
      </div>

      {/* AI 优化按钮 */}
      <button
        className="rf-enhance-btn"
        onClick={onEnhance}
        disabled={enhancing}
      >
        {enhancing ? (
          <><span className="rf-spinner" /> AI 正在优化...</>
        ) : (
          <>✨ AI 一键优化</>
        )}
      </button>
    </div>
  )
}
