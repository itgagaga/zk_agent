import { Routes, Route, Link } from 'react-router-dom'
import HomePage from './pages/HomePage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import DownloadsPage from './pages/DownloadsPage.jsx'
import ServicesPage from './pages/ServicesPage.jsx'
import DocumentsPage from './pages/DocumentsPage.jsx'
import ResumePage from './pages/ResumePage.jsx'
import Footer from './components/Footer.jsx'
import NavPill from './components/NavPill.jsx'

export default function App() {
  return (
    <div className="app">
      <NavPill />
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/downloads" element={<DownloadsPage />} />
          <Route path="/services" element={<ServicesPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/resume" element={<ResumePage />} />
        </Routes>
      </main>
      <Footer />
    </div>
  )
}
