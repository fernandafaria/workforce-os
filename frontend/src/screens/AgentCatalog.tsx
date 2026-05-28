import { useState, useEffect } from 'react';
import { PersonaCircle } from '../components/PersonaCircle';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface Persona {
  slug: string;
  handle: string;
  name: string;
  home_team?: string;
  domains?: string[];
}

const TEAM_LABELS: Record<string, string> = {
  strategy: 'Estratégia',
  growth: 'Growth',
  product: 'Produto',
  tech: 'Tecnologia',
  people: 'Pessoas',
  finance: 'Finanças',
  marketing: 'Marketing',
  sales: 'Vendas',
  operations: 'Operações',
  legal: 'Jurídico',
};

const TEAM_COLORS: Record<string, [string, string]> = {
  strategy: ['#1A4D5C', '#2D8A99'],
  growth: ['#6B4EFF', '#9B8EFF'],
  product: ['#E86A33', '#F59B6E'],
  tech: ['#1B4965', '#5FA8D3'],
  people: ['#8B5E3C', '#C49A6C'],
  finance: ['#2D6A4F', '#52B788'],
  marketing: ['#C44569', '#E36F8C'],
  sales: ['#3B5998', '#6B8AC4'],
  operations: ['#6C584C', '#A98467'],
  legal: ['#5C4D7D', '#8E7DBE'],
};

function getTeamColors(team?: string): [string, string] {
  return TEAM_COLORS[team || ''] || ['#5B5B5B', '#8E8E93'];
}

export default function AgentCatalogPage() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [filtered, setFiltered] = useState<Persona[]>([]);
  const [search, setSearch] = useState('');
  const [team, setTeam] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Persona | null>(null);
  const [detail, setDetail] = useState<{ prompt: string; length: number } | null>(null);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    fetch(`${API}/personas`)
      .then(r => r.json())
      .then(d => {
        const list = d.personas || [];
        setPersonas(list);
        setFiltered(list);
        setTotal(d.total || list.length);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    let result = personas;
    if (team) result = result.filter(p => p.home_team === team);
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(p =>
        p.name.toLowerCase().includes(q) ||
        p.handle?.toLowerCase().includes(q) ||
        p.slug.toLowerCase().includes(q) ||
        (p.domains || []).some(d => d.toLowerCase().includes(q))
      );
    }
    setFiltered(result);
  }, [search, team, personas]);

  const openDetail = (p: Persona) => {
    setSelected(p);
    setDetail(null);
    fetch(`${API}/personas/${p.slug}`)
      .then(r => r.json())
      .then(d => setDetail(d))
      .catch(() => {});
  };

  const teams = [...new Set(personas.map(p => p.home_team).filter(Boolean))] as string[];

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: 'var(--canvas)', color: 'var(--label-2)' }}>
        Carregando catálogo...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--canvas)', position: 'relative' }}>
      {/* Header */}
      <div style={{ padding: '8px 20px 12px', display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <div className="t-largeTitle">Especialistas</div>
          <div style={{ fontSize: 13, color: 'var(--label-2)', marginTop: 2 }}>{total} personas disponíveis</div>
        </div>
        <button onClick={() => window.history.back()} style={{ background: 'none', border: 0, color: 'var(--accent)', fontSize: 15, fontWeight: 600, cursor: 'pointer' }}>
          Voltar
        </button>
      </div>

      {/* Search */}
      <div style={{ padding: '0 20px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--fill-tertiary)', borderRadius: 999, height: 38, padding: '0 14px', color: 'var(--label-3)' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="10.5" cy="10.5" r="6"/><path d="m20 20-4.6-4.6"/></svg>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por nome, especialidade ou domínio"
            style={{ flex: 1, background: 'none', border: 0, outline: 'none', fontSize: 15, color: 'var(--label)' }}
          />
          {search && (
            <button onClick={() => setSearch('')} style={{ background: 'none', border: 0, color: 'var(--label-3)', cursor: 'pointer', fontSize: 16, padding: 0 }}>✕</button>
          )}
        </div>
      </div>

      {/* Team filter */}
      {teams.length > 0 && (
        <div style={{ padding: '0 20px 8px', display: 'flex', gap: 6, overflowX: 'auto' }}>
          <button
            onClick={() => setTeam(null)}
            style={{
              padding: '4px 12px', borderRadius: 999, border: 0, fontSize: 12, fontWeight: 600,
              background: !team ? 'var(--accent)' : 'var(--fill-tertiary)',
              color: !team ? '#fff' : 'var(--label-2)',
              cursor: 'pointer', whiteSpace: 'nowrap',
            }}
          >
            Todos
          </button>
          {teams.map(t => (
            <button
              key={t}
              onClick={() => setTeam(t === team ? null : t)}
              style={{
                padding: '4px 12px', borderRadius: 999, border: 0, fontSize: 12, fontWeight: 600,
                background: team === t ? 'var(--accent)' : 'var(--fill-tertiary)',
                color: team === t ? '#fff' : 'var(--label-2)',
                cursor: 'pointer', whiteSpace: 'nowrap',
              }}
            >
              {TEAM_LABELS[t as keyof typeof TEAM_LABELS] || t}
            </button>
          ))}
        </div>
      )}

      {/* Grid */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 16px 16px' }}>
        {filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--label-2)', fontSize: 14 }}>
            Nenhum especialista encontrado.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
            {filtered.map(p => {
              const [c1, c2] = getTeamColors(p.home_team);
              return (
                <button
                  key={p.slug}
                  onClick={() => openDetail(p)}
                  style={{
                    background: 'var(--surface)', borderRadius: 16, padding: 14, border: 0,
                    cursor: 'pointer', textAlign: 'left',
                    boxShadow: '0 1px 2px rgba(0,0,0,0.03), 0 4px 12px rgba(0,0,0,0.03)',
                  }}
                >
                  <PersonaCircle name={p.name} size={40} fontSize={16} color1={c1} color2={c2} />
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--label)', marginTop: 8, lineHeight: '18px' }}>
                    {p.name}
                  </div>
                  {p.home_team && (
                    <div style={{ fontSize: 11, color: 'var(--label-2)', marginTop: 3, textTransform: 'capitalize' }}>
                      {TEAM_LABELS[p.home_team as keyof typeof TEAM_LABELS] || p.home_team}
                    </div>
                  )}
                  {(p.domains || []).length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
                      {(p.domains || []).slice(0, 3).map(d => (
                        <span key={d} style={{ fontSize: 10, color: 'var(--label-3)', background: 'var(--fill-tertiary)', borderRadius: 6, padding: '2px 6px' }}>
                          {d}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Detail Sheet */}
      {selected && (
        <>
          <div onClick={() => setSelected(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.32)', zIndex: 50 }} />
          <div style={{ position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 51, paddingBottom: 28 }}>
            <div className="sheet" style={{ paddingBottom: 16 }}>
              <div className="grabber" />
              <div style={{ padding: '16px 20px 4px', display: 'flex', alignItems: 'center', gap: 12 }}>
                <PersonaCircle name={selected.name} size={48} fontSize={20} color1={getTeamColors(selected.home_team ?? undefined)[0]} color2={getTeamColors(selected.home_team ?? undefined)[1]} />
                <div>
                  <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: -0.1 }}>{selected.name}</div>
                  <div style={{ fontSize: 13, color: 'var(--label-2)' }}>@{selected.handle || selected.slug}</div>
                </div>
              </div>
              <div style={{ padding: '12px 20px 0' }}>
                {selected.home_team && (
                  <div style={{ display: 'inline-block', padding: '3px 10px', borderRadius: 999, background: 'var(--fill-tertiary)', fontSize: 12, fontWeight: 600, color: 'var(--label)', marginBottom: 8 }}>
                    {TEAM_LABELS[selected.home_team as keyof typeof TEAM_LABELS] || selected.home_team}
                  </div>
                )}
                {(selected.domains || []).length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                    {(selected.domains || []).map((d: string) => (
                      <span key={d} style={{ fontSize: 11, color: 'var(--label-2)', background: 'var(--fill-tertiary)', borderRadius: 8, padding: '4px 10px' }}>
                        {d}
                      </span>
                    ))}
                  </div>
                )}
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 12, color: 'var(--label-2)', textTransform: 'uppercase', letterSpacing: 0.6, fontWeight: 600, marginBottom: 8 }}>
                    System Prompt
                  </div>
                  <div style={{
                    background: 'var(--canvas)', borderRadius: 12, padding: 12,
                    fontSize: 12, color: 'var(--label-2)', lineHeight: '18px',
                    maxHeight: 200, overflowY: 'auto', whiteSpace: 'pre-wrap',
                    fontFamily: 'SF Mono, Menlo, monospace',
                  }}>
                    {detail?.prompt || 'Carregando...'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
