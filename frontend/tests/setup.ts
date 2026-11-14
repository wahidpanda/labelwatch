import '@testing-library/jest-dom/vitest'
import { configure } from '@testing-library/react'

// Cold CI runners render the first page slowly; the 1 s default flakes.
configure({ asyncUtilTimeout: 5000 })
