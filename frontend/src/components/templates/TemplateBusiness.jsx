/**
 * 模板3：商务雅致 — 衬线字体+灰蓝配色，适合金融/咨询/国企
 */
export default function TemplateBusiness({ data }) {
  const { basic, education, skills, projects, intro } = data

  return (
    <div className="resume-tpl resume-tpl-business">
      {/* 头部 */}
      <header className="tpl-biz-header">
        <div className="tpl-biz-header-top">
          <div className="tpl-biz-header-left">
            <h1 className="tpl-biz-name">{basic.name || '你的姓名'}</h1>
            <div className="tpl-biz-contact">
              {basic.phone && <span>{basic.phone}</span>}
              {basic.email && <span>{basic.email}</span>}
              {basic.address && <span>{basic.address}</span>}
              {basic.website && <span>{basic.website}</span>}
            </div>
          </div>
          {basic.photo && <img src={basic.photo} alt="" className="tpl-photo" />}
        </div>
        <div className="tpl-biz-divider" />
      </header>

      {/* 教育背景 */}
      {education.length > 0 && education[0].school && (
        <section className="tpl-biz-section">
          <h2 className="tpl-biz-section-title">教育背景</h2>
          <div className="tpl-biz-section-line" />
          {education.map((edu, i) => (
            edu.school ? (
              <div key={i} className="tpl-biz-entry">
                <div className="tpl-biz-entry-header">
                  <span className="tpl-biz-entry-title">{edu.school}</span>
                  <span className="tpl-biz-entry-date">{edu.start}{edu.start && edu.end ? ' — ' : ''}{edu.end}</span>
                </div>
                <div className="tpl-biz-entry-sub">{edu.major}{edu.degree ? ` · ${edu.degree}` : ''}</div>
              </div>
            ) : null
          ))}
        </section>
      )}

      {/* 专业技能 */}
      {skills.length > 0 && skills[0].category && (
        <section className="tpl-biz-section">
          <h2 className="tpl-biz-section-title">专业技能</h2>
          <div className="tpl-biz-section-line" />
          <div className="tpl-biz-skills-grid">
            {skills.map((sg, i) => (
              sg.category ? (
                <div key={i} className="tpl-biz-skill-group">
                  <span className="tpl-biz-skill-cat">{sg.category}</span>
                  <span className="tpl-biz-skill-items">{sg.items}</span>
                </div>
              ) : null
            ))}
          </div>
        </section>
      )}

      {/* 项目经历 */}
      {projects.length > 0 && projects[0].name && (
        <section className="tpl-biz-section">
          <h2 className="tpl-biz-section-title">项目经历</h2>
          <div className="tpl-biz-section-line" />
          {projects.map((proj, i) => (
            proj.name ? (
              <div key={i} className="tpl-biz-entry">
                <div className="tpl-biz-entry-header">
                  <span className="tpl-biz-entry-title">{proj.name}</span>
                  <span className="tpl-biz-entry-date">{proj.start}{proj.start && proj.end ? ' — ' : ''}{proj.end}</span>
                </div>
                {proj.role && <div className="tpl-biz-entry-sub">{proj.role}{proj.tech_stack ? ` | ${proj.tech_stack}` : ''}</div>}
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
        <section className="tpl-biz-section">
          <h2 className="tpl-biz-section-title">自我介绍</h2>
          <div className="tpl-biz-section-line" />
          <p className="tpl-biz-intro">{intro}</p>
        </section>
      )}
    </div>
  )
}
