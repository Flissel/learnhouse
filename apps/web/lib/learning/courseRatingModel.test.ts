// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'

import { allesSuper, cleanKeywords, prefillFrom, shouldPrefill } from './courseRatingModel'

describe('cleanKeywords', () => {
  test('trims and drops empty entries', () => {
    expect(cleanKeywords([' a ', '', 'b'])).toEqual({ ok: true, stichworte: ['a', 'b'] })
  })

  test('rejects a keyword longer than 40 characters', () => {
    expect(cleanKeywords(['x'.repeat(41)])).toEqual({ ok: false, fehler: 'zu_lang' })
    expect(cleanKeywords(['x'.repeat(40)]).ok).toBe(true)
  })

  test('caps at three keywords', () => {
    expect(cleanKeywords(['a', 'b', 'c', 'd'])).toEqual({ ok: true, stichworte: ['a', 'b', 'c'] })
  })
})

describe('prefillFrom', () => {
  test('reads the rating out of the proxy wrapper', () => {
    const reply = { bewertung: { smiley: 'mittel', stichworte: ['laut'], aktualisiert: '2026-10-30T10:00:00' } }
    expect(prefillFrom(reply as never)).toEqual({ smiley: 'mittel', words: ['laut', '', ''] })
  })
  test('returns null when there is no rating yet', () => {
    expect(prefillFrom({ bewertung: null })).toBeNull()
    expect(prefillFrom(null)).toBeNull()
    expect(prefillFrom({} as never)).toBeNull()
  })
})

describe('allesSuper', () => {
  test('is a good rating without keywords', () => {
    expect(allesSuper()).toEqual({ smiley: 'gut', stichworte: [] })
  })
})

describe('shouldPrefill', () => {
  test('prefills only while the form is untouched', () => {
    expect(shouldPrefill(false)).toBe(true)
    expect(shouldPrefill(true)).toBe(false)
  })
})
