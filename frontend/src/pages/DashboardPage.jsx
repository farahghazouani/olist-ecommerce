// frontend/src/pages/DashboardPage.jsx
import { useState, useEffect } from 'react';
import Sidebar from '../components/Layout/Sidebar';
import Topbar from '../components/Layout/Topbar';
import KpiCard from '../components/Dashboard/KpiCard';
import RevenueChart from '../components/Dashboard/RevenueChart';
import TopCategoriesChart from '../components/Dashboard/TopCategoriesChart';
import ChatWidget from '../components/Chatbot/ChatWidget';
import ChartExplainer from '../components/Common/ChartExplainer';
import {
  getDashboardMetrics, getRiskOrders, getRevenueByMonth, getTopCategories, getCustomerStates,
} from '../services/api';
import './DashboardPage.css';

export default function DashboardPage() {
  const [metrics, setMetrics] = useState(null);
  const [riskOrders, setRiskOrders] = useState([]);
  const [revenueByMonth, setRevenueByMonth] = useState([]);
  const [topCategories, setTopCategories] = useState([]);
  const [states, setStates] = useState([]);
  const [selectedRegion, setSelectedRegion] = useState('');
  const [selectedDate, setSelectedDate] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const handleRegionChange = (value) => { setLoading(true); setSelectedRegion(value); };
  const handleDateChange = (value) => { setLoading(true); setSelectedDate(value); };

  useEffect(() => {
    Promise.all([getRevenueByMonth(), getTopCategories(5), getCustomerStates()])
      .then(([revenue, categories, statesData]) => {
        setRevenueByMonth(revenue);
        setTopCategories(categories.map((c) => ({ category: c.category, revenue: c.revenue })));
        setStates(statesData);
      })
      .catch((err) => console.error('Erreur chargement donnees globales :', err));
  }, []);

  useEffect(() => {
    let isMounted = true;
    const params = {};
    if (selectedRegion) params.region = selectedRegion;
    if (selectedDate) params.date = selectedDate;

    Promise.all([getDashboardMetrics(params), getRiskOrders({ ...params, limit: 50 })])
      .then(([metricsData, riskData]) => {
        if (!isMounted) return;
        setMetrics(metricsData);
        setRiskOrders(Array.isArray(riskData) ? riskData : []);
        setError(null);
      })
      .catch((err) => {
        if (!isMounted) return;
        console.error('Erreur de connexion a l\'API :', err);
        setError("Impossible de récupérer les données depuis l'API. Vérifiez que le serveur backend est actif.");
      })
      .finally(() => isMounted && setLoading(false));

    return () => { isMounted = false; };
  }, [selectedRegion, selectedDate]);

  const pageContext = metrics ? {
    chart_title: 'Tableau de bord exécutif',
    page: 'Dashboard',
    filters: { region: selectedRegion || null, date: selectedDate || null },
    data: {
      volume_affaires_gmv: metrics.totalGmv,
      tendance_gmv: metrics.gmvTrend,
      taux_livraison_a_temps_pct: metrics.onTimeRate,
      tendance_livraison: metrics.onTimeTrend,
      satisfaction_csat: metrics.avgCsat,
      ratio_fret_prix_pct: metrics.freightRatio,
      nombre_commandes_a_risque: riskOrders.length,
      top_categories: topCategories,
      ca_par_mois: revenueByMonth,
    },
  } : null;

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <Topbar
          title="Tableau de bord exécutif"
          subtitle="Synthèse stratégique de la performance commerciale, logistique et de la satisfaction client."
          states={states}
          selectedRegion={selectedRegion}
          onRegionChange={handleRegionChange}
          selectedDate={selectedDate}
          onDateChange={handleDateChange}
        />

        {error && <div className="banner banner-danger">{error}</div>}

        <div className="dashboard-grid">
          <div className="dashboard-main-col">
            
            {/* Disposition 2x2 des KPI */}
            <section className="kpi-row">
              <KpiCard label="Volume d'affaires (GMV)" value={metrics ? `${Number(metrics.totalGmv).toLocaleString('pt-BR')} R$` : '—'} trend={metrics?.gmvTrend} accent="brand" loading={loading} />
              <KpiCard label="Livraison à temps" value={metrics ? `${metrics.onTimeRate}%` : '—'} trend={metrics?.onTimeTrend} accent={metrics && metrics.onTimeRate >= 90 ? 'positive' : 'warning'} loading={loading} />
              <KpiCard label="Satisfaction (CSAT)" value={metrics?.avgCsat ? `${metrics.avgCsat} / 5.0` : '—'} trend="Moyenne des avis" accent="brand" loading={loading} />
              <KpiCard label="Ratio fret / prix" value={metrics ? `${metrics.freightRatio}%` : '—'} trend="Coût logistique moyen" accent="brand" loading={loading} />
            </section>

            <ChartExplainer>
              Ces 4 indicateurs résument la performance globale de l'activité sur la période de 2016 à 2018. Le GMV mesure le volume d'affaires total, le taux de livraison à temps et le CSAT évaluent la qualité de service, et le ratio fret/prix traduit l'impact des coûts logistiques.
            </ChartExplainer>

            {/* Visualisations côte à côte */}
            <section className="charts-row">
              <RevenueChart data={revenueByMonth} />
              <TopCategoriesChart data={topCategories} />
            </section>

            {/* Section repliable : Commandes à risque */}
            <details className="card risk-table-card risk-table-collapsible">
              <summary className="risk-table-summary">
                <h3 style={{ color: 'var(--danger)', display: 'inline' }}>
                  Commandes à risque (livraisons en retard enregistrées)
                </h3>
                <span className="eyebrow">{riskOrders.length} commandes — cliquer pour afficher</span>
              </summary>
              
              <div className="risk-table-container">
                <table className="risk-table">
                  <thead>
                    <tr>
                      <th>État client</th>
                      <th>Catégorie</th>
                      <th className="num">Prix</th>
                      <th className="num">Frais de port</th>
                      <th className="num">Retard</th>
                      <th className="num">CSAT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr><td colSpan={6} className="risk-table-empty">Chargement...</td></tr>
                    ) : riskOrders.length > 0 ? (
                      riskOrders.map((order, idx) => (
                        <tr key={order.order_id || idx}>
                          <td>{order.customer_state || '—'}</td>
                          <td>{order.product_category_name || '—'}</td>
                          <td className="num">{order.price != null ? `${Number(order.price).toFixed(2)} R$` : '—'}</td>
                          <td className="num">{order.freight_value != null ? `${Number(order.freight_value).toFixed(2)} R$` : '—'}</td>
                          <td className="num risk-delay">{order.delay_days != null ? `+${Math.round(order.delay_days)} j` : '—'}</td>
                          <td className="num">{order.review_score != null ? `★ ${order.review_score}` : '—'}</td>
                        </tr>
                      ))
                    ) : (
                      <tr><td colSpan={6} className="risk-table-empty">Aucune commande en retard pour ces filtres.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>

              <ChartExplainer>
                Liste des commandes déjà livrées en retard. Le CSAT (Customer Satisfaction Score) mesure le niveau de satisfaction évalué par le client sur une échelle de 1 à 5.
              </ChartExplainer>
            </details>
          </div>

          <aside className="card assistant-panel">
            <div className="assistant-panel-header">
              <span className="assistant-avatar avatar-float">🤖</span>
              <div>
                <h3>Assistant BI</h3>
                <p style={{ fontSize: 12, color: 'var(--text-low)', marginBottom: 10 }}>
                  Pour estimer le risque d'une future commande, utilisez le simulateur en page Prévisions ML.
                </p>
                <p>Questions en langage naturel sur vos données et avis clients.</p>
              </div>
            </div>
            <ChatWidget pageContext={pageContext} />
          </aside>
        </div>
      </main>
    </div>
  );
}