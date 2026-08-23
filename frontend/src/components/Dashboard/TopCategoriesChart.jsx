// frontend/src/components/Dashboard/TopCategoriesChart.jsx
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const SHADES = ['var(--brand)', 'var(--brand-strong)', '#7fa0ff', '#a4bcff', '#c7d6ff'];

function truncate(label, max = 16) {
  if (!label) return '';
  return label.length > max ? `${label.slice(0, max - 1)}…` : label;
}

function CategoryTick({ x, y, payload }) {
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fontSize={10.5} fill="var(--text-mid)">
      {truncate(payload.value)}
    </text>
  );
}

export default function TopCategoriesChart({ data }) {
  return (
    <div className="card" style={{ padding: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '14px' }}>
        <h3>Top catégories par CA</h3>
        <span className="eyebrow">Top {data?.length || 0}</span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} layout="vertical" margin={{ left: 4, right: 16 }}>
          <XAxis type="number" tick={{ fontSize: 10.5, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} />
          <YAxis dataKey="category" type="category" width={128} tick={<CategoryTick />} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, color: 'var(--text-high)' }}
            labelFormatter={(label) => label}
            formatter={(v) => `${Number(v).toLocaleString('fr-FR', { minimumFractionDigits: 2 })} R$`}
          />
          <Bar dataKey="revenue" radius={[0, 6, 6, 0]} barSize={18}>
            {(data || []).map((_, i) => <Cell key={i} fill={SHADES[i % SHADES.length]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}