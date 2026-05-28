import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function LandingPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const navigate = useNavigate();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    navigate('/home');
  }

  return (
    <div style={{
      minHeight: '100vh',
      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", system-ui, sans-serif',
      color: '#1D1D1F',
      WebkitFontSmoothing: 'antialiased',
      background: '#F5F5F7',
    }}>
      {/* ────── Nav ────── */}
      <header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '20px 28px', maxWidth: 1200, margin: '0 auto',
      }}>
        <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: -0.1, color: '#1A4D5C' }}>
          Second Brain
        </div>
        <button
          onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: 14, fontWeight: 500, color: '#6E6E73',
          }}
        >
          {mode === 'login' ? 'Criar conta' : 'Entrar'}
        </button>
      </header>

      {/* ────── Hero ────── */}
      <section style={{ maxWidth: 720, margin: '0 auto', padding: '80px 28px 60px', textAlign: 'center' }}>
        <h1 style={{
          fontSize: 56, fontWeight: 700, letterSpacing: -0.8, lineHeight: 1.08,
          margin: 0, color: '#1D1D1F',
        }}>
          Conselheiros de elite.<br />Disponíveis 24 horas.
        </h1>
        <p style={{
          fontSize: 18, lineHeight: 1.55, color: '#6E6E73', margin: '20px auto 0',
          maxWidth: 480, fontWeight: 400,
        }}>
          Cada especialista é modelado em uma pessoa real — com metodologia,
          conhecimento profundo e viés conhecido. Como ter um board pessoal
          sempre disponível para qualquer decisão do seu negócio.
        </p>
      </section>

      {/* ────── Três passos ────── */}
      <section style={{ maxWidth: 880, margin: '0 auto', padding: '0 28px 80px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 32 }}>
          {[
            { num: '01', title: 'Escolha quem te inspira', body: 'Elena Verna. Patrick Campbell. April Dunford. Pessoas reais com décadas de experiência e metodologia própria.' },
            { num: '02', title: 'Descreva sua decisão', body: 'Em linguagem natural. Como se estivesse falando com um consultor de confiança. Zero prompting.' },
            { num: '03', title: 'Receba a recomendação', body: 'Múltiplas perspectivas. Estruturado com sumário executivo, fontes e advogado do diabo.' },
          ].map((s, i) => (
            <div key={i}>
              <div style={{
                fontSize: 12, fontWeight: 600, color: '#AEAEB2',
                letterSpacing: 0.8, marginBottom: 12, textTransform: 'uppercase',
              }}>{s.num}</div>
              <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: -0.1, marginBottom: 8, color: '#1D1D1F' }}>{s.title}</div>
              <div style={{ fontSize: 14, lineHeight: 1.55, color: '#6E6E73' }}>{s.body}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ────── Quote ────── */}
      <section style={{ maxWidth: 720, margin: '0 auto', padding: '0 28px 80px', textAlign: 'center' }}>
        <blockquote style={{ margin: 0 }}>
          <p style={{ fontSize: 28, fontWeight: 600, letterSpacing: -0.3, lineHeight: 1.35, color: '#1D1D1F' }}>
            "Antes de decidir: o atrito é entrega ou direção?"
          </p>
          <footer style={{ fontSize: 14, color: '#6E6E73', marginTop: 12 }}>
            Roger Martin · Conselho de estratégia · 14:32
          </footer>
        </blockquote>
      </section>

      {/* ────── Login / Signup ────── */}
      <section style={{ background: '#FFFFFF', borderTop: '1px solid rgba(60,60,67,0.12)', padding: '60px 28px 80px' }}>
        <div style={{ maxWidth: 360, margin: '0 auto' }}>
          <h2 style={{
            fontSize: 28, fontWeight: 700, letterSpacing: -0.3, textAlign: 'center',
            margin: '0 0 4px', color: '#1D1D1F',
          }}>
            {mode === 'login' ? 'Entrar' : 'Criar conta'}
          </h2>
          <p style={{
            fontSize: 15, color: '#6E6E73', textAlign: 'center', margin: '0 0 28px',
          }}>
            {mode === 'login' ? '3 consultas grátis por mês. Sem cartão.' : 'Comece em 30 segundos. Sem cartão.'}
          </p>

          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: '#6E6E73', marginBottom: 6 }}>
                Email
              </label>
              <input
                type="email" value={email} onChange={e => setEmail(e.target.value)}
                required
                style={{
                  width: '100%', padding: '12px 14px',
                  background: '#F5F5F7', borderRadius: 10,
                  border: '1px solid rgba(60,60,67,0.12)', outline: 'none',
                  fontSize: 16, color: '#1D1D1F',
                }}
              />
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: '#6E6E73', marginBottom: 6 }}>
                Senha
              </label>
              <input
                type="password" value={password} onChange={e => setPassword(e.target.value)}
                required
                style={{
                  width: '100%', padding: '12px 14px',
                  background: '#F5F5F7', borderRadius: 10,
                  border: '1px solid rgba(60,60,67,0.12)', outline: 'none',
                  fontSize: 16, color: '#1D1D1F',
                }}
              />
            </div>
            <button
              type="submit"
              style={{
                width: '100%', padding: '13px', borderRadius: 10,
                background: '#1A4D5C', color: '#FFFFFF', border: 'none',
                fontSize: 16, fontWeight: 600, cursor: 'pointer',
                letterSpacing: -0.1,
              }}
            >
              {mode === 'login' ? 'Entrar' : 'Criar conta'}
            </button>
          </form>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '20px 0' }}>
            <div style={{ flex: 1, height: 1, background: 'rgba(60,60,67,0.12)' }} />
            <span style={{ fontSize: 13, color: '#AEAEB2' }}>ou</span>
            <div style={{ flex: 1, height: 1, background: 'rgba(60,60,67,0.12)' }} />
          </div>

          <button
            onClick={() => navigate('/home')}
            style={{
              width: '100%', padding: '13px', borderRadius: 10,
              background: '#FFFFFF', border: '1px solid rgba(60,60,67,0.12)',
              fontSize: 16, fontWeight: 500, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              color: '#1D1D1F',
            }}
          >
            Continuar com Google
          </button>

          <p style={{
            fontSize: 12, color: '#AEAEB2', textAlign: 'center', marginTop: 24,
            lineHeight: 1.5,
          }}>
            Seus dados são criptografados ponta-a-ponta.<br />
            Ninguém além de você acessa suas decisões.
          </p>
        </div>
      </section>

      {/* ────── FAQ ────── */}
      <section style={{ maxWidth: 720, margin: '0 auto', padding: '80px 28px', borderTop: '1px solid rgba(60,60,67,0.12)' }}>
        <h2 style={{ fontSize: 28, fontWeight: 700, letterSpacing: -0.3, textAlign: 'center', marginBottom: 40, color: '#1D1D1F' }}>
          O que é o Second Brain
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {[
            { q: 'Não é um chatbot.', a: 'É um conselho consultivo. Cada especialista tem alma — modelado em uma pessoa real com metodologia, conhecimento e viés conhecido. Você sabe de onde vem cada recomendação.' },
            { q: 'Não é genérico.', a: 'O contexto brasileiro está embutido. Sete verticais setoriais com knowledge bases profundas — da indústria ao varejo, do agro à tecnologia.' },
            { q: 'Não é passivo.', a: 'Você cria agentes automáticos que rodam sozinhos. Escolha uma inspiração, defina a frequência, e receba no Telegram ou WhatsApp.' },
            { q: 'Não é caro.', a: 'R$497/mês. Menos que uma hora de consultoria especializada. Três consultas grátis por mês para testar.' },
          ].map((item, i) => (
            <div key={i}>
              <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: -0.1, marginBottom: 6, color: '#1D1D1F' }}>{item.q}</div>
              <div style={{ fontSize: 15, lineHeight: 1.6, color: '#6E6E73' }}>{item.a}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ────── Footer ────── */}
      <footer style={{
        textAlign: 'center', padding: '40px 28px',
        color: '#AEAEB2', fontSize: 12,
        borderTop: '1px solid rgba(60,60,67,0.12)',
      }}>
        Second Brain · FeBrain · 2026
      </footer>
    </div>
  );
}
