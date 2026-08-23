// frontend/src/components/Dashboard/KpiCard.jsx
import './KpiCard.css';

export default function KpiCard({ label, value, trend, accent = 'brand', icon, loading = false }) {
  return (
    <div className={`kpi-card accent-${accent}`}>
      <div className="kpi-card-top">
        <span className="kpi-card-label">{label}</span>
        {icon && <span className="kpi-card-icon">{icon}</span>}
      </div>
      <div className="kpi-card-value num">{loading ? '—' : value}</div>
      {trend && <div className="kpi-card-trend">{loading ? ' ' : trend}</div>}
    </div>
  );
}