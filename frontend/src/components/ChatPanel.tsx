import { useState } from 'react'

import { API_BASE_URL } from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export function ChatPanel() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)

  async function ask() {
    if (!question.trim()) return
    setBusy(true)
    setAnswer('')
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, locale: 'en' }),
      })
      const text = await res.text()
      const tokens = [...text.matchAll(/"text"\s*:\s*"([^"]*)"/g)].map((m) => m[1])
      setAnswer(tokens.join(''))
    } catch {
      setAnswer('Could not reach the chat service.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Ask the data</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">Not medical advice. Answers use dashboard stats only.</p>
        <div className="flex gap-2">
          <input
            aria-label="Question"
            className="w-full rounded-md border px-3 py-2 text-sm"
            placeholder="How many judgements do we have?"
            value={question}
            onChange={(e) => {
              setQuestion(e.target.value)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void ask()
            }}
          />
          <button
            type="button"
            className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"
            disabled={busy}
            onClick={() => {
              void ask()
            }}
          >
            Ask
          </button>
        </div>
        {answer && <p className="text-sm">{answer}</p>}
      </CardContent>
    </Card>
  )
}
