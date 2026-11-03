// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'
import { resumedTurn } from './resumeModel'

const turn = {
  session_id: '11111111-1111-1111-1111-111111111111',
  session_revision: 2,
  state: 'active' as const,
  mode: 'training' as const,
  task: null,
  progress: { completed: 1, total: 20 },
}

describe('resumedTurn', () => {
  test('is null when the engine has no active session', () => {
    expect(resumedTurn({ state: null, result: { session: null } })).toBeNull()
    expect(resumedTurn({ state: null, result: {} })).toBeNull()
  })
  test('returns the active training session', () => {
    expect(resumedTurn({ state: null, result: { session: turn } })).toEqual(turn)
  })
  test('leaves exam sessions and finished sessions out', () => {
    expect(resumedTurn({ state: null, result: { session: { ...turn, mode: 'exam' } } })).toBeNull()
    expect(resumedTurn({ state: null, result: { session: { ...turn, state: 'completed' } } })).toBeNull()
  })
})
