// frontend/src/pages/CustomersPage.jsx
import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import Sidebar from '../components/Layout/Sidebar';
import Topbar from '../components/Layout/Topbar';
import ChatWidget from '../components/Chatbot/ChatWidget';
import ChartExplainer from '../components/Common/ChartExplainer';
import { getCustomerStates, getCustomerSegmentsSummary } from '../services/api';
import './CustomersPage.css';

const SEGMENT_ACCENT = {
  'Champions (fidèles)': 'positive',
  'Gros acheteurs one-shot': 'brand',
  'Nouveaux / petits paniers': 'brand',
  'Dormants / à réactiver': 'warning',
};

export default function CustomersPage() {
  const [states, setStates] = useState([]);
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    Promise.all([getCustomerStates(), getCustomerSegmentsSummary()])
      .then(([statesData, segmentsData]) => {
        if (!isMounted) return;
        setStates(statesData);
        setSegments(segmentsData);
        setError(null);
      })
      .catch((err) => isMounted && setError(err.message))
      .finally(() => isMounted && setLoading(false));
    return () => { isMounted = false; };
  }, []);

  const pageContext = segments.length > 0 ? {
    chart_title: 'Intelligence clients & géographie',
    page: 'Clients',
    filters: {},
    data: {
      segments_clients: segments,
      repartition_geographique_top10_etats: states,
    },
  } : null;

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <Topbar title="Intelligence clients & géographie" subtitle="Segmentation comportementale (RFM/KMeans) et répartition géographique." />

        {error && <div className="banner banner-danger">{error}</div>}
        {loading && <p style={{ color: 'var(--text-low)', fontSize: 13, marginBottom: 14 }}>Chargement...</p>}

        <div className="page-grid">
          <div className="page-main-col">
            <section style={{ marginBottom: 24 }}>
              <h3 style={{ marginBottom: 4 }}>Segments clients</h3>
              <p style={{ color: 'var(--text-low)', fontSize: 13, marginBottom: 16 }}>
                Basé sur la récence, la fréquence et le montant des achats.
              </p>
              
              <div className="segment-cards">
                {segments.map((seg) => (
                  <div key={seg.segment_name} className="segment-card card">
                    <span className="eyebrow" style={{ color: `var(--${SEGMENT_ACCENT[seg.segment_name] || 'brand'})` }}>
                      {seg.pct}% des clients
                    </span>
                    <h3 style={{ margin: '6px 0 10px' }}>{seg.segment_name}</h3>
                    <div className="segment-stats">
                      <div><span className="num">{seg.n_customers.toLocaleString('fr-FR')}</span><small>clients</small></div>
                      <div><span className="num">{Math.round(seg.avg_recency_days)}j</span><small>récence moy.</small></div>
                      <div><span className="num">{seg.avg_monetary} R$</span><small>panier moy.</small></div>
                    </div>
                  </div>
                ))}
              </div>

              <ChartExplainer>
                4 groupes de clients aux comportements similaires (méthode K-Means sur récence/fréquence/montant). "Champions" = clients fidèles à choyer, "Dormants" = clients à réactiver (relance ciblée), "Gros acheteurs one-shot" = fort potentiel de fidélisation, "Nouveaux/petits paniers" = à faire monter en gamme.
              </ChartExplainer>
            </section>

            <section className="card" style={{ padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
                <h3>Répartition géographique des clients</h3>
                <span className="eyebrow">Top 10 états</span>
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={states} layout="vertical" margin={{ left: 4 }}>
                  <XAxis type="number" tick={{ fontSize: 10.5, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} unit="%" />
                  <YAxis dataKey="state" type="category" width={42} tick={{ fontSize: 11, fill: 'var(--text-mid)' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }} formatter={(v, name, props) => [`${v}% (${props.payload.total_customers.toLocaleString('fr-FR')} clients)`, 'Part des clients']} />
                  <Bar dataKey="percentage" radius={[0, 6, 6, 0]} barSize={16} fill="var(--brand)" />
                </BarChart>
              </ResponsiveContainer>
              <ChartExplainer>
                Où sont les clients concentrés.
              </ChartExplainer>
            </section>
          </div>

          <aside className="card assistant-panel">
            <div className="assistant-panel-header">
              <span className="assistant-avatar avatar-float">🤖</span>
              <div>
                <h3>Agent RAG clients</h3>
                <p>Satisfaction, réclamations et avis, en langage naturel.</p>
              </div>
            </div>
            <ChatWidget pageContext={pageContext} />
          </aside>
        </div>
      </main>
    </div>
  );
}