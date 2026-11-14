import { useState } from 'react'
import { Link } from 'react-router'

import { API_BASE_URL } from '@/api/client'
import { authHeader } from '@/lib/auth'
import { useDocumentTitle } from '@/lib/format'

type Brand = {
  id: string
  brand_name: string
  generic_name: string
  drug_id: string | null
  manufacturer: string | null
  has_us_label_data: boolean
}

export function BdPage() {
  useDocumentTitle('Bangladesh brands')
  const [q, setQ] = useState('')
  const [items, setItems] = useState<Brand[]>([])
  const [note, setNote] = useState('')

  async function search() {
    setNote('')
    const res = await fetch(`${API_BASE_URL}/api/v1/bd/brands?q=${encodeURIComponent(q)}`, {
      headers: authHeader(),
    })
    if (!res.ok) {
      setNote('Search failed. Import brands with scripts/import_bd_brands.py --fixture first.')
      return
    }
    setItems((await res.json()) as Brand[])
  }

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold">Bangladesh brands</h1>
        <p className="max-w-prose text-muted-foreground">
          Reference: US FDA labeling on DailyMed, not DGDA labeling. Not medical advice.
        </p>
      </header>
      <div className="flex gap-2">
        <input
          aria-label="Brand search"
          className="w-full max-w-md rounded-md border px-3 py-2 text-sm"
          placeholder="Monas"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
          }}
        />
        <button
          type="button"
          className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground"
          onClick={() => {
            void search()
          }}
        >
          Search
        </button>
      </div>
      {note && <p className="text-sm">{note}</p>}
      <ul className="space-y-2">
        {items.map((b) => (
          <li key={b.id} className="rounded-lg border p-3">
            <p className="font-medium">
              {b.brand_name} — {b.generic_name}
            </p>
            <p className="text-sm text-muted-foreground">{b.manufacturer}</p>
            {b.has_us_label_data && b.drug_id ? (
              <Link to={`/drugs/${b.drug_id}`} className="text-sm underline">
                Open US label lag timeline
              </Link>
            ) : (
              <p className="text-sm text-muted-foreground">US label data not loaded yet.</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
