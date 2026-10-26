// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'

import { practiceModel } from './practiceModel'
import type { PracticeTurn } from '@/services/learning/practice'

const ref = JSON.stringify({ locator: { heading: 'Vor der Arbeit' }, content: 'Vor jedem Einsatz prüfen.' })

function turn(overrides: Partial<PracticeTurn> = {}): PracticeTurn {
  return {
    session_id: 's1', session_revision: 2, state: 'active', mode: 'training',
    task: { id: 't1', type: 'multiple_choice', prompt: 'Welche?', options: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }], source_refs: [ref] },
    progress: { completed: 1, total: 4 },
    ...overrides,
  }
}

describe('practiceModel', () => {
  test('maps an engine task with options, evidence and progress', () => {
    const model = practiceModel(turn(), { mode: 'training' })
    expect(model.sessionProgress).toEqual({ completed: 1, total: 4 })
    expect(model.task?.type).toBe('multiple_choice')
    expect((model.task as any).multiple).toBe(true)
    expect(model.task?.evidence[0]).toMatchObject({ title: 'Vor der Arbeit', locator: 'Vor jedem Einsatz prüfen.' })
  })

  test('says when an answer counted for mastery and when a person reviews it', () => {
    const counted = practiceModel(turn({ feedback: { state: 'correct', score: 1, mastery_applied: true } }), { mode: 'training' })
    expect(counted.feedback?.message).toContain('Lernstand ist aktualisiert')
    const review = practiceModel(turn({ feedback: { state: 'needs_review', score: 0.8 } }), { mode: 'training' })
    expect(review.feedback?.state).toBe('needs_review')
  })

  test('embeds the drawing page of the open canvas task and says when it was submitted', () => {
    const canvasTurn = turn({ task: { id: 'c1', type: 'penecho_canvas', prompt: 'Zeichne', options: [], source_refs: [] } })
    expect((practiceModel(canvasTurn, { mode: 'training' }).task as any).canvasUrl).toBeUndefined()
    const url = 'http://100.67.177.45:8090/zeichnen/t.s'
    const open = practiceModel(canvasTurn, { mode: 'training', canvas: { taskId: 'c1', url, submitted: false } })
    expect((open.task as any).canvasUrl).toBe(url)
    expect(open.feedback).toBeUndefined()
    const done = practiceModel(canvasTurn, { mode: 'training', canvas: { taskId: 'c1', url, submitted: true } })
    expect(done.feedback?.state).toBe('submitted')
    // A link of another task is never shown.
    expect((practiceModel(canvasTurn, { mode: 'training', canvas: { taskId: 'x', url, submitted: false } }).task as any).canvasUrl).toBeUndefined()
  })

  test('shows a summary when the session is completed and nothing without a session', () => {
    const done = practiceModel(turn({ state: 'completed', task: null, summary: { attempted: 4, correct: 3, score: 0.75 } }), { mode: 'training' })
    expect(done.summary).toEqual({ attempted: 4, correct: 3, score: 0.75 })
    expect(practiceModel(null, { mode: 'exam' }).task).toBeNull()
  })
})
