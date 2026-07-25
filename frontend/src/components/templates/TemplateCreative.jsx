/**
 * 模板4：创意彩页 — 顶部彩色横幅+图标，适合设计/市场/应届生
 */
export default function TemplateCreative({ data }) {
  const { basic, education, skills, projects, intro } = data

  return (
    <div className="resume-tpl resume-tpl-creative">
      {/* 顶部彩色横幅 */}
      <header className="tpl-cre-header">
        <div className="tpl-cre-header-content">
          <h1 className="tpl-cre-name">{basic.name || '你的姓名'}</h1>
          <div className="tpl-cre-contact">
            {basic.phone && <span>📱 {basic.phone}</span>}
            {basic.email && <span>✉️ {basic.email}</span>}
            {basic.address && <span>📍 {basic.address}</span>}
            {basic.website && <span>🔗 {basic.website}</span>}
          </div>
        </div>
        {basic.photo && <img src={basic.photo} alt="" className="tpl-cre-photo" />}
      </header>

      {/* 自我介绍（放在最前面） */}
      {intro && (
        <section className="tpl-cre-section">
          <h2 className="tpl-cre-section-title">🌟 自我介绍</h2>
          <p className="tpl-cre-intro">{intro}</p>
        </section>
      )}

      {/* 教育背景 */}
      {education.length > 0 && education[0].school && (
        <section className="tpl-cre-section">
          <h2 className="tpl-cre-section-title">🎓 教育背景</h2>
          {education.map((edu, i) => (
            edu.school ? (
              <div key={i} className="tpl-cre-entry">
                <div className="tpl-cre-entry-header">
                  <span className="tpl-cre-entry-title">{edu.school}</span>
                  <span className="tpl-cre-entry-date">{edu.start}{edu.start && edu.end ? ' - ' : ''}{edu.end}</span>
                </div>
                <div className="tpl-cre-entry-sub">{edu.major}{edu.degree ? ` · ${edu.degree}` : ''}</div>
              </div>
            ) : null
          ))}
        </section>
      )}

      {/* 专业技能 */}
      {skills.length > 0 && skills[0].category && (
        <section className="tpl-cre-section">
          <h2 className="tpl-cre-section-title">💡 专业技能</h2>
          <div className="tpl-cre-skills-wrap">
            {skills.map((sg, i) => (
              sg.category ? (
                <div key={i} className="tpl-cre-skill-chip-group">
                  <span className="tpl-cre-skill-cat">{sg.category}</span>
                  <div className="tpl-cre-skill-chips">
                    {sg.items.split(/[,，、]/).filter(s => s.trim()).map((item, j) => (
                      <span key={j} className="tpl-cre-skill-chip">{item.trim()}</span>
                    ))}
                  </div>
                </div>
              ) : null
            ))}
          </div>
        </section>
      )}

      {/* 项目经历 */}
      {projects.length > 0 && projects[0].name && (
        <section className="tpl-cre-section">
          <h2 className="tpl-cre-section-title">📂 项目经历</h2>
          {projects.map((proj, i) => (
            proj.name ? (
              <div key={i} className="tpl-cre-entry">
                <div className="tpl-cre-entry-header">
                  <span className="tpl-cre-entry-title">{proj.name}</span>
                  <span className="tpl-cre-entry-date">{proj.start}{proj.start && proj.end ? ' - ' : ''}{proj.end}</span>
                </div>
                {proj.role && <div className="tpl-cre-entry-sub">{proj.role}{proj.tech_stack ? ` | ${proj.tech_stack}` : ''}</div>}
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
        </section>
      )}
    </div>
  )
}
