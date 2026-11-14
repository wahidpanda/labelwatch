import { MessageCircle, X } from 'lucide-react'
import { useState } from 'react'

import { useChat } from '@/hooks/useChat'

export function ChatDock() {
  const [open, setOpen] = useState(false)
  const chat = useChat()

  return (
  <>
      <button
      type="button"
      aria-label={open ? 'Close assistant' : 'Open assistant'}
      className="fixed bottom-5 right-5 z-50 flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition hover:scale-105 focus-visible:ring-2 focus-visible:ring-ring"
      onClick={() => {
        setOpen((v) => !v)
      }}
    >
      {open ? <X className="size-6" /> : <MessageCircle className="size-6" />}
    </button>
    {open && (
      <div
        role="dialog"
        aria-labelledby="chat-dock-title"
        className="fixed bottom-24 right-5 z-50 flex w-[min(100vw-2.5rem,24rem)] flex-col gap-3 rounded-2xl border bg-card/95 p-4 shadow-2xl backdrop-blur-md"
      >
        <h2 id="chat-dock-title" className="text-sm font-semibold">
          Data assistant
        </h2>
        <p className="text-xs text-muted-foreground">
          Overview answers from live stats. Full agent tools coming next. Not medical advice.
        </p>
        {chat.steps.length > 0 && (
          <ul className="flex flex-wrap gap-1 text-xs text-muted-foreground">
            {chat.steps.map((s) => (
              <li key={s} className="rounded-full bg-muted px-2 py-0.5">
                {s}
              </li>
            ))}
          </ul>
        )}
        <textarea
          aria-label="Question"
          rows={2}
          className="w-full resize-none rounded-lg border bg-background px-3 py-2 text-sm"
          placeholder="How many judgements today?"
          value={chat.question}
          onChange={(e) => {
            chat.setQuestion(e.target.value)
          }}
        />
        <button
          type="button"
          disabled={chat.busy}
          className="rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"
          onClick={() => {
            void chat.ask()
          }}
        >
          {chat.busy ? 'Thinking…' : 'Ask'}
        </button>
        {chat.answer && <p className="max-h-40 overflow-y-auto text-sm">{chat.answer}</p>}
      </div>
    )}
    </>
  )
}
