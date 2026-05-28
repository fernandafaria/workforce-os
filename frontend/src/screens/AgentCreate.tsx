import { useState } from 'react';
import { Link } from 'react-router-dom';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const INSPIRACOES = [
  { slug: 'elena-verna', nome: 'Elena Verna', sub: 'Growth & PLG' },
  { slug: 'patrick-campbell', nome: 'Patrick Campbell', sub: 'Pricing' },
  { slug: 'april-dunford', nome: 'April Dunford', sub: 'Posicionamento' },
  { slug: 'roger-martin', nome: 'Roger Martin', sub: 'Estratégia' },
  { slug: 'bobby-pinero', nome: 'Bobby Pinero', sub: 'Finance' },
  { slug: 'chris-voss', nome: 'Chris Voss', sub: 'Negociação' },
  { slug: 'ruth-porat', nome: 'Ruth Porat', sub: 'Risco & CFO' },
  { slug: 'simon-willison', nome: 'Simon Willison', sub: 'Tech & AI' },
];

const FREQUENCIAS = [
  { value: '0 9 * * 1', label: 'Segunda 9h' },
  { value: '0 7 * * 1-5', label: 'Diário 7h' },
  { value: '0 9 * * 3', label: 'Quarta 9h' },
  { value: '0 18 * * 5', label: 'Sexta 18h' },
  { value: '0 9 1 * *', label: 'Mensal' },
];

export function AgentCreatePage() {
  const [inspiracao, setInspiracao] = useState(INSPIRACOES[0]);
  const [objetivo, setObjetivo] = useState('');
  const [frequencia, setFrequencia] = useState(FREQUENCIAS[0].value);
  const [canal, setCanal] = useState('telegram');
  const [agendado, setAgendado] = useState(false);
  const [loading, setLoading] = useState(false);

  async function criarAgente() {
    if (!objetivo.trim()) return;
    setLoading(true);
    try {
      await fetch(`${API}/agents/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: objetivo.slice(0, 60),
          persona_slug: inspiracao.slug,
          cron_expression: frequencia,
          prompt_template: objetivo,
          channel: canal,
        }),
      });
      setAgendado(true);
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  }

  if (agendado) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--canvas)', alignItems: 'center', justifyContent: 'center', padding: 40, textAlign: 'center' }}>
        <div style={{ width: 64, height: 64, borderRadius: 18, background: 'var(--accent-bg)', color: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 32, marginBottom: 20 }}>✓</div>
        <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: -0.4, marginBottom: 8 }}>Agente criado</div>
        <div style={{ color: 'var(--label-2)', fontSize: 15, marginBottom: 24, maxWidth: 320 }}>
          **{inspiracao.nome}** vai te mandar updates<br />
          {FREQUENCIAS.find(f => f.value === frequencia)?.label.toLowerCase()}.
        </div>
        <Link to="/" className="btn-primary" style={{ textDecoration: 'none', padding: '14px 32px' }}>Voltar ao início</Link>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--canvas)' }}>
      {/* Nav */}
      <div style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: '1px solid var(--separator)' }}>
        <Link to="/" style={{ color: 'var(--accent)', fontSize: 17, textDecoration: 'none' }}>←</Link>
        <div style={{ fontWeight: 600, fontSize: 17 }}>Criar agente</div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '24px 20px' }}>
        {/* Inspiração */}
        <div style={{ fontSize: 13, color: 'var(--label-2)', fontWeight: 600, marginBottom: 10, letterSpacing: 0.3 }}>
          QUEM VAI FALAR COM VOCÊ
        </div>
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4, marginBottom: 24 }}>
          {INSPIRACOES.map(i => (
            <button
              key={i.slug}
              onClick={() => setInspiracao(i)}
              style={{
                flex: '0 0 auto',
                background: inspiracao.slug === i.slug ? 'var(--accent-bg)' : 'var(--surface)',
                borderRadius: 14,
                padding: '10px 14px',
                border: inspiracao.slug === i.slug ? '1.5px solid var(--accent)' : '1px solid transparent',
                cursor: 'pointer',
                boxShadow: inspiracao.slug === i.slug ? '0 2px 8px rgba(26,77,92,0.12)' : '0 1px 2px rgba(0,0,0,0.04)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 10,
                  background: inspiracao.slug === i.slug ? 'var(--accent)' : 'var(--fill-tertiary)',
                  color: inspiracao.slug === i.slug ? '#fff' : 'var(--label)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 700,
                }}>
                  {i.nome.split(' ').map(n => n[0]).join('').slice(0, 2)}
                </div>
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--label)', whiteSpace: 'nowrap' }}>{i.nome}</div>
                  <div style={{ fontSize: 10, color: 'var(--label-2)', whiteSpace: 'nowrap' }}>{i.sub}</div>
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* Objetivo */}
        <div style={{ fontSize: 13, color: 'var(--label-2)', fontWeight: 600, marginBottom: 10, letterSpacing: 0.3 }}>
          O QUE VOCÊ PRECISA
        </div>
        <textarea
          value={objetivo}
          onChange={e => setObjetivo(e.target.value)}
          placeholder='"Me mande toda segunda um resumo de growth com cases de PLG e alertas de churn..."'
          autoFocus
          style={{
            width: '100%', minHeight: 88, padding: 14,
            background: 'var(--surface)', borderRadius: 16,
            border: '1px solid var(--separator)',
            fontSize: 16, color: 'var(--label)', lineHeight: '22px',
            resize: 'vertical', marginBottom: 24,
          }}
        />

        {/* Frequência + Canal na mesma linha */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, color: 'var(--label-2)', fontWeight: 600, marginBottom: 8, letterSpacing: 0.3 }}>
              QUANDO
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {FREQUENCIAS.map(f => (
                <button
                  key={f.value}
                  onClick={() => setFrequencia(f.value)}
                  className={frequencia === f.value ? 'chip chip-on' : 'chip'}
                  style={{ fontSize: 12, height: 30, padding: '0 10px' }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 13, color: 'var(--label-2)', fontWeight: 600, marginBottom: 8, letterSpacing: 0.3 }}>
              ONDE
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              {[
                { value: 'telegram', label: 'Telegram' },
                { value: 'whatsapp', label: 'WhatsApp' },
              ].map(c => (
                <button
                  key={c.value}
                  onClick={() => setCanal(c.value)}
                  className={canal === c.value ? 'chip chip-on' : 'chip'}
                  style={{ fontSize: 12, height: 30, padding: '0 10px' }}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Preview sutil */}
        <div style={{
          background: 'var(--surface)', borderRadius: 16, padding: 14,
          border: '1px solid var(--separator)', marginBottom: 20,
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: 12,
            background: 'var(--accent-bg)', color: 'var(--accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 13, fontWeight: 700,
          }}>
            {inspiracao.nome.split(' ').map(n => n[0]).join('').slice(0, 2)}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--label)' }}>{inspiracao.nome}</div>
            <div style={{ fontSize: 12, color: 'var(--label-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {objetivo || 'Descreva o que você precisa...'}
            </div>
          </div>
          <div style={{ fontSize: 11, color: 'var(--label-3)' }}>
            {FREQUENCIAS.find(f => f.value === frequencia)?.label}
          </div>
        </div>

        <button
          onClick={criarAgente}
          disabled={!objetivo.trim() || loading}
          className="btn-primary"
          style={{ width: '100%' }}
        >
          {loading ? 'Criando...' : 'Criar agente'}
        </button>
      </div>
    </div>
  );
}
