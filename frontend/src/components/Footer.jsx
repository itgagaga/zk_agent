export default function Footer() {
  return (
    <footer className="footer">
      <h2 style={{ color: 'white', maxWidth: 600 }}>
        我们随时在这里，当你想了解仲恺的时候。
      </h2>
      <div className="footer-grid">
        <div>
          <div className="footer-col-title">项目</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <a href="/">项目简介</a>
            <a href="/chat">智能问答</a>
            <a href="/documents">智能文档</a>
          </div>
        </div>
        <div>
          <div className="footer-col-title">服务</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <a href="/downloads">办事资料智库</a>
          </div>
        </div>
        <div>
          <div className="footer-col-title">数据来源</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <a href="https://www.zhku.edu.cn/" target="_blank" rel="noreferrer">
              仲恺农业工程学院 ↗
            </a>
            <a href="https://jwc.zhku.edu.cn/" target="_blank" rel="noreferrer">
              教务部 ↗
            </a>
            <a href="https://yjs.zhku.edu.cn/" target="_blank" rel="noreferrer">
              研究生处 ↗
            </a>
          </div>
        </div>
        <div>
          <div className="footer-col-title">关于</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <span>仅基于公开资料</span>
            <span>不采集个人隐私</span>
            <span>v0.1.0</span>
          </div>
        </div>
      </div>
    </footer>
  )
}
