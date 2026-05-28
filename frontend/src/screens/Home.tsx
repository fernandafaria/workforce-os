import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function HomePage() {
  const [personaCount, setPersonaCount] = useState(12);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    fetch(`${API}/personas`)
      .then(r => r.json())
      .then(d => { if (d.total) setPersonaCount(d.total); })
      .catch(() => {});
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--canvas)', position: 'relative', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '8px 20px 12px', display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div className="t-largeTitle">Meu cérebro</div>
        <div className="avatar lg" style={{ background: '#ECEBE9' }}>JM</div>
      </div>

      {/* Search */}
      <div style={{ padding: '0 20px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--fill-tertiary)', borderRadius: 999, height: 38, padding: '0 14px', color: 'var(--label-3)' }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="7" cy="7" r="5"/><line x1="11" y1="11" x2="15" y2="15"/></svg>
          <span style={{ fontSize: 15 }}>Buscar conversas e memórias</span>
        </div>
      </div>

      {/* Memories strip */}
      <div style={{ padding: '0 20px 4px', display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--label-2)', textTransform: 'uppercase', letterSpacing: 0.7, fontWeight: 600 }}>
            🔒 O que mandei pro meu cérebro
          </div>
          <div style={{ fontSize: 10, color: 'var(--label-3)', marginTop: 2 }}>Cifrado ponta-a-ponta · só você acessa</div>
        </div>
        <button style={{ background: 'none', border: 0, color: 'var(--accent)', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>Ver tudo</button>
      </div>

      <div style={{ padding: '10px 20px 12px', display: 'flex', gap: 10, overflowX: 'auto' }}>
        {[
          { state: 'live', origin: 'WhatsApp · há 2h', text: 'Decidi pricing enterprise +6% com grandfathering de 90 dias.' },
          { state: 'live', origin: 'Áudio · ontem', text: 'Quando falar com investidor, esquecer narrativa de "plataforma". É produto.' },
          { state: 'archived', origin: 'WhatsApp · seg', text: 'Time comercial tem que aprender a dizer não para descontos abaixo de 20%.' },
        ].map((m, i) => (
          <div key={i} style={{
            flex: '0 0 240px', background: 'var(--surface)', borderRadius: 14, padding: 12,
            boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04)',
            opacity: m.state === 'archived' ? 0.55 : 1, cursor: 'pointer',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 6, height: 6, borderRadius: 999, background: m.state === 'live' ? 'var(--accent)' : 'var(--label-3)' }} />
              <span style={{ fontSize: 10, color: 'var(--label-2)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 600 }}>
                {m.state === 'live' ? 'Vivo' : 'Arquivado'}
              </span>
              <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--label-3)' }}>{m.origin}</span>
            </div>
            <div style={{ fontSize: 13, color: 'var(--label)', lineHeight: '18px', marginTop: 6 }}>{m.text}</div>
          </div>
        ))}
      </div>

      {/* Preview Cards */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Link to="/criar" style={{ textDecoration: 'none', color: 'inherit' }}>
          <div style={{ background: 'var(--surface)', borderRadius: 18, padding: 16, boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.04)' }}>
            <div style={{ fontSize: 10, color: 'var(--label-2)', textTransform: 'uppercase', letterSpacing: 0.7, fontWeight: 600 }}>CRIE SEU PRIMEIRO AGENTE</div>
            <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: -0.1, marginTop: 2 }}>Agente automático</div>
            <div style={{ marginTop: 10, fontSize: 13, color: 'var(--label)', lineHeight: '18px' }}>
              Escolha uma inspiração, defina o que precisa, e receba atualizações automáticas no Telegram ou WhatsApp.
            </div>
          </div>
        </Link>

        <Link to="/conselho" style={{ textDecoration: 'none', color: 'inherit' }}>
          <div style={{ background: 'var(--surface)', borderRadius: 18, padding: 16, boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.04)' }}>
            <div style={{ fontSize: 10, color: 'var(--label-2)', textTransform: 'uppercase', letterSpacing: 0.7, fontWeight: 600 }}>ÚLTIMA TROCA · 14:32</div>
            <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: -0.1, marginTop: 2 }}>Marketing — Conselho</div>
            <div style={{ marginTop: 10, fontSize: 14, color: 'var(--label)', lineHeight: '20px' }}>
              "Então o caminho é contratar liderança e renegociar escopo — não cortar."
            </div>
            <div style={{ marginTop: 8, fontSize: 11, color: 'var(--label-3)' }}>3 perguntas em aberto</div>
          </div>
        </Link>

        <Link to="/grupo" style={{ textDecoration: 'none', color: 'inherit' }}>
          <div style={{ background: 'var(--surface)', borderRadius: 18, padding: 16, boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.04)' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
              <div>
                <div style={{ fontSize: 10, color: 'var(--label-2)', textTransform: 'uppercase', letterSpacing: 0.7, fontWeight: 600 }}>5 VOZES · 4 NOVAS</div>
                <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: -0.1, marginTop: 2 }}>Grupo: Preço março</div>
              </div>
              <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 20, height: 20, padding: '0 7px', borderRadius: 999, background: 'var(--accent)', color: '#fff', fontSize: 11, fontWeight: 600 }}>4</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 10 }}>
              <span style={{ fontSize: 22, fontWeight: 600, letterSpacing: -0.4, color: 'var(--accent)', lineHeight: 1 }}>73%</span>
              <div style={{ flex: 1, fontSize: 12, color: 'var(--label)', lineHeight: '16px' }}>das reclamações 2024 vêm de mid-market — não SMB.</div>
            </div>
            <div style={{ marginTop: 8, fontSize: 10, color: 'var(--label-3)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 600 }}>Advogado do diabo · há 2 min</div>
          </div>
        </Link>

        {/* Team entry */}
        <button style={{ background: 'transparent', border: 0, borderRadius: 14, padding: '14px 4px', display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', textAlign: 'left', color: 'var(--label-2)' }}>
          <span style={{ width: 36, height: 36, borderRadius: 12, background: 'var(--canvas)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
            👥
          </span>
          <Link to="/catalogo" style={{ textDecoration: 'none', color: 'inherit', flex: 1 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--label)' }}>Meu time</div>
            <div style={{ fontSize: 12, color: 'var(--label-2)' }}>{personaCount} especialistas disponíveis</div>
          </div>
          </Link>
        </button>
      </div>

      {/* FAB */}
      <button className="fab" aria-label="Criar" onClick={() => setShowCreate(true)} style={{ position: 'absolute', right: 20, bottom: 32 }}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      </button>

      {/* Create Sheet */}
      {showCreate && (
        <>
          <div onClick={() => setShowCreate(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.32)', zIndex: 50 }} />
          <div style={{ position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 51, paddingBottom: 28 }}>
            <div className="sheet" style={{ paddingBottom: 16 }}>
              <div className="grabber" />
              <div style={{ padding: '16px 20px 4px' }}>
                <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: -0.2 }}>O que você quer criar?</div>
                <div style={{ color: 'var(--label-2)', fontSize: 15, marginTop: 4 }}>Escolha como esse contato vai trabalhar para você.</div>
              </div>
              <div style={{ padding: '16px 16px 0', display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[
                  { kicker: 'CRIE UM AGENTE · RODA SOZINHO', title: 'Criar agente automático', sub: 'Escolha uma inspiração, defina a frequência e receba no Telegram ou WhatsApp.', to: '/criar' },
                  { kicker: 'RESPONDE QUANDO VOCÊ PRECISAR', title: 'Me aconselha quando eu precisar', sub: 'Uma conversa para decisões e conselhos.', to: '/conselho' },
                  { kicker: 'VÁRIAS VOZES · TEMPO ESTIMADO ~15 MIN', title: 'Grupo para decidir', sub: 'Vozes discutem um tema e fecham um resumo.', to: '/grupo' },
                ].map((o, i) => (
                  <Link key={i} to={o.to} onClick={() => setShowCreate(false)} style={{ textDecoration: 'none', color: 'inherit' }}>
                    <div style={{ background: 'var(--canvas)', borderRadius: 16, padding: 14 }}>
                      <div style={{ fontSize: 10, color: 'var(--label-2)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 600 }}>{o.kicker}</div>
                      <div style={{ fontSize: 16, fontWeight: 600, letterSpacing: -0.1, marginTop: 3 }}>{o.title}</div>
                      <div style={{ fontSize: 12, color: 'var(--label-2)', marginTop: 4, lineHeight: '16px' }}>{o.sub}</div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
