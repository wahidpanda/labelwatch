import { createBrowserRouter, createMemoryRouter, type RouteObject } from 'react-router'

import { Layout } from '@/app/Layout'
import { DashboardPage } from '@/pages/DashboardPage'
import { DrugPage } from '@/pages/DrugPage'
import { EventPage } from '@/pages/EventPage'
import { LeafletPage } from '@/pages/LeafletPage'
import { MethodologyPage } from '@/pages/MethodologyPage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { StalePage } from '@/pages/StalePage'

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'drugs/:drugId', element: <DrugPage /> },
      { path: 'events/:eventId', element: <EventPage /> },
      { path: 'stale', element: <StalePage /> },
      { path: 'methodology', element: <MethodologyPage /> },
      { path: 'leaflet', element: <LeafletPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]

export function createAppRouter() {
  return createBrowserRouter(routes)
}

export function createTestRouter(initialPath = '/') {
  return createMemoryRouter(routes, { initialEntries: [initialPath] })
}
