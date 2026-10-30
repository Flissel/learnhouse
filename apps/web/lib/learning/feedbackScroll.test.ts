// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'

import { shouldScrollToFeedback } from './feedbackScroll'

describe('shouldScrollToFeedback', () => {
  test('scrolls when feedback newly appears', () => {
    expect(shouldScrollToFeedback(undefined, { message: 'Richtig' })).toBe(true)
    expect(shouldScrollToFeedback(null, { message: 'Richtig' })).toBe(true)
  })
  test('does not scroll without feedback or when it was already shown', () => {
    expect(shouldScrollToFeedback(undefined, undefined)).toBe(false)
    expect(shouldScrollToFeedback({ message: 'a' }, undefined)).toBe(false)
    expect(shouldScrollToFeedback({ message: 'a' }, { message: 'a' })).toBe(false)
  })
  test('scrolls when new feedback replaces older feedback', () => {
    expect(shouldScrollToFeedback({ message: 'a' }, { message: 'b' })).toBe(true)
  })
})
