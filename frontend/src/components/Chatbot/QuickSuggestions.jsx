// frontend/src/components/Chatbot/QuickSuggestions.jsx
const SUGGESTIONS = [
  "Quel est le CA de la semaine dernière ?",
  "Montre-moi la prévision de ventes",
  "Quels sont les avis clients récents ?",
];

export default function QuickSuggestions({ onSelect }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '0 20px 12px' }}>
      {SUGGESTIONS.map((text, i) => (
        <button
          key={i}
          onClick={() => onSelect(text)}
          style={{
            textAlign: 'left',
            background: '#fff',
            border: '1px solid #e0e7ff',
            borderRadius: '10px',
            padding: '10px 14px',
            fontSize: '13px',
            color: '#4338ca',
            cursor: 'pointer',
            transition: 'background 0.15s',
          }}
          onMouseEnter={(e) => e.target.style.background = '#eef2ff'}
          onMouseLeave={(e) => e.target.style.background = '#fff'}
        >
          {text} <span style={{ float: 'right' }}>›</span>
        </button>
      ))}
    </div>
  );
}