import { Menu } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { getSystemHealth } from '../api/client';
import type { SystemHealth } from '../types';
import Sidebar from './Sidebar';
import TopBar from './TopBar';

function getInitialCollapsed(): boolean {
  return window.localStorage.getItem('university-rag-sidebar-collapsed') === 'true';
}

export default function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(getInitialCollapsed);
  const [health, setHealth] = useState<SystemHealth | null>(null);

  useEffect(() => {
    getSystemHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  function toggleCollapsed() {
    setSidebarCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem('university-rag-sidebar-collapsed', String(next));
      return next;
    });
  }

  return (
    <div className={`app-shell rtl-shell ${sidebarCollapsed ? 'sidebar-is-collapsed' : ''}`}>
      <Sidebar
        open={sidebarOpen}
        collapsed={sidebarCollapsed}
        onClose={() => setSidebarOpen(false)}
        onToggleCollapsed={toggleCollapsed}
        health={health}
      />

      <main className="app-main">
        <TopBar health={health} onOpenMenu={() => setSidebarOpen(true)} />

        <header className="mobile-header">
          <img src="/university-rag-mark.svg" alt="نشان پروژه University RAG" />
          <div>
            <strong>سامانه پرسش و پاسخ دانشگاه</strong>
            <span>دانشگاه شهید باهنر کرمان</span>
          </div>
          <button onClick={() => setSidebarOpen(true)} aria-label="باز کردن منو">
            <Menu size={23} />
          </button>
        </header>

        <Outlet />
      </main>
    </div>
  );
}
