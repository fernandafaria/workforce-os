import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PersonaCircle } from '../components/PersonaCircle';

const VOCES = [
  { name: 'April Dunford', role: 'Estratégia', initials: 'AD', color1: '#1A4D5C', color2: '#6E6E73' },
  { name: 'Marty Neumeier', role: 'Marca', initials: 'MN', color1: '#305C6B', color2: '#9CA1A6' },
  { name: 'Bill Gurley', role: 'Finanças', initials: 'BG', color1: '#2C5F6F', color2: '#7A8A90' },
  { name: 'Ben Horowitz', role: 'Operações', initials: 'BH', color1: '#1F4A55', color2: '#8B949A' },
  { name: 'Charlie Munger', role: 'Pushback', initials: 'CM', color1: '#0E3B47', color2: '#AEAEB2' },
];

export default function GrupoPage() {
  const [step, setStep] = useState(1);
  const [topic, setTopic] = useState('Vale cortar agência e trazer marketing interno?');
  const [devilsAdvocate, setDevilsAdvocate] = useState(true);
  const navigate = useNavigate();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--canvas)', fontFamily: 'var(--font)', color: 'var(--label)', WebkitFontSmoothing: 'antialiased' }}>
      {/* Nav */}
      <div style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: '1px solid var(--separator)' }}>
        <Link to="/home" style={{ color: 'var(--accent)', fontSize: 17, textDecoration: 'none' }}>←</Link>
        <div style={{ fontWeight: 600, fontSize: 17 }}>Grupo</div>
      </div>

      {step === 1 && (
        <>
          <div style={{ padding: '8px 24px 0', flex: 1, overflowY: 'auto' }}>
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: -0.4, lineHeight: '34px' }}>
                Que decisão está em jogo.
              </div>
              <div style={{ color: 'var(--label-2)', fontSize: 15, marginTop: 8, lineHeight: '22px' }}>
                Uma pergunta. Quanto mais nítida, mais útil o resumo no fim.
              </div>
            </div>

            {/* Big textarea */}
            <div style={{ marginTop: 24 }}>
              <div style={{ background: 'var(--surface)', borderRadius: 14, padding: '16px 18px', boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.03)', minHeight: 110 }}>
                <textarea
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  style={{ width: '100%', border: 0, background: 'transparent', fontSize: 18, color: 'var(--label)', lineHeight: '26px', letterSpacing: -0.1, resize: 'none', outline: 'none', fontFamily: 'inherit', minHeight: 80 }}
                />
              </div>
            </div>

            {/* Decisões frequentes */}
            <div style={{ marginTop: 28, fontSize: 11, fontWeight: 600, letterSpacing: 0.7, textTransform: 'uppercase', color: 'var(--label-2)' }}>
              Decisões frequentes
            </div>
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { tag: 'CAPITAL', t: 'Devo aceitar a contraproposta do investidor?' },
                { tag: 'ESTRUTURA', t: 'Reestruturar a área comercial agora ou em Q4?' },
                { tag: 'PRICING', t: 'Vale cortar agência e trazer marketing interno?' },
              ].map((e, i) => (
                <button
                  key={i}
                  onClick={() => { setTopic(e.t); setStep(2); }}
                  style={{
                    background: 'var(--surface)', border: 0, borderRadius: 12,
                    padding: '12px 14px', cursor: 'pointer', fontFamily: 'var(--font)',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                    display: 'flex', alignItems: 'center', gap: 12, textAlign: 'left', width: '100%',
                  }}
                >
                  <span style={{ fontSize: 10, color: 'var(--label-3)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 700, width: 70, flex: '0 0 70px' }}>
                    {e.tag}
                  </span>
                  <span style={{ flex: 1, fontSize: 14, color: 'var(--label)', lineHeight: '19px' }}>{e.t}</span>
                </button>
              ))}
            </div>
          </div>
          <div style={{ padding: '20px 24px 28px' }}>
            <button onClick={() => setStep(2)} className="btn-primary" style={{ width: '100%' }}>Continuar</button>
          </div>
        </>
      )}

      {step === 2 && (
        <>
          <div style={{ padding: '8px 24px 0', flex: 1, overflowY: 'auto' }}>
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: -0.4, lineHeight: '34px' }}>
                Vou convocar este grupo.
              </div>
              <div style={{ color: 'var(--label-2)', fontSize: 15, marginTop: 8, lineHeight: '22px' }}>
                Eles discutem, divergem onde precisa, e te entregam um resumo para decidir.
              </div>
            </div>

            {/* Preview card */}
            <div style={{ marginTop: 24 }}>
              <div style={{ background: 'var(--surface)', borderRadius: 20, padding: 20, boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 12px 32px rgba(0,0,0,0.05)' }}>
                <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase', color: 'var(--accent)' }}>
                  Ritual · Deep Dive · 4 estágios
                </div>
                <div style={{ fontSize: 19, fontWeight: 600, letterSpacing: -0.2, marginTop: 4, lineHeight: '25px' }}>
                  {topic}
                </div>

                {/* Voices */}
                <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--separator)' }}>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase', color: 'var(--label-3)', marginBottom: 10 }}>Vozes · {VOCES.length}</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {VOCES.map((v, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <PersonaCircle name={v.name} initials={v.initials} size={28} fontSize={11} color1={v.color1} color2={v.color2} />
                        <div style={{ flex: 1, minWidth: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
                          <span style={{ fontSize: 13, fontWeight: 500 }}>{v.role}</span>
                          <span style={{ fontSize: 11, color: 'var(--label-3)' }}>{v.name.split(' ')[0]}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Stats */}
                <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--separator)', display: 'flex', gap: 28 }}>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--label-3)', textTransform: 'uppercase', letterSpacing: 0.7, fontWeight: 600 }}>Pronto em</div>
                    <div style={{ fontSize: 18, fontWeight: 600, marginTop: 4, letterSpacing: -0.2 }}>~15 min</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--label-3)', textTransform: 'uppercase', letterSpacing: 0.7, fontWeight: 600 }}>Custo até</div>
                    <div style={{ fontSize: 18, fontWeight: 600, marginTop: 4, letterSpacing: -0.2 }}>R$ 18</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--label-3)', textTransform: 'uppercase', letterSpacing: 0.7, fontWeight: 600 }}>Entrega</div>
                    <div style={{ fontSize: 18, fontWeight: 600, marginTop: 4, letterSpacing: -0.2 }}>Resumo</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Devil's advocate toggle */}
            <div style={{ marginTop: 16, padding: '14px 16px', background: 'var(--surface)', borderRadius: 14, boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.03)', display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, letterSpacing: -0.1 }}>Quero que discordem de mim</div>
                <div style={{ fontSize: 12, color: 'var(--label-2)', marginTop: 3, lineHeight: '17px' }}>
                  Charlie Munger entra com o papel de inversão e crítica.
                </div>
              </div>
              <div
                onClick={() => setDevilsAdvocate(!devilsAdvocate)}
                style={{
                  width: 48, height: 28, borderRadius: 999,
                  background: devilsAdvocate ? 'var(--accent)' : 'var(--fill-secondary)',
                  position: 'relative', cursor: 'pointer', flexShrink: 0,
                  transition: 'background 0.2s',
                }}
              >
                <div style={{
                  width: 24, height: 24, borderRadius: 999, background: '#fff',
                  position: 'absolute', top: 2, left: devilsAdvocate ? 22 : 2,
                  transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.15)',
                }}/>
              </div>
            </div>
          </div>
          <div style={{ padding: '20px 24px 28px' }}>
            <button onClick={() => navigate('/home')} className="btn-primary" style={{ width: '100%' }}>
              Convocar o grupo
            </button>
          </div>
        </>
      )}
    </div>
  );
}
