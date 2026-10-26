import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './components/AppShell';
import AboutPage from './pages/AboutPage';
import ChatPage from './pages/ChatPage';
import DocumentsPage from './pages/DocumentsPage';
import EvaluationPage from './pages/EvaluationPage';
import IndexPage from './pages/IndexPage';
import SettingsPage from './pages/SettingsPage';
import UploadPage from './pages/UploadPage';

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<ChatPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="index" element={<IndexPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
