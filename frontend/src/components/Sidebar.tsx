import {
  ArrowDown,
  BadgeCheck,
  BarChart3,
  BotMessageSquare,
  BrainCircuit,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Database,
  FileSearch,
  Files,
  FileText,
  Info,
  MessageCircleQuestion,
  PanelRightClose,
  PanelRightOpen,
  Settings,
  Sparkles,
  Upload,
  Workflow,
  X,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import type { SystemHealth } from '../types';

interface SidebarProps {
  open: boolean;
  collapsed: boolean;
  onClose: () => void;
  onToggleCollapsed: () => void;
  health: SystemHealth | null;
}

const navGroups = [
  {
    label: 'کاربری',
    items: [
      { to: '/', icon: BotMessageSquare, label: 'پرسش و پاسخ' },
      { to: '/documents', icon: FileText, label: 'اسناد و منابع' },
      { to: '/upload', icon: Upload, label: 'آپلود سند' },
    ],
  },
  {
    label: 'مدیریت سامانه',
    items: [
      { to: '/index', icon: Database, label: 'ساخت ایندکس' },
      { to: '/evaluation', icon: BarChart3, label: 'ارزیابی سیستم' },
      { to: '/settings', icon: Settings, label: 'تنظیمات' },
    ],
  },
  {
    label: 'اطلاعات',
    items: [{ to: '/about', icon: Info, label: 'درباره پروژه' }],
  },
];

const workflowSteps = [
  {
    icon: MessageCircleQuestion,
    title: 'سؤال کاربر',
    description: 'دریافت پرسش فارسی',
  },
  {
    icon: Sparkles,
    title: 'آماده‌سازی پرسش',
    description: 'نرمال‌سازی و تحلیل',
  },
  {
    icon: FileSearch,
    title: 'بازیابی ترکیبی',
    description: 'BM25 + جست‌وجوی برداری',
  },
  {
    icon: Files,
    title: 'انتخاب شواهد',
    description: 'رتبه‌بندی منابع مرتبط',
  },
  {
    icon: BrainCircuit,
    title: 'تولید پاسخ',
    description: 'مدل زبانی Grounded',
  },
  {
    icon: BadgeCheck,
    title: 'پاسخ مستند',
    description: 'منبع، صفحه و ماده',
  },
];

export default function Sidebar({
  open,
  collapsed,
  onClose,
  onToggleCollapsed,
  health,
}: SidebarProps) {
  return (
    <>
      <div
        className={`sidebar-overlay ${open ? 'is-open' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        className={`sidebar rtl-sidebar ${
          open ? 'is-open' : ''
        } ${collapsed ? 'is-collapsed' : ''}`}
      >
        <button
          className="sidebar-close"
          onClick={onClose}
          aria-label="بستن منو"
        >
          <X size={21} />
        </button>

        <div className="brand-block rtl-brand-block">
          <img
            src="/university-rag-mark.svg"
            alt="لوگوی دانشگاه شهید باهنر کرمان"
          />
          <div className="brand-copy">
            <strong>سامانه هوشمند دانشگاه</strong>
            <span>دانشگاه شهید باهنر کرمان</span>
          </div>
        </div>

        <button
          className="sidebar-collapse-button"
          type="button"
          onClick={onToggleCollapsed}
          aria-label={
            collapsed ? 'باز کردن سایدبار' : 'جمع کردن سایدبار'
          }
          title={
            collapsed ? 'باز کردن سایدبار' : 'جمع کردن سایدبار'
          }
        >
          {collapsed ? (
            <PanelRightOpen size={18} />
          ) : (
            <PanelRightClose size={18} />
          )}
          {!collapsed && <span>جمع کردن منو</span>}
        </button>

        <nav className="sidebar-nav" aria-label="منوی اصلی">
          {navGroups.map((group) => (
            <div className="sidebar-nav-group" key={group.label}>
              {!collapsed && (
                <span className="sidebar-group-label">
                  {group.label}
                </span>
              )}
              {group.items.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  onClick={onClose}
                  title={collapsed ? label : undefined}
                  className={({ isActive }) =>
                    `sidebar-link ${
                      isActive ? 'is-active' : ''
                    }`
                  }
                >
                  <span className="sidebar-link-icon">
                    <Icon size={20} strokeWidth={1.8} />
                  </span>
                  {!collapsed && (
                    <span className="sidebar-link-label">
                      {label}
                    </span>
                  )}
                  {!collapsed && (
                    <ChevronLeft
                      className="sidebar-link-arrow"
                      size={15}
                    />
                  )}
                  {collapsed && (
                    <ChevronRight
                      className="sidebar-link-arrow-collapsed"
                      size={13}
                    />
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        {!collapsed && (
          <details className="sidebar-flowchart" open>
            <summary>
              <span>
                <Workflow size={18} />
                نحوه کار سامانه
              </span>
              <ChevronDown size={16} />
            </summary>

            <div className="sidebar-flowchart-body">
              {workflowSteps.map(
                ({ icon: Icon, title, description }, index) => (
                  <div
                    className="flowchart-step"
                    key={title}
                  >
                    <span className="flowchart-step-icon">
                      <Icon size={16} />
                    </span>
                    <div>
                      <strong>{title}</strong>
                      <small>{description}</small>
                    </div>
                    {index < workflowSteps.length - 1 && (
                      <ArrowDown
                        className="flowchart-connector"
                        size={14}
                      />
                    )}
                  </div>
                ),
              )}
            </div>
          </details>
        )}

        <div
          className="system-status-card compact-system-card"
          title={collapsed ? 'وضعیت سامانه' : undefined}
        >
          <div className="compact-status-head">
            <span
              className={`system-dot ${
                health?.status === 'ready'
                  ? 'is-ready'
                  : 'is-demo'
              }`}
            />
            {!collapsed && (
              <div>
                <strong>
                  {health?.status === 'ready'
                    ? 'سامانه آماده است'
                    : 'حالت نمایشی'}
                </strong>
                <span>
                  {health?.documents?.toLocaleString('fa-IR') ??
                    '—'}{' '}
                  سند،{' '}
                  {health?.chunks?.toLocaleString('fa-IR') ?? '—'}{' '}
                  قطعه
                </span>
              </div>
            )}
          </div>
          {!collapsed && (
            <small>{health?.retriever ?? 'Hybrid + Rerank'}</small>
          )}
        </div>
      </aside>
    </>
  );
}
