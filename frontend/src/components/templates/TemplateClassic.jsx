/**
 * 模板1：经典简约 — 白底黑字，单栏布局，适合通用求职
 */
export default function TemplateClassic({ data }) {
  const { basic, education, skills, projects, intro } = data

  return (
    <div className="resume-tpl resume-tpl-classic">
      {/* 头部：姓名 + 照片 + 联系方式 */}
      <header className="tpl-header">
        <div className="tpl-header-main">
          <h1 className="tpl-name">{basic.name || '你的姓名'}</h1>
          <div className="tpl-contact">
            {basic.phone && <span>{basic.phone}</span>}
            {basic.email && <span>{basic.email}</span>}
            {basic.address && <span>{basic.address}</span>}
            {basic.website && <span>{basic.website}</span>}
          </div>
        </div>
        {basic.photo && <img src={basic.photo} alt="" className="tpl-photo" />}
      </header>

      {/* 教育背景 */}
      {education.length > 0 && education[0].school && (
        <section className="tpl-section">
          <h2 className="tpl-section-title">教育背景</h2>
          <div className="tpl-section-content">
            {education.map((edu, i) => (
              edu.school ? (
                <div key={i} className="tpl-entry">
                  <div className="tpl-entry-header">
                    <span className="tpl-entry-title">{edu.school}</span>
                    <span className="tpl-entry-date">{edu.start}{edu.start && edu.end ? ' - ' : ''}{edu.end}</span>
                  </div>
                  <div className="tpl-entry-sub">{edu.major}{edu.degree ? ` · ${edu.degree}` : ''}</div>
                </div>
              ) : null
            ))}
          </div>
        </section>
      )}

      {/* 专业技能 */}
      {skills.length > 0 && skills[0].category && (
        <section className="tpl-section">
          <h2 className="tpl-section-title">专业技能</h2>
          <div className="tpl-section-content">
            {skills.map((sg, i) => (
              sg.category ? (
                <div key={i} className="tpl-skill-group">
                  <span className="tpl-skill-cat">{sg.category}：</span>
                  <span className="tpl-skill-items">{sg.items}</span>
                </div>
              ) : null
            ))}
          </div>
        </section>
      )}

      {/* 项目经历 */}
      {projects.length > 0 && projects[0].name && (
        <section className="tpl-section">
          <h2 className="tpl-section-title">项目经历</h2>
          <div className="tpl-section-content">
            {projects.map((proj, i) => (
              proj.name ? (
                <div key={i} className="tpl-entry">
                  <div className="tpl-entry-header">
                    <span className="tpl-entry-title">{proj.name}</span>
                    <span className="tpl-entry-date">{proj.start}{proj.start && proj.end ? ' - ' : ''}{proj.end}</span>
                  </div>
                  {proj.role && <div className="tpl-entry-sub">{proj.role}{proj.tech_stack ? ` | ${proj.tech_stack}` : ''}</div>}
                  {proj.description && (
                    <ul className="tpl-bullets">
                      {proj.description.split(/[;；\n]/).filter(s => s.trim()).map((line, j) => (
                        <li key={j}>{line.trim()}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : null
            ))}
          </div>
        </section>
      )}

      {/* 自我介绍 */}
      {intro && (
        <section className="tpl-section">
          <h2 className="tpl-section-title">自我介绍</h2>
          <div className="tpl-section-content">
            <p className="tpl-intro">{intro}</p>
          </div>
        </section>
      )}
    </div>
  )
}
