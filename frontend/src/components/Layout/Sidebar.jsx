import { Link, useLocation } from 'react-router-dom';
import './Sidebar.css';

const NAV_ITEMS = [
  { section: 'Pilotage', items: [{ label: 'Vue exécutive', path: '/dashboard', icon: IconGrid }] },
  {
    section: 'Analyse',
    items: [
      { label: 'Ventes', path: '/ventes', icon: IconTrend },
      { label: 'Catalogue', path: '/produits', icon: IconBox },
      { label: 'Clients', path: '/clients', icon: IconUsers },
    ],
  },
  { section: 'Intelligence', items: [{ label: 'Prévisions ML', path: '/previsions', icon: IconRadar }] },
];

export default function Sidebar() {
  const location = useLocation();

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-mark" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <circle cx="4" cy="16" r="2.4" fill="var(--brand)" />
            <circle cx="16" cy="4" r="2.4" fill="var(--brand)" />
            <path d="M5.8 14.4 14.2 5.6" stroke="var(--brand)" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </span>
        <div className="brand-text">
          <span className="brand-name">Olist BI</span>
          <span className="brand-sub">Control Tower</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map((group) => (
          <div className="nav-group" key={group.section}>
            <span className="nav-group-label">{group.section}</span>
            {group.items.map((item) => {
              const isActive = location.pathname === item.path;
              const Icon = item.icon;
              return (
                <Link key={item.path} to={item.path} className={`nav-item${isActive ? ' active' : ''}`}>
                  <Icon />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="status-pill">
          <span className="pulse-dot" />
          <span>Agent IA connecté</span>
        </div>
      </div>
    </aside>
  );
}

function IconGrid() {
  return (
    <svg width="17" height="17" viewBox="0 0 17 17" fill="none">
      <rect x="1.5" y="1.5" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      <rect x="9.5" y="1.5" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      <rect x="1.5" y="9.5" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      <rect x="9.5" y="9.5" width="6" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}
function IconTrend() {
  return (
    <svg width="17" height="17" viewBox="0 0 17 17" fill="none">
      <path d="M1.5 12.5 6 7l3 3 6-6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M11.5 3h3.5v3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function IconBox() {
  return (
    <svg width="17" height="17" viewBox="0 0 17 17" fill="none">
      <path d="M1.7 5 8.5 1.5 15.3 5v7L8.5 15.5 1.7 12z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M1.7 5 8.5 8.5 15.3 5M8.5 8.5v7" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}
function IconUsers() {
  return (
    <svg width="17" height="17" viewBox="0 0 17 17" fill="none">
      <circle cx="6.2" cy="5" r="2.4" stroke="currentColor" strokeWidth="1.4" />
      <path d="M1.6 14c.6-2.6 2.4-4 4.6-4s4 1.4 4.6 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="12.3" cy="5.6" r="1.9" stroke="currentColor" strokeWidth="1.3" />
      <path d="M11.3 10.3c1.9.1 3.3 1.4 3.8 3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}
function IconRadar() {
  return (
    <svg width="17" height="17" viewBox="0 0 17 17" fill="none">
      <circle cx="8.5" cy="8.5" r="6.8" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="8.5" cy="8.5" r="3.6" stroke="currentColor" strokeWidth="1.1" opacity="0.6" />
      <circle cx="8.5" cy="8.5" r="1.1" fill="currentColor" />
      <path d="M8.5 8.5 13 4.2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}