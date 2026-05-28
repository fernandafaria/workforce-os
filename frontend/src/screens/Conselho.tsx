import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PersonaCircle } from '../components/PersonaCircle';

export default function ConselhoPage() {
  const [step, setStep] = useState(1);
  const [problem, setProblem] = useState('Estou avaliando se vale cortar a agência de marketing e trazer o time pra dentro.');
  const [context, setContext] = useState('Lidero marketing em empresa B2B de saúde, time de 6 pessoas. Acabei de assumir e estou avaliando estrutura da agência.');
  const navigate = useNavigate();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--canvas)', fontFamily: 'var(--font)', color: 'var(--label)', WebkitFontSmoothing: 'antialiased' }}>
      {/* Nav */}
      <div style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: '1px solid var(--separator)' }}>
        <Link to="/home" style={{ color: 'var(--accent)', fontSize: 17, textDecoration: 'none' }}>←</Link>
        <div style={{ fontWeight: 600, fontSize: 17 }}>Conselho</div>
      </div>

      {step === 1 && (
        <>
          <div style={{ padding: '8px 24px 0', flex: 1, overflowY: 'auto' }}>
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: -0.4, lineHeight: '34px' }}>
                O que está te puxando esta semana.
              </div>
              <div style={{ color: 'var(--label-2)', fontSize: 15, marginTop: 8, lineHeight: '22px' }}>
                Descreva em uma frase. Eu monto quem te ajuda a pensar.
              </div>
            </div>

            {/* Textarea */}
            <div style={{ marginTop: 22, background: 'var(--surface)', borderRadius: 16, padding: '16px 18px', boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.03)', minHeight: 100 }}>
              <textarea
                value={problem}
                onChange={e => setProblem(e.target.value)}
                style={{ width: '100%', border: 0, background: 'transparent', fontSize: 17, color: 'var(--label)', lineHeight: '25px', letterSpacing: -0.1, resize: 'none', outline: 'none', fontFamily: 'inherit' }}
              />
            </div>

            {/* Hot prompts */}
            <div style={{ marginTop: 18, display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase', color: 'var(--label-2)' }}>Quentes esta semana</div>
              <div style={{ fontSize: 10, color: 'var(--label-3)' }}>↗</div>
            </div>
            <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {['Reestruturar pricing', 'Sucessão executiva', 'Demitir bem', 'Carta anual ao board', 'Negociar com investidor'].map((p, i) => (
                <button key={i} onClick={() => setProblem(p)} className="chip" style={{ fontSize: 12, padding: '4px 11px', cursor: 'pointer' }}>{p}</button>
              ))}
            </div>

            {/* Live specialist preview */}
            <div style={{ marginTop: 32 }}>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 6, height: 6, borderRadius: 999, background: 'var(--accent)' }}/>
                Pra isso, eu chamaria
              </div>

              <div style={{ background: 'var(--surface)', borderRadius: 20, padding: 20, boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 12px 32px rgba(0,0,0,0.06)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <PersonaCircle name="April Dunford" initials="EP" size={56} fontSize={18} color1="#1A4D5C" color2="#6E6E73" />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase', color: 'var(--accent)' }}>Marketing & Marca</div>
                    <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: -0.3, marginTop: 2 }}>Conselheira de Posicionamento</div>
                    <div style={{ fontSize: 12, color: 'var(--label-2)', marginTop: 2 }}>Inspirada em April Dunford</div>
                  </div>
                </div>

                <div style={{ marginTop: 18, paddingTop: 18, borderTop: '1px solid var(--separator)' }}>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase', color: 'var(--label-3)', marginBottom: 8 }}>Ela vai te perguntar primeiro</div>
                  <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: -0.3, lineHeight: '27px' }}>
                    "O atrito hoje é <span style={{color:'var(--accent)'}}>entrega</span> ou <span style={{color:'var(--accent)'}}>direção</span>?"
                  </div>
                </div>

                <div style={{ marginTop: 18 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: 'uppercase', color: 'var(--label-3)', marginBottom: 8 }}>Como ela pensa</div>
                  {['Posicionamento começa por uso real, não por persona.', 'Direção vem antes de execução.'].map((l, i) => (
                    <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginTop: i === 0 ? 0 : 6 }}>
                      <span style={{ width: 4, height: 4, borderRadius: 999, background: 'var(--accent)', marginTop: 7, flex: '0 0 4px' }}/>
                      <span style={{ fontSize: 13, color: 'var(--label-2)', lineHeight: '18px', fontStyle: 'italic' }}>"{l}"</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div style={{ padding: '20px 24px 28px' }}>
            <button onClick={() => setStep(2)} className="btn-primary" style={{ width: '100%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              Abrir conversa com Abril →
            </button>
          </div>
        </>
      )}

      {step === 2 && (
        <>
          <div style={{ padding: '8px 24px 0', flex: 1, overflowY: 'auto' }}>
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: -0.4, lineHeight: '34px' }}>
                Contexto que você compartilhou
              </div>
              <div style={{ color: 'var(--label-2)', fontSize: 15, marginTop: 8, lineHeight: '22px' }}>
                Revise antes de abrir a conversa.
              </div>
            </div>

            {/* Context card */}
            <div style={{ marginTop: 20, padding: '14px 16px', background: 'var(--surface)', borderRadius: 14, boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.03)' }}>
              <textarea
                value={context}
                onChange={e => setContext(e.target.value)}
                style={{ width: '100%', border: 0, background: 'transparent', fontSize: 15, color: 'var(--label)', lineHeight: '21px', resize: 'none', outline: 'none', fontFamily: 'inherit', minHeight: 60 }}
              />
            </div>

            {/* Specialist preview */}
            <div style={{ marginTop: 24 }}>
              <div style={{ background: 'var(--surface)', borderRadius: 20, padding: 20, boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 12px 32px rgba(0,0,0,0.05)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <PersonaCircle name="April Dunford" initials="EP" size={44} fontSize={15} color1="#1A4D5C" color2="#6E6E73" />
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.7, textTransform: 'uppercase', color: 'var(--label-2)' }}>Conselho 1:1</div>
                    <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: -0.1, marginTop: 2 }}>Marketing — Conselho</div>
                  </div>
                </div>
                <div style={{ marginTop: 16, fontSize: 15, lineHeight: '21px', fontStyle: 'italic', letterSpacing: -0.05, color: 'var(--label)' }}>
                  "Olá, José. Pode trazer um dilema concreto — ou só pedir uma leitura do cenário."
                </div>
                <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--separator)', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {['B2B', 'Pricing', 'Brand', 'Liderança'].map((t, i) => (
                    <span key={i} style={{ background: 'var(--canvas)', color: 'var(--label-2)', borderRadius: 999, padding: '3px 9px', fontSize: 11, fontWeight: 500 }}>{t}</span>
                  ))}
                </div>
              </div>
            </div>

            <div style={{ marginTop: 14, fontSize: 11, color: 'var(--label-3)', lineHeight: '16px', textAlign: 'center' }}>
              Inspirada em <b style={{color:'var(--label-2)'}}>April Dunford</b> · ajuste o estilo a qualquer momento.
            </div>
          </div>

          <div style={{ padding: '20px 24px 28px' }}>
            <button onClick={() => navigate('/home')} className="btn-primary" style={{ width: '100%' }}>Abrir conversa</button>
          </div>
        </>
      )}
    </div>
  );
}
