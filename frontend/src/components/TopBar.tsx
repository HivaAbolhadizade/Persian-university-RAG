import { Menu, Moon, Sun, Wifi } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import type { SystemHealth } from '../types';

interface TopBarProps {
  health: SystemHealth | null;
  onOpenMenu: () => void;
}

const routeLabels: Record<string, string> = {
  '/': 'پرسش و پاسخ',
  '/documents': 'اسناد و منابع',
  '/upload': 'آپلود سند',
  '/index': 'ساخت ایندکس',
  '/evaluation': 'ارزیابی سیستم',
  '/settings': 'تنظیمات',
  '/about': 'درباره پروژه',
};

function getInitialTheme(): 'light' | 'dark' {
  const stored = window.localStorage.getItem('university-rag-theme');
  return stored === 'dark' ? 'dark' : 'light';
}

export default function TopBar({ health, onOpenMenu }: TopBarProps) {
  const location = useLocation();
  const [theme, setTheme] = useState<'light' | 'dark'>(getInitialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('university-rag-theme', theme);
  }, [theme]);

  return (
    <header className="desktop-topbar rtl-topbar">
      <div className="topbar-page-title">
        <button className="topbar-menu-button" type="button" onClick={onOpenMenu} aria-label="باز کردن منو">
          <Menu size={20} />
        </button>
        <div>
          <strong>{routeLabels[location.pathname] || 'سامانه دانشگاه'}</strong>
          <span>University RAG</span>
        </div>
      </div>

      <div className="topbar-actions simple-topbar-actions">
        <div className={`topbar-health health-${health?.status || 'offline'}`}>
          <span className="health-pulse" />
          <Wifi size={16} />
          <span>{health?.status === 'ready' ? 'سرویس‌ها فعال' : 'حالت نمایشی'}</span>
        </div>

        <button
          className="icon-button topbar-icon-button"
          type="button"
          aria-label="تغییر پوسته"
          onClick={() => setTheme((value) => (value === 'light' ? 'dark' : 'light'))}
        >
          {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
        </button>
      </div>
    </header>
  );
}
