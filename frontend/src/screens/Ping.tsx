import { useState } from 'react';
import { Link } from 'react-router-dom';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function PingPage() {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/council`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setResult({ error: 'API indisponível. Tente novamente.' });
    }
    setLoading(false);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--canvas)' }}>
      {/* Nav */}
      <div style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: '1px solid var(--separator)' }}>
        <Link to="/" style={{ color: 'var(--accent)', fontSize: 17, textDecoration: 'none' }}>←</Link>
        <div style={{ fontWeight: 600, fontSize: 17 }}>Ping — Consulta rápida</div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 24 }}>
        <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: -0.4, marginBottom: 8 }}>Pergunte a um especialista</div>
        <div style={{ color: 'var(--label-2)', fontSize: 15, marginBottom: 20 }}>Seu conselho consultivo pessoal responde em segundos.</div>

        <form onSubmit={handleSubmit}>
          <textarea
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder='Ex: "Devo reajustar o pricing enterprise em 6%?"'
            style={{
              width: '100%', minHeight: 100, padding: 14,
              background: 'var(--surface)', borderRadius: 16, border: '1px solid var(--separator)',
              fontSize: 16, color: 'var(--label)', resize: 'vertical',
            }}
          />
          <button
            type="submit"
            disabled={loading}
            className="btn-primary"
            style={{ marginTop: 16, width: '100%' }}
          >
            {loading ? 'Consultando...' : 'Consultar'}
          </button>
        </form>

        {result && (
          <div style={{ marginTop: 24 }}>
            {result.error ? (
              <div style={{ color: 'red' }}>{result.error}</div>
            ) : (
              <div style={{ whiteSpace: 'pre-wrap', background: 'var(--surface)', borderRadius: 18, padding: 20, boxShadow: 'var(--sh-card)' }}
                   dangerouslySetInnerHTML={{ __html: result.html || result.markdown || JSON.stringify(result) }} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
