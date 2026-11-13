import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <section aria-labelledby="not-found-title" className="space-y-4">
      <h1 id="not-found-title" className="text-3xl font-semibold">
        Page not found
      </h1>
      <Link to="/" className="text-accent underline">
        Back to the dashboard
      </Link>
    </section>
  )
}
