// frontend/src/components/Dashboard/MlInsightsCard.jsx
export default function MlInsightsCard({ forecast, classification }) {
  const perfColor = {
    'Forte': '#22c55e',
    'Moyenne': '#f59e0b',
    'Faible': '#ef4444',
  }[classification?.predicted_performance] || '#6366f1';

  return (
    <div style={{ display: 'flex', gap: '16px' }}>
      <div style={{ flex: 1, background: 'linear-gradient(135deg, #eef2ff, #e0e7ff)', borderRadius: '14px', padding: '20px 24px' }}>
        <p style={{ margin: 0, fontSize: '13px', color: '#4338ca', fontWeight: 600 }}>🔮 PRÉVISION SEMAINE PROCHAINE</p>
        <p style={{ margin: '10px 0 0', fontSize: '24px', fontWeight: 700, color: '#111827' }}>
          {forecast?.predicted_next_week_revenue?.toLocaleString('fr-FR', { minimumFractionDigits: 2 })} R$
        </p>
        <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#6b7280' }}>
          Basé sur {forecast?.based_on_weeks} semaines de données
        </p>
      </div>

      <div style={{ flex: 1, background: '#fff', borderRadius: '14px', padding: '20px 24px', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <p style={{ margin: 0, fontSize: '13px', color: '#6b7280', fontWeight: 600 }}>📈 PERFORMANCE PRÉVUE</p>
        <p style={{ margin: '10px 0 0', fontSize: '24px', fontWeight: 700, color: perfColor }}>
          {classification?.predicted_performance}
        </p>
        <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#6b7280' }}>
          Confiance : {(classification?.confidence * 100).toFixed(1)}%
        </p>
      </div>
    </div>
  );
}