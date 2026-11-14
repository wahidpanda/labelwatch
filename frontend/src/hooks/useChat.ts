import { useCallback, useState } from 'react'

import { API_BASE_URL } from '@/api/client'
import { authHeader } from '@/lib/auth'

export function useChat() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [steps, setSteps] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  const ask = useCallback(async () => {
    if (!question.trim()) return
    setBusy(true)
    setAnswer('')
    setSteps([])
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader() },
        body: JSON.stringify({ question, locale: 'en' }),
      })
      if (res.status === 401) {
        setAnswer('Sign in again to use the assistant.')
        return
      }
      const text = await res.text()
      const tokens = [...text.matchAll(/"text"\s*:\s*"([^"]*)"/g)]
        .map((m) => m[1])
        .filter((s): s is string => Boolean(s))
      const foundSteps = [...text.matchAll(/"name"\s*:\s*"([^"]*)"/g)]
        .map((m) => m[1])
        .filter((s): s is string => Boolean(s))
      setSteps(foundSteps)
      setAnswer(tokens.join(''))
    } catch {
      setAnswer('Could not reach the chat service.')
    } finally {
      setBusy(false)
    }
  }, [question])

  return { question, setQuestion, answer, steps, busy, ask }
}
