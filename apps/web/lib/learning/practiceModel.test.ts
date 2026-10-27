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

describe('practiceTask for hands-on items', () => {
  const base = { id: 't9', prompt: 'Sortiere', options: [] as Array<{ id: string; label: string }>, source_refs: [ref] }

  test('ordering keeps the (already shuffled) options as items', () => {
    const model = practiceModel(turn({ task: { ...base, type: 'ordering', options: [{ id: 's2', label: 'Zwei' }, { id: 's1', label: 'Eins' }] } }), { mode: 'training' })
    expect(model.task?.type).toBe('ordering')
    expect((model.task as any).items.map((i: any) => i.id)).toEqual(['s2', 's1'])
  })

  test('matching takes left and right from the presentation', () => {
    const presentation = { left: [{ id: 'b1', label: 'Terminal' }], right: [{ id: 'e1', label: 'Das Fenster für Befehle' }] }
    const model = practiceModel(turn({ task: { ...base, type: 'matching', presentation } }), { mode: 'training' })
    expect(model.task?.type).toBe('matching')
    expect((model.task as any).left[0].label).toBe('Terminal')
    expect((model.task as any).right[0].id).toBe('e1')
  })

  test('fill_in carries the template with its blank', () => {
    const model = practiceModel(turn({ task: { ...base, type: 'fill_in', presentation: { template: 'irm https://claude.ai/{{wert}} | iex', shell: 'powershell' } } }), { mode: 'training' })
    expect(model.task?.type).toBe('fill_in')
    expect((model.task as any).template).toBe('irm https://claude.ai/{{wert}} | iex')
  })

  // 27.10.: drawn terminal windows with an empty box to fill, and windows to match.
  test('an image fill_in keeps picture, size and boxes', () => {
    const presentation = {
      image: 'http://100.67.177.45:8090/lernsequenz-medien/term-0123456789abcdef.png', width: 560, height: 96, shell: 'powershell',
      rect: { x: 280, y: 54, w: 132, h: 22 }, more: [{ x: 18, y: 80, w: 132, h: 22 }],
    }
    const model = practiceModel(turn({ task: { ...base, type: 'fill_in', presentation } }), { mode: 'training' })
    expect((model.task as any).image).toEqual({ src: presentation.image, width: 560, height: 96, rect: presentation.rect, more: presentation.more })
    expect((model.task as any).shell).toBe('powershell')
  })

  test('a broken image presentation falls back to the text blank', () => {
    const presentation = { image: 'http://x/term.png', width: '560', rect: { x: 1 }, template: 'a {{wert}}' }
    const model = practiceModel(turn({ task: { ...base, type: 'fill_in', presentation } }), { mode: 'training' })
    expect((model.task as any).image).toBeUndefined()
    expect((model.task as any).template).toBe('a {{wert}}')
  })

  test('matching items keep their window picture', () => {
    const presentation = {
      left: [{ id: 'f1', label: 'Fenster 1', image: 'http://h/lernsequenz-medien/term-a.png', width: 560, height: 96 }, { id: 'f2', label: 'Text' }],
      right: [{ id: 's1', label: 'Windows CMD' }],
    }
    const model = practiceModel(turn({ task: { ...base, type: 'matching', presentation } }), { mode: 'training' })
    expect((model.task as any).left[0].image).toEqual({ src: 'http://h/lernsequenz-medien/term-a.png', width: 560, height: 96 })
    expect((model.task as any).left[1].image).toBeUndefined()
  })
})
