// frontend/src/components/Common/ChartExplainer.jsx
// Petit bloc d'explication a placer sous un graphique/KPI : objectif,
// utilite, comment le lire. Style en ligne pour ne dependre d'aucun
// fichier CSS externe (s'utilise partout sans configuration).
export default function ChartExplainer({ children }) {
  return (
    <p
      style={{
        fontSize: 12,
        color: 'var(--text-low, #6b7280)',
        marginTop: 8,
        lineHeight: 1.5,
        display: 'flex',
        gap: 6,
        alignItems: 'flex-start',
      }}
    >
      <span aria-hidden="true">💡</span>
      <span>{children}</span>
    </p>
  );
}