import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '@/store'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { setToken } = useStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (res.status === 401) {
        setError('Invalid username or password')
        return
      }
      if (!res.ok) {
        setError(`Login failed (${res.status})`)
        return
      }
      const data = await res.json()
      setToken(data.access_token)
      navigate('/', { replace: true })
    } catch {
      setError('Network error — is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#0f172a',
    }}>
      <div className="card" style={{ width: 360, padding: 32 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>⚗</div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: 'white' }}>Alembic</h1>
          <p style={{ margin: '4px 0 0', color: 'var(--text-muted)', fontSize: 13 }}>Sign in to your dashboard</p>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: 'var(--text-muted)', fontWeight: 500 }}>
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              autoComplete="username"
              required
              style={{ width: '100%', boxSizing: 'border-box' }}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: 'var(--text-muted)', fontWeight: 500 }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
              style={{ width: '100%', boxSizing: 'border-box' }}
            />
          </div>

          {error && (
            <div style={{ marginBottom: 16, padding: '8px 12px', background: '#450a0a', border: '1px solid #7f1d1d', borderRadius: 6, color: '#fca5a5', fontSize: 13 }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn-primary"
            disabled={loading}
            style={{ width: '100%', padding: '10px 16px', fontSize: 14 }}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
