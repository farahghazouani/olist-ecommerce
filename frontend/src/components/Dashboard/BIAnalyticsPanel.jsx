export default function BIAnalyticsPanel() {
  const paymentMethods = [
    { name: 'Carte de crédit', pct: 73.9, color: '#6366f1' },
    { name: 'Boleto', pct: 19.0, color: '#f59e0b' },
    { name: 'Voucher', pct: 5.6, color: '#10b981' },
    { name: 'Débit', pct: 1.5, color: '#ef4444' },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px', marginTop: '20px' }}>
      {/* Répartition des paiements */}
      <div style={{ background: '#fff', padding: '20px', borderRadius: '14px', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: '16px', color: '#111827' }}>💳 Moyens de paiement</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {paymentMethods.map((pm) => (
            <div key={pm.name}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '4px' }}>
                <span style={{ fontWeight: 500 }}>{pm.name}</span>
                <span style={{ color: '#6b7280' }}>{pm.pct}%</span>
              </div>
              <div style={{ background: '#f3f4f6', height: '8px', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ width: `${pm.pct}%`, background: pm.color, height: '100%', borderRadius: '4px' }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Impact Logistique vs Satisfaction */}
      <div style={{ background: '#fff', padding: '20px', borderRadius: '14px', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <h3 style={{ margin: '0 0 12px', fontSize: '16px', color: '#111827' }}>🚚 Impact Retard vs Satisfaction</h3>
        <div style={{ background: '#fef2f2', borderLeft: '4px solid #ef4444', padding: '12px 16px', borderRadius: '8px' }}>
          <p style={{ margin: 0, fontSize: '13px', color: '#991b1b', fontWeight: 600 }}>
            Corrélation Négative : -0.27
          </p>
          <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#7f1d1d' }}>
            Les retards de livraison sont le 1er facteur de baisse des notes d'évaluation.
          </p>
        </div>
        <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#6b7280' }}>
          <span>Marge moyenne / article : <strong>100.66 R$</strong></span>
          <span>Top État : <strong>SP (São Paulo)</strong></span>
        </div>
      </div>
    </div>
  );
}