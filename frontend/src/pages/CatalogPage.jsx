// frontend/src/pages/CatalogPage.jsx
import { useEffect, useState, useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import Sidebar from '../components/Layout/Sidebar';
import Topbar from '../components/Layout/Topbar';
import { getProductsAnalytics } from '../services/api';
import './CatalogPage.css';

export default function CatalogPage() {
  const [productsData, setProductsData] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState('Toutes');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    getProductsAnalytics()
      .then((data) => {
        if (!isMounted) return;
        setProductsData(Array.isArray(data) ? data : []);
        setError(null);
      })
      .catch((err) => isMounted && setError(err.message))
      .finally(() => isMounted && setLoading(false));
    return () => { isMounted = false; };
  }, []);

  const categoryOptions = useMemo(
    () => [...new Set(productsData.map((p) => p.category_name).filter(Boolean))].sort(),
    [productsData]
  );

  const filteredProducts = productsData.filter(
    (item) => selectedCategory === 'Toutes' || item.category_name === selectedCategory
  );

  const chartData = filteredProducts.slice(0, 8).map((p) => ({ category: p.category_name, margin: p.margin || 0 }));

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <Topbar title="Analytics produits & catégories" subtitle="Performance réelle par catégorie : volume, marge, logistique et satisfaction." />

        <div className="catalog-toolbar">
          <select value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)} className="topbar-select">
            <option value="Toutes">Toutes les catégories ({productsData.length})</option>
            {categoryOptions.map((cat) => <option key={cat} value={cat}>{cat}</option>)}
          </select>
        </div>

        {error && <div className="banner banner-danger">{error}</div>}

        <div className="charts-row" style={{ marginBottom: 18 }}>
          <div className="card" style={{ padding: 20, gridColumn: '1 / -1' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 }}>
              <h3>Marge moyenne par catégorie</h3><span className="eyebrow">R$ / commande</span>
            </div>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chartData}>
                <XAxis dataKey="category" tick={{ fontSize: 10, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} interval={0} angle={-20} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 11, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }} formatter={(v) => [`${v} R$`, 'Marge moyenne']} />
                <Bar dataKey="margin" radius={[6, 6, 0, 0]}>
                  {chartData.map((_, i) => <Cell key={i} fill="var(--brand)" />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <section className="card" style={{ padding: 20 }}>
          <h3 style={{ marginBottom: 14 }}>Performance de l'offre produit</h3>
          {loading && <p style={{ color: 'var(--text-low)', fontSize: 14 }}>Chargement...</p>}
          {!loading && !error && (
            <table className="data-table">
              <thead>
                <tr><th>Catégorie</th><th>Volume vendu</th><th>Marge moyenne</th><th>Ratio fret/prix</th><th>Retard moyen</th><th>Avis négatifs</th></tr>
              </thead>
              <tbody>
                {filteredProducts.length > 0 ? (
                  filteredProducts.map((item, index) => (
                    <tr key={index}>
                      <td style={{ fontWeight: 600, color: 'var(--text-high)' }}>{item.category_name}</td>
                      <td className="num">{item.volume ?? 0} unités</td>
                      <td className="num" style={{ color: 'var(--positive)', fontWeight: 600 }}>+{item.margin ?? 0} R$</td>
                      <td className="num">{item.freight_ratio ?? 0}%</td>
                      <td className="num">{item.avg_delay_days != null ? `${item.avg_delay_days} j` : '—'}</td>
                      <td className="num" style={{ color: 'var(--danger)', fontWeight: 600 }}>{item.bad_reviews_pct ?? 0}%</td>
                    </tr>
                  ))
                ) : (
                  <tr><td colSpan={6} className="data-table-empty">Aucune donnée pour cette catégorie.</td></tr>
                )}
              </tbody>
            </table>
          )}
        </section>
      </main>
    </div>
  );
}