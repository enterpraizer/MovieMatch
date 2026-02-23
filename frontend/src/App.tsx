import { FormEvent, useMemo, useState } from 'react'

type Mode = 'collaborative' | 'nlp' | 'mood'

type Recommendation = {
  movie_id: number
  title: string
  score: number
  reason: string
}

type LoginResponse = {
  access_token: string
  refresh_token: string
  token_type: string
  user_id: number
  expires_in: number
}

const API_BASE = 'http://localhost:8000'

export function App() {
  const [email, setEmail] = useState('ml_user_1@moviematch.local')
  const [password, setPassword] = useState('moviematch')
  const [mode, setMode] = useState<Mode>('collaborative')
  const [query, setQuery] = useState('space')
  const [topK, setTopK] = useState(5)
  const [accessToken, setAccessToken] = useState('')
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [status, setStatus] = useState('Ready')

  const queryLabel = useMemo(() => {
    if (mode === 'nlp') return 'Query'
    if (mode === 'mood') return 'Mood (happy/sad/neutral...)'
    return 'Query (optional)'
  }, [mode])

  async function handleLogin(event: FormEvent) {
    event.preventDefault()
    setStatus('Logging in...')

    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })

    if (!response.ok) {
      setStatus(`Login failed: ${response.status}`)
      return
    }

    const payload: LoginResponse = await response.json()
    setAccessToken(payload.access_token)
    setStatus(`Logged in as user ${payload.user_id}`)
  }

  async function handleRecommend(event: FormEvent) {
    event.preventDefault()
    if (!accessToken) {
      setStatus('Login first')
      return
    }

    setStatus('Fetching recommendations...')

    const body: { top_k: number; query?: string } = { top_k: topK }
    if (query.trim()) {
      body.query = query.trim()
    }

    const response = await fetch(`${API_BASE}/recommendations/${mode}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      setStatus(`Recommendation failed: ${response.status}`)
      setRecommendations([])
      return
    }

    const payload = await response.json()
    const jobId: string | undefined = payload.job_id
    if (!jobId) {
      setStatus('Recommendation failed: no job_id')
      return
    }

    setStatus(`Job queued: ${jobId}`)
    const deadline = Date.now() + 60000
    while (Date.now() < deadline) {
      const statusResp = await fetch(`${API_BASE}/recommendations/jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      if (!statusResp.ok) {
        setStatus(`Status check failed: ${statusResp.status}`)
        return
      }
      const statusPayload = await statusResp.json()
      if (statusPayload.status === 'completed') {
        const items = statusPayload.result?.recommendations ?? []
        setRecommendations(items)
        setStatus(`Done: ${items.length} items`)
        return
      }
      if (statusPayload.status === 'failed') {
        setStatus(`Job failed: ${statusPayload.error ?? 'unknown error'}`)
        setRecommendations([])
        return
      }
      await new Promise((resolve) => setTimeout(resolve, 1000))
    }

    setStatus('Recommendation job timed out')
    setRecommendations([])
  }

  return (
    <div className="page">
      <header>
        <h1>MovieMatch Vertical Slice</h1>
        <p>Flow: Frontend {'>'} Gateway {'>'} Orchestrator {'>'} Worker {'>'} DB/Cache {'>'} Response</p>
      </header>

      <section className="card">
        <h2>1) Login</h2>
        <form onSubmit={handleLogin} className="grid">
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>

          <button type="submit">Get JWT</button>
        </form>
      </section>

      <section className="card">
        <h2>2) Request recommendations</h2>
        <form onSubmit={handleRecommend} className="grid">
          <label>
            Mode
            <select value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
              <option value="collaborative">Collaborative</option>
              <option value="nlp">NLP Search</option>
              <option value="mood">Mood</option>
            </select>
          </label>

          <label>
            {queryLabel}
            <input value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>

          <label>
            Top K
            <input
              type="number"
              min={1}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            />
          </label>

          <button type="submit">Recommend</button>
        </form>
      </section>

      <section className="card">
        <h2>3) Results</h2>
        <p className="status">{status}</p>
        <ul>
          {recommendations.map((item, index) => (
            <li key={`${item.movie_id}-${index}`}>
              <strong>{index + 1}. {item.title}</strong>
              <span>score: {item.score.toFixed(3)}</span>
              <span>{item.reason}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
