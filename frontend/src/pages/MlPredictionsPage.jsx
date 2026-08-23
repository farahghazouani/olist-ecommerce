// frontend/src/pages/MlPredictionsPage.jsx
import { useEffect, useState } from 'react';
import Sidebar from '../components/Layout/Sidebar';
import Topbar from '../components/Layout/Topbar';
import {
  getForecastCategories, getForecastByCategory,
  getDelayRisk, getCustomerStates, getProductsAnalytics, predictSegment,
} from '../services/api';
import './MlPredictionsPage.css';

const MONTHS = [
  'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
];

const RISK_ACCENT = { Faible: 'positive', Modéré: 'warning', Élevé: 'danger' };

export default function MlPredictionsPage() {
  const [categories, setCategories] = useState([]);
  const [states, setStates] = useState([]);
  const [productCategories, setProductCategories] = useState([]);
  const [fcCategory, setFcCategory] = useState('');
  const [fcState, setFcState] = useState('');
  const [fcResult, setFcResult] = useState(null);
  const [fcLoading, setFcLoading] = useState(false);
  const [fcError, setFcError] = useState(null);

  const [segForm, setSegForm] = useState({ recency_days: 60, frequency: 1, monetary: 150 });
  const [segResult, setSegResult] = useState(null);
  const [segLoading, setSegLoading] = useState(false);
  const [segError, setSegError] = useState(null);

  const [delayForm, setDelayForm] = useState({
    category: '', customer_state: '', order_month: new Date().getMonth() + 1,
    total_price: 150, total_freight: 20, n_items: 1, n_unique_products: 1,
    n_unique_sellers: 1, pct_same_state: 0.5, avg_product_weight_g: 800,
    max_product_weight_g: 800, n_payment_installments_max: 3, has_voucher: 0,
  });
  const [delayResult, setDelayResult] = useState(null);
  const [delayLoading, setDelayLoading] = useState(false);
  const [delayError, setDelayError] = useState(null);

  useEffect(() => {
    getForecastCategories().then((cats) => {
      setCategories(cats);
      setFcCategory(cats[0] || '');
    }).catch(() => {});
    getCustomerStates().then(setStates).catch(() => {});
    getProductsAnalytics().then((rows) => {
      const cats = [...new Set(rows.map((r) => r.category_name).filter(Boolean))].sort();
      setProductCategories(cats);
      setDelayForm((f) => ({ ...f, category: cats[0] || '', customer_state: '' }));
    }).catch(() => {});
  }, []);

  const runForecast = () => {
    if (!fcCategory) return;
    setFcLoading(true);
    setFcError(null);
    getForecastByCategory(fcCategory, fcState || undefined)
      .then(setFcResult)
      .catch((err) => setFcError(err.response?.data?.detail || err.message))
      .finally(() => setFcLoading(false));
  };

  const runDelayRisk = () => {
    setDelayLoading(true);
    setDelayError(null);
    getDelayRisk(delayForm)
      .then(setDelayResult)
      .catch((err) => setDelayError(err.response?.data?.detail || err.message))
      .finally(() => setDelayLoading(false));
  };

  const updateDelayField = (key, value) => setDelayForm((f) => ({ ...f, [key]: value }));

  const runSegmentation = () => {
    setSegLoading(true);
    setSegError(null);
    predictSegment(segForm)
      .then(setSegResult)
      .catch((err) => setSegError(err.response?.data?.detail || err.message))
      .finally(() => setSegLoading(false));
  };

  const updateSegField = (key, value) => setSegForm((f) => ({ ...f, [key]: value }));

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <Topbar title="Prévisions & intelligence artificielle" subtitle="Modèles entraînés sur l'historique Olist — choisissez vos critères pour obtenir une prédiction." />

        <div className="ml-grid">
          <section className="card ml-card">
            <div className="ml-card-header">
              <span className="eyebrow">Modèle 1 — Régression</span>
              <h3>Prévision de CA par catégorie & région</h3>
              <p>Approche top-down : croissance prévue de la catégorie × répartition historique par état.</p>
            </div>

            <div className="ml-form-row">
              <label>
                Catégorie
                <select value={fcCategory} onChange={(e) => setFcCategory(e.target.value)}>
                  {categories.length === 0 && <option value="">Chargement...</option>}
                  {categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label>
                État (optionnel)
                <select value={fcState} onChange={(e) => setFcState(e.target.value)}>
                  <option value="">Toutes régions</option>
                  {states.map((s) => <option key={s.state} value={s.state}>{s.state}</option>)}
                </select>
              </label>
              <button className="ml-btn" onClick={runForecast} disabled={fcLoading}>
                {fcLoading ? 'Calcul...' : 'Prédire'}
              </button>
            </div>

            {fcError && <div className="banner banner-danger">{fcError}</div>}

            {fcResult && (
              <div className="ml-result">
                <div className="ml-result-main">
                  <span className="eyebrow">CA prévu — {fcResult.forecast_month}</span>
                  <div className="ml-result-value num">{fcResult.predicted_revenue_total.toLocaleString('fr-FR')} R$</div>
                  {fcResult.state && (
                    <p className="ml-result-sub">
                      dont <strong>{fcResult.predicted_revenue_state.toLocaleString('fr-FR')} R$</strong> pour {fcResult.state}
                      {' '}(part historique : {(fcResult.state_share * 100).toFixed(1)}%)
                    </p>
                  )}
                </div>
                <div className="ml-confidence">
                  <span className="eyebrow">Confiance</span>
                  <p>Ratio de croissance prédit : <span className="num">{fcResult.growth_ratio}</span>× le dernier CA connu ({fcResult.last_known_month}).</p>
                  <p className="ml-confidence-note">
                    Marge d'erreur historique mesurée en validation : ≈ ±49% (MAPE). Une estimation, pas une garantie —
                    utile pour arbitrer entre catégories, pas comme chiffre contractuel.
                  </p>
                </div>
              </div>
            )}
          </section>

          <section className="card ml-card">
            <div className="ml-card-header">
              <span className="eyebrow">Modèle 2 — Classification</span>
              <h3>Risque de retard de livraison</h3>
              <p>Probabilité de retard avant expédition, avec les facteurs qui l'expliquent.</p>
            </div>

            <div className="ml-form-grid">
              <label>
                Catégorie
                <select value={delayForm.category} onChange={(e) => updateDelayField('category', e.target.value)}>
                  {productCategories.length === 0 && <option value="">Chargement...</option>}
                  {productCategories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label>
                État client
                <select value={delayForm.customer_state} onChange={(e) => updateDelayField('customer_state', e.target.value)}>
                  <option value="">—</option>
                  {states.map((s) => <option key={s.state} value={s.state}>{s.state}</option>)}
                </select>
              </label>
              <label>
                Mois de commande
                <select value={delayForm.order_month} onChange={(e) => updateDelayField('order_month', Number(e.target.value))}>
                  {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </select>
              </label>
              <label>Prix (R$)<input type="number" value={delayForm.total_price} onChange={(e) => updateDelayField('total_price', Number(e.target.value))} /></label>
              <label>Frais de port (R$)<input type="number" value={delayForm.total_freight} onChange={(e) => updateDelayField('total_freight', Number(e.target.value))} /></label>
              <label>Poids moyen produit (g)<input type="number" value={delayForm.avg_product_weight_g} onChange={(e) => updateDelayField('avg_product_weight_g', Number(e.target.value))} /></label>
              <label>Nb items<input type="number" value={delayForm.n_items} onChange={(e) => updateDelayField('n_items', Number(e.target.value))} /></label>
              <label>Nb vendeurs uniques<input type="number" value={delayForm.n_unique_sellers} onChange={(e) => updateDelayField('n_unique_sellers', Number(e.target.value))} /></label>
              <label className="ml-checkbox">
                <input type="checkbox" checked={delayForm.has_voucher === 1} onChange={(e) => updateDelayField('has_voucher', e.target.checked ? 1 : 0)} />
                Bon de réduction utilisé
              </label>
            </div>

            <button className="ml-btn" onClick={runDelayRisk} disabled={delayLoading}>
              {delayLoading ? 'Calcul...' : 'Estimer le risque'}
            </button>

            {delayError && <div className="banner banner-danger">{delayError}</div>}

            {delayResult && (
              <div className="ml-result">
                <div className={`risk-badge accent-${RISK_ACCENT[delayResult.risk_level] || 'brand'}`}>
                  <span className="eyebrow">Risque {delayResult.risk_level}</span>
                  <div className="ml-result-value num">{(delayResult.risk_probability * 100).toFixed(1)}%</div>
                  <p className="ml-result-sub">de probabilité de retard</p>
                </div>
                <div className="ml-confidence">
                  <span className="eyebrow">Facteurs principaux</span>
                  <ul className="ml-factors">
                    {delayResult.top_factors.map((f) => <li key={f}>{f}</li>)}
                  </ul>
                </div>
              </div>
            )}
          </section>

          <section className="card ml-card">
            <div className="ml-card-header">
              <span className="eyebrow">Modèle 3 — Segmentation (K-Means)</span>
              <h3>Segment client en direct</h3>
              <p>Simule le segment marketing d'un profil client (récence, fréquence, montant) — même modèle que la segmentation globale.</p>
            </div>

            <div className="ml-form-row">
              <label>
                Récence (jours depuis le dernier achat)
                <input type="number" value={segForm.recency_days} onChange={(e) => updateSegField('recency_days', Number(e.target.value))} />
              </label>
              <label>
                Fréquence (nb d'achats)
                <input type="number" value={segForm.frequency} onChange={(e) => updateSegField('frequency', Number(e.target.value))} />
              </label>
              <label>
                Montant total dépensé (R$)
                <input type="number" value={segForm.monetary} onChange={(e) => updateSegField('monetary', Number(e.target.value))} />
              </label>
              <button className="ml-btn" onClick={runSegmentation} disabled={segLoading}>
                {segLoading ? 'Calcul...' : 'Prédire le segment'}
              </button>
            </div>

            {segError && <div className="banner banner-danger">{segError}</div>}

            {segResult && (
              <div className="ml-result">
                <div className="ml-result-main">
                  <span className="eyebrow">Segment prédit</span>
                  <div className="ml-result-value num">{segResult.segment_name}</div>
                  {!segResult.segment_name_is_mapped && (
                    <p className="ml-confidence-note">
                      Nom générique (cluster {segResult.cluster_id}) — la correspondance nom/segment n'a pas pu être retrouvée dans customer_segments.csv.
                    </p>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}