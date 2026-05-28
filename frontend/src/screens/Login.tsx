import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError('');

    if (!email || !password) {
      setError('Email e senha são obrigatórios.');
      return;
    }

    setLoading(true);

    try {
      if (SUPABASE_URL && SUPABASE_ANON_KEY) {
        // Supabase Auth via REST (no SDK needed)
        const res = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'apikey': SUPABASE_ANON_KEY,
          },
          body: JSON.stringify({ email, password }),
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.error_description || err.msg || 'Credenciais inválidas');
        }

        const data = await res.json();
        localStorage.setItem('wf_token', data.access_token);
        localStorage.setItem('wf_user_id', data.user?.id || '');
      } else {
        // Dev mode: skip auth, store email as pseudo-identity
        localStorage.setItem('wf_token', 'dev-token');
        localStorage.setItem('wf_user_id', email);
      }

      navigate('/');
    } catch (err: any) {
      setError(err.message || 'Erro ao fazer login.');
    }

    setLoading(false);
  }

  async function handleSignUp(e: React.FormEvent) {
    e.preventDefault();
    setError('');

    if (!email || !password) {
      setError('Email e senha são obrigatórios.');
      return;
    }

    if (password.length < 6) {
      setError('Senha deve ter pelo menos 6 caracteres.');
      return;
    }

    setLoading(true);

    try {
      if (SUPABASE_URL && SUPABASE_ANON_KEY) {
        const res = await fetch(`${SUPABASE_URL}/auth/v1/signup`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'apikey': SUPABASE_ANON_KEY,
          },
          body: JSON.stringify({ email, password }),
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.msg || 'Erro ao criar conta');
        }

        const data = await res.json();
        localStorage.setItem('wf_token', data.access_token);
        localStorage.setItem('wf_user_id', data.user?.id || '');
        navigate('/');
      } else {
        localStorage.setItem('wf_token', 'dev-token');
        localStorage.setItem('wf_user_id', email);
        navigate('/');
      }
    } catch (err: any) {
      setError(err.message || 'Erro ao criar conta.');
    }

    setLoading(false);
  }

  return (
    <div className="eb" style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--canvas)', padding: 24,
    }}>
      <div style={{
        width: '100%', maxWidth: 400, background: 'var(--surface)', borderRadius: 24,
        padding: 32, boxShadow: '0 1px 2px rgba(0,0,0,0.04), 0 12px 40px rgba(0,0,0,0.08)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: -0.3 }}>Second Brain</div>
          <div style={{ fontSize: 14, color: 'var(--label-2)', marginTop: 4 }}>
            Entre para acessar seu conselho executivo
          </div>
        </div>

        {error && (
          <div style={{
            background: '#FEE2E2', color: '#991B1B', borderRadius: 12, padding: '10px 14px',
            fontSize: 13, marginBottom: 16,
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleLogin}>
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--label)', marginBottom: 6 }}>
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="seu@email.com"
              autoComplete="email"
              style={{
                width: '100%', padding: '12px 14px', borderRadius: 12, border: '1px solid var(--separator)',
                fontSize: 15, background: 'var(--canvas)', color: 'var(--label)',
                outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--label)', marginBottom: 6 }}>
              Senha
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Sua senha"
              autoComplete="current-password"
              style={{
                width: '100%', padding: '12px 14px', borderRadius: 12, border: '1px solid var(--separator)',
                fontSize: 15, background: 'var(--canvas)', color: 'var(--label)',
                outline: 'none', boxSizing: 'border-box',
              }}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn-primary"
            style={{
              width: '100%', padding: '14px', borderRadius: 999, border: 'none',
              fontSize: 16, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? 'Entrando...' : 'Entrar'}
          </button>
        </form>

        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <button
            onClick={handleSignUp}
            disabled={loading}
            style={{
              width: '100%', padding: '14px', borderRadius: 999,
              border: '1px solid var(--separator)', background: 'transparent',
              fontSize: 16, fontWeight: 500, color: 'var(--label)', cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? 'Criando...' : 'Criar conta grátis'}
          </button>
        </div>

        <div style={{ marginTop: 20, textAlign: 'center' }}>
          <Link to="/" style={{ fontSize: 13, color: 'var(--label-3)', textDecoration: 'none' }}>
            ← Voltar para o site
          </Link>
        </div>
      </div>
    </div>
  );
}
