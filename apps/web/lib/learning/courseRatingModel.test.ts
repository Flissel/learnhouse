// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'

import { allesSuper, cleanKeywords } from './courseRatingModel'

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

describe('allesSuper', () => {
  test('is a good rating without keywords', () => {
    expect(allesSuper()).toEqual({ smiley: 'gut', stichworte: [] })
  })
})
