import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '@/store'
import alembicLogo from '@/assets/alembic.png'

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
        setError('Username or password is incorrect.')
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
      width: '100%',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#f0f2f5',
    }}>
      {/* Logo */}
      <img
        src={alembicLogo}
        alt="Alembic"
        style={{ width: 72, height: 72, objectFit: 'contain', marginBottom: 24 }}
      />

      {/* Form */}
      <form
        onSubmit={handleSubmit}
        noValidate
        style={{ width: '100%', maxWidth: 320 }}
      >
        <div style={{ marginBottom: 14 }}>
          <label style={{
            display: 'block',
            marginBottom: 6,
            fontSize: 13,
            fontWeight: 500,
            color: '#334155',
          }}>
            Username
          </label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Enter your username"
            autoComplete="username"
            autoFocus
            required
            style={{
              display: 'block',
              width: '100%',
              padding: '10px 12px',
              fontSize: 14,
              color: '#0f172a',
              background: '#ffffff',
              border: '1px solid #cbd5e1',
              borderRadius: 8,
              outline: 'none',
            }}
            onFocus={(e) => {
              e.target.style.borderColor = '#3b82f6'
              e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.12)'
            }}
            onBlur={(e) => {
              e.target.style.borderColor = '#cbd5e1'
              e.target.style.boxShadow = 'none'
            }}
          />
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{
            display: 'block',
            marginBottom: 6,
            fontSize: 13,
            fontWeight: 500,
            color: '#334155',
          }}>
            Password
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete="current-password"
            required
            style={{
              display: 'block',
              width: '100%',
              padding: '10px 12px',
              fontSize: 14,
              color: '#0f172a',
              background: '#ffffff',
              border: '1px solid #cbd5e1',
              borderRadius: 8,
              outline: 'none',
            }}
            onFocus={(e) => {
              e.target.style.borderColor = '#3b82f6'
              e.target.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.12)'
            }}
            onBlur={(e) => {
              e.target.style.borderColor = '#cbd5e1'
              e.target.style.boxShadow = 'none'
            }}
          />
        </div>

        {error && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 16,
            padding: '10px 14px',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: 8,
            color: '#b91c1c',
            fontSize: 13,
          }}>
            <span style={{ flexShrink: 0 }}>⚠</span>
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          style={{
            display: 'block',
            width: '100%',
            padding: '11px 16px',
            fontSize: 14,
            fontWeight: 600,
            color: '#ffffff',
            background: loading ? '#93c5fd' : '#2563eb',
            border: 'none',
            borderRadius: 8,
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
          onMouseEnter={(e) => { if (!loading) (e.target as HTMLButtonElement).style.background = '#1d4ed8' }}
          onMouseLeave={(e) => { if (!loading) (e.target as HTMLButtonElement).style.background = '#2563eb' }}
        >
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
