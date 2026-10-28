// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'

import { splitMath } from './mathSplit'

describe('splitMath', () => {
  test('splits inline and block formulas from text', () => {
    expect(splitMath('a $x^2$ b $$y$$')).toEqual([
      { kind: 'text', value: 'a ' },
      { kind: 'inline', value: 'x^2' },
      { kind: 'text', value: ' b ' },
      { kind: 'block', value: 'y' },
    ])
  })

  test('leaves a lone or currency dollar sign as text', () => {
    expect(splitMath('5 $ heute')).toEqual([{ kind: 'text', value: '5 $ heute' }])
    expect(splitMath('Es kostet 5 $ und 6 $ morgen')).toEqual([{ kind: 'text', value: 'Es kostet 5 $ und 6 $ morgen' }])
  })

  test('plain text and empty input', () => {
    expect(splitMath('Hallo')).toEqual([{ kind: 'text', value: 'Hallo' }])
    expect(splitMath('')).toEqual([])
  })
})
