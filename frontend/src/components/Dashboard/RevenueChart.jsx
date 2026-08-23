// frontend/src/components/Dashboard/RevenueChart.jsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function RevenueChart({ data }) {
  return (
    <div className="card" style={{ padding: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '14px' }}>
        <h3>Evolution du chiffre d'affaires</h3>
        <span className="eyebrow">Mensuel</span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-low)' }} axisLine={{ stroke: 'var(--border)' }} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: 'var(--text-low)' }} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, color: 'var(--text-high)' }}
            formatter={(value) => [`${Number(value).toLocaleString('fr-FR', { minimumFractionDigits: 2 })} R$`, 'CA']}
          />
          <Line type="monotone" dataKey="revenue" stroke="var(--brand)" strokeWidth={2} dot={{ r: 3, fill: 'var(--brand)' }} activeDot={{ r: 5 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}