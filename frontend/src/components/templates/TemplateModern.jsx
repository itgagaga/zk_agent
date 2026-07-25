/**
 * 模板2：现代双栏 — 左侧深色侧栏+右侧白色内容，适合互联网/技术岗
 */
export default function TemplateModern({ data }) {
  const { basic, education, skills, projects, intro } = data

  return (
    <div className="resume-tpl resume-tpl-modern">
      {/* 左侧侧栏 */}
      <aside className="tpl-modern-sidebar">
        <div className="tpl-modern-avatar">
          {basic.photo ? (
            <img src={basic.photo} alt="" className="tpl-modern-avatar-img" />
          ) : (
            basic.name ? basic.name.charAt(0) : '你'
          )}
        </div>
        <h1 className="tpl-modern-name">{basic.name || '你的姓名'}</h1>
        {basic.phone && (
          <div className="tpl-modern-contact-item">
            <span className="tpl-modern-icon">📱</span> {basic.phone}
          </div>
        )}
        {basic.email && (
          <div className="tpl-modern-contact-item">
            <span className="tpl-modern-icon">✉️</span> {basic.email}
          </div>
        )}
        {basic.address && (
          <div className="tpl-modern-contact-item">
            <span className="tpl-modern-icon">📍</span> {basic.address}
          </div>
        )}
        {basic.website && (
          <div className="tpl-modern-contact-item">
            <span className="tpl-modern-icon">🔗</span> {basic.website}
          </div>
        )}

        {/* 技能放在侧栏 */}
        {skills.length > 0 && skills[0].category && (
          <div className="tpl-modern-skills">
            <h3 className="tpl-modern-sidebar-title">专业技能</h3>
            {skills.map((sg, i) => (
              sg.category ? (
                <div key={i} className="tpl-modern-skill-group">
                  <div className="tpl-modern-skill-cat">{sg.category}</div>
                  <div className="tpl-modern-skill-items">{sg.items}</div>
                </div>
              ) : null
            ))}
          </div>
        )}
      </aside>

      {/* 右侧主内容 */}
      <main className="tpl-modern-main">
        {/* 教育背景 */}
        {education.length > 0 && education[0].school && (
          <section className="tpl-modern-section">
            <h2 className="tpl-modern-section-title">教育背景</h2>
            {education.map((edu, i) => (
              edu.school ? (
                <div key={i} className="tpl-modern-entry">
                  <div className="tpl-modern-entry-header">
                    <strong>{edu.school}</strong>
                    <span>{edu.start}{edu.start && edu.end ? ' - ' : ''}{edu.end}</span>
                  </div>
                  <div className="tpl-modern-entry-sub">{edu.major}{edu.degree ? ` · ${edu.degree}` : ''}</div>
                </div>
              ) : null
            ))}
          </section>
        )}

        {/* 项目经历 */}
        {projects.length > 0 && projects[0].name && (
          <section className="tpl-modern-section">
            <h2 className="tpl-modern-section-title">项目经历</h2>
            {projects.map((proj, i) => (
              proj.name ? (
                <div key={i} className="tpl-modern-entry">
                  <div className="tpl-modern-entry-header">
                    <strong>{proj.name}</strong>
                    <span>{proj.start}{proj.start && proj.end ? ' - ' : ''}{proj.end}</span>
                  </div>
                  {proj.role && <div className="tpl-modern-entry-sub">{proj.role}{proj.tech_stack ? ` | ${proj.tech_stack}` : ''}</div>}
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

        {/* 自我介绍 */}
        {intro && (
          <section className="tpl-modern-section">
            <h2 className="tpl-modern-section-title">自我介绍</h2>
            <p className="tpl-modern-intro">{intro}</p>
          </section>
        )}
      </main>
    </div>
  )
}
