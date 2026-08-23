// frontend/src/pages/SalesPage.jsx
import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import Sidebar from '../components/Layout/Sidebar';
import Topbar from '../components/Layout/Topbar';
import KpiCard from '../components/Dashboard/KpiCard';
import ChatWidget from '../components/Chatbot/ChatWidget';
import ChartExplainer from '../components/Common/ChartExplainer';
import {
  getSalesMetrics, getRevenueByState, getTopSellers,
  getBestSellerBySeason, getTopReviews,
} from '../services/api';
import './SalesPage.css';

const SHADES = ['var(--brand)', 'var(--brand-strong)', '#7fa0ff', '#a4bcff', '#c7d6ff'];

const SEASON_COLOR = {
  'Été': '#f0a93b',
  'Automne': '#c2703d',
  'Hiver': '#3457d5',
  'Printemps': '#0f9d6c',
};
const SEASON_ICON = { 'Été': '☀️', 'Automne': '🍂', 'Hiver': '❄️', 'Printemps': '🌸' };

export default function SalesPage() {
  const [metrics, setMetrics] = useState(null);
  const [revenueByState, setRevenueByState] = useState([]);
  const [topSellers, setTopSellers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [bestSellers, setBestSellers] = useState([]);
  const [selectedLabel, setSelectedLabel] = useState('');
  const [positiveReviews, setPositiveReviews] = useState([]);
  const [reviewsLoading, setReviewsLoading] = useState(false);

  useEffect(() => {
    let isMounted = true;
    Promise.all([getSalesMetrics(), getRevenueByState(), getTopSellers(8), getBestSellerBySeason()])
      .then(([m, states, sellers, seasons]) => {
        if (!isMounted) return;
        setMetrics(m);
        setRevenueByState(states);
        setTopSellers(sellers);
        setBestSellers(seasons);
        if (seasons.length > 0) {
          setReviewsLoading(true);
          setSelectedLabel(seasons[seasons.length - 1].label);
        }
        setError(null);
      })
      .catch((err) => isMounted && setError(err.message))
      .finally(() => isMounted && setLoading(false));
    return () => { isMounted = false; };
  }, []);

  const handleSeasonChange = (label) => {
    setReviewsLoading(true);
    setSelectedLabel(label);
  };

  const selectedSeason = bestSellers.find((s) => s.label === selectedLabel) || null;

  useEffect(() => {
    if (!selectedSeason) return;
    let isMounted = true;
    getTopReviews(selectedSeason.category, 3)
      .then((data) => isMounted && setPositiveReviews(data))
      .catch(() => isMounted && setPositiveReviews([]))
      .finally(() => isMounted && setReviewsLoading(false));
    return () => { isMounted = false; };
  }, [selectedLabel]); // eslint-disable-line react-hooks/exhaustive-deps

  const pageContext = metrics ? {
    chart_title: 'Analyse stratégique des ventes',
    page: 'Ventes',
    filters: { saison_selectionnee: selectedLabel || null },
    data: {
      marge_estimee_totale: metrics.totalMargin,
      ratio_frais_port_pct: metrics.freightRatio,
      ratio_vente_meme_etat_pct: metrics.sameStateRatio,
      ca_par_etat: revenueByState,
      top_vendeurs: topSellers,
      meilleure_categorie_par_saison: bestSellers,
      saison_selectionnee_detail: selectedSeason,
    },
  } : null;

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <Topbar title="Analyse stratégique des ventes" />
        {error && <div className="banner banner-danger">{error}</div>}

        <div className="page-grid">
          <div className="page-main-col">
            <section className="kpi-row">
              <KpiCard label="Marge estimée totale" value={metrics ? `${Number(metrics.totalMargin).toLocaleString('fr-FR')} R$` : '—'} trend="Cumul sur la période stable" accent="positive" loading={loading} />
              <KpiCard label="Ratio frais de port / prix" value={metrics ? `${metrics.freightRatio}%` : '—'} trend="Coût logistique moyen" accent="brand" loading={loading} />
              <KpiCard label="Ventes même état (local)" value={metrics ? `${metrics.sameStateRatio}%` : '—'} trend="Vendeur et client dans le même état" accent="brand" loading={loading} />
            </section>
            <ChartExplainer>
              Ces indicateursmesurent la rentabilité générée par les ventes, le poids des coûts logistiques dans le chiffre d'affaires ainsi que la proximité géographique entre vendeurs et clients, un facteur pouvant influencer les délais et les coûts de livraison.
            </ChartExplainer>

            <section className="card season-explorer">
              <div className="season-explorer-header">
                <h3>Best-seller par saison</h3>
                <span className="eyebrow">Clique une barre pour explorer</span>
              </div>

              <ResponsiveContainer width="100%" height={190}>
                <BarChart data={bestSellers} margin={{ top: 8 }}>
                  <XAxis dataKey="label" tick={{ fontSize: 10.5, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} interval={0} angle={-25} textAnchor="end" height={44} />
                  <YAxis tick={{ fontSize: 10.5, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} width={70} />
                  <Tooltip
                    cursor={{ fill: 'var(--surface-hover)' }}
                    contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                    formatter={(v, name, props) => [`${Number(v).toLocaleString('fr-FR')} R$`, props.payload.category]}
                  />
                  <Bar dataKey="revenue" radius={[6, 6, 0, 0]} onClick={(data) => handleSeasonChange(data.label)} cursor="pointer">
                    {bestSellers.map((s) => (
                      <Cell
                        key={s.label}
                        fill={SEASON_COLOR[s.season] || 'var(--brand)'}
                        opacity={s.label === selectedLabel ? 1 : 0.45}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>

              {selectedSeason && (
                <div className="season-result">
                  <div className="season-result-main">
                    <span className="season-icon">{SEASON_ICON[selectedSeason.season] || '📦'}</span>
                    <div>
                      <span className="eyebrow">{selectedSeason.label} — meilleure catégorie</span>
                      <div className="season-category-badge">{selectedSeason.category}</div>
                      <p className="season-result-sub">
                        <span className="num">{selectedSeason.revenue.toLocaleString('fr-FR')} R$</span> de CA sur cette période
                      </p>
                    </div>
                  </div>
                  <div className="season-reviews">
                    <span className="eyebrow" style={{ color: 'var(--positive)' }}>
                      Pourquoi ça plaît — avis originaux (PT-BR)
                    </span>
                    {reviewsLoading ? (
                      <p className="season-reviews-empty">Chargement...</p>
                    ) : positiveReviews.length > 0 ? (
                      <ul className="season-reviews-list">
                        {positiveReviews.map((rev, i) => <li key={i}>"{rev}"</li>)}
                      </ul>
                    ) : (
                      <p className="season-reviews-empty">Aucun avis positif trouvé pour cette catégorie.</p>
                    )}
                  </div>
                </div>
              )}
              <ChartExplainer>
                Meilleure catégorie par saison. Cliquez sur une barre pour consulter les avis clients correspondants.
              </ChartExplainer>
            </section>

            <section className="card" style={{ padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
                <h3>CA par état client</h3><span className="eyebrow">Top 10</span>
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={revenueByState} layout="vertical" margin={{ left: 4 }}>
                  <XAxis type="number" tick={{ fontSize: 10.5, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} />
                  <YAxis dataKey="state" type="category" width={42} tick={{ fontSize: 11, fill: 'var(--text-mid)' }} axisLine={false} tickLine={false} interval={0} />
                  <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }} formatter={(v) => `${Number(v).toLocaleString('fr-FR')} R$`} />
                  <Bar dataKey="revenue" radius={[0, 6, 6, 0]} barSize={18}>
                    {revenueByState.map((_, i) => <Cell key={i} fill={SHADES[i % SHADES.length]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <ChartExplainer>
                Répartition du chiffre d'affaires par état client.
              </ChartExplainer>
            </section>
          </div>

          <aside className="card assistant-panel">
            <div className="assistant-panel-header">
              <span className="assistant-avatar avatar-float">🤖</span>
              <div><h3>Assistant BI</h3><p>Questions sur les ventes, marges et vendeurs.</p></div>
            </div>
            <ChatWidget pageContext={pageContext} />
          </aside>
        </div>
      </main>
    </div>
  );
}