// frontend/src/components/Layout/Topbar.jsx
import './Topbar.css';

export default function Topbar({
  title, subtitle, states = [],
  selectedRegion, onRegionChange,
  selectedDate, onDateChange,
}) {
  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="topbar-subtitle">{subtitle}</p>}
      </div>

      {(onRegionChange || onDateChange) && (
        <div className="topbar-filters">
          {onRegionChange && (
            <select className="topbar-select" value={selectedRegion} onChange={(e) => onRegionChange(e.target.value)}>
              <option value="">Tous les états</option>
              {states.map((s) => (
                <option key={s.state} value={s.state}>
                  {s.state} · {s.total_customers.toLocaleString('fr-FR')} clients
                </option>
              ))}
            </select>
          )}
          {onDateChange && (
            <input type="date" className="topbar-select" value={selectedDate} onChange={(e) => onDateChange(e.target.value)} />
          )}
        </div>
      )}
    </header>
  );
}