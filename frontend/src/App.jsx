import { Routes, Route, Navigate } from 'react-router-dom'
import HomePage from './pages/HomePage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import DownloadsPage from './pages/DownloadsPage.jsx'
import DocumentsPage from './pages/DocumentsPage.jsx'
import ResumePage from './pages/ResumePage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import RegisterPage from './pages/RegisterPage.jsx'
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
          <Route path="/services" element={<Navigate to="/downloads" replace />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/resume" element={<ResumePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Routes>
      </main>
      <Footer />
    </div>
  )
}
