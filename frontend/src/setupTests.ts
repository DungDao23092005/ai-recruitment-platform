import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Polyfill scrollTo for jsdom
if (typeof HTMLElement.prototype.scrollTo === 'undefined') {
  HTMLElement.prototype.scrollTo = vi.fn()
}

afterEach(() => {
  cleanup()
  localStorage.clear()
})