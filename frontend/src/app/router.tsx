import { createBrowserRouter, createMemoryRouter, type RouteObject } from 'react-router'

import { Layout } from '@/app/Layout'
import { DashboardPage } from '@/pages/DashboardPage'
import { NotFoundPage } from '@/pages/NotFoundPage'

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <DashboardPage /> },
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
