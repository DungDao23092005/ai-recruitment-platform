import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Polyfill scrollTo for jsdom
if (typeof HTMLElement.prototype.scrollTo === 'undefined') {
  HTMLElement.prototype.scrollTo = vi.fn()
}

if (typeof globalThis.EventSource === 'undefined') {
  class EventSourceStub {
    static readonly CONNECTING = 0
    static readonly OPEN = 1
    static readonly CLOSED = 2

    readonly CONNECTING = 0
    readonly OPEN = 1
    readonly CLOSED = 2

    readyState = EventSourceStub.CONNECTING
    onopen: ((event: Event) => void) | null = null
    onerror: ((event: Event) => void) | null = null
    onmessage: ((event: MessageEvent) => void) | null = null

    constructor(readonly url: string) {}

    addEventListener(): void {}
    removeEventListener(): void {}
    close(): void {
      this.readyState = EventSourceStub.CLOSED
    }
  }

  Object.defineProperty(globalThis, 'EventSource', {
    value: EventSourceStub,
    writable: true,
    configurable: true,
  })
}

afterEach(() => {
  cleanup()
  localStorage.clear()
})