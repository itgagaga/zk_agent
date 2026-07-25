/**
 * 模板5：学术研究 — 极简排版，强调学术成果，适合考研/学术/研究岗
 */
export default function TemplateAcademic({ data }) {
  const { basic, education, skills, projects, intro } = data

  return (
    <div className="resume-tpl resume-tpl-academic">
      {/* 头部 */}
      <header className="tpl-ac-header">
        <div className="tpl-ac-header-left">
          <h1 className="tpl-ac-name">{basic.name || '你的姓名'}</h1>
          <div className="tpl-ac-contact">
            {basic.email && <span>{basic.email}</span>}
            {basic.phone && <span>{basic.phone}</span>}
            {basic.address && <span>{basic.address}</span>}
            {basic.website && <span>{basic.website}</span>}
          </div>
        </div>
        {basic.photo && <img src={basic.photo} alt="" className="tpl-photo" />}
      </header>

      <hr className="tpl-ac-hr" />

      {/* 教育背景（放在最前面） */}
      {education.length > 0 && education[0].school && (
        <section className="tpl-ac-section">
          <h2 className="tpl-ac-section-title">教育背景</h2>
          {education.map((edu, i) => (
            edu.school ? (
              <div key={i} className="tpl-ac-entry">
                <div className="tpl-ac-entry-row">
                  <strong>{edu.school}</strong>
                  <em>{edu.major}{edu.degree ? `, ${edu.degree}` : ''}</em>
                  <span>{edu.start}{edu.start && edu.end ? ' — ' : ''}{edu.end}</span>
                </div>
              </div>
            ) : null
          ))}
        </section>
      )}

      {/* 研究项目 / 项目经历 */}
      {projects.length > 0 && projects[0].name && (
        <section className="tpl-ac-section">
          <h2 className="tpl-ac-section-title">研究项目</h2>
          {projects.map((proj, i) => (
            proj.name ? (
              <div key={i} className="tpl-ac-entry">
                <div className="tpl-ac-entry-row">
                  <strong>{proj.name}</strong>
                  <span>{proj.start}{proj.start && proj.end ? ' — ' : ''}{proj.end}</span>
                </div>
                {proj.role && <div className="tpl-ac-entry-role">{proj.role}</div>}
                {proj.tech_stack && <div className="tpl-ac-entry-tech">技术/方法：{proj.tech_stack}</div>}
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

      {/* 专业技能 */}
      {skills.length > 0 && skills[0].category && (
        <section className="tpl-ac-section">
          <h2 className="tpl-ac-section-title">专业技能</h2>
          <div className="tpl-ac-skills">
            {skills.map((sg, i) => (
              sg.category ? (
                <div key={i}>
                  <strong>{sg.category}：</strong>{sg.items}
                </div>
              ) : null
            ))}
          </div>
        </section>
      )}

      {/* 自我介绍 */}
      {intro && (
        <section className="tpl-ac-section">
          <h2 className="tpl-ac-section-title">个人陈述</h2>
          <p className="tpl-ac-intro">{intro}</p>
        </section>
      )}
    </div>
  )
}
