// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'

import { answerFromForm } from '@components/Learning/TaskRenderer'
import { imageFallback, parseNumber, practiceModel, practiceTask } from './practiceModel'
import { readFileSync } from 'node:fs'
import { excerpt } from '@/services/learning/practice'
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

  test('an image fill_in also keeps its text template for the fallback', () => {
    // Final review: without it a missing picture left an empty input with no command.
    const presentation = {
      image: 'http://h/lernsequenz-medien/term-0123456789abcdef.png', width: 560, height: 96, shell: 'cmd',
      rect: { x: 280, y: 54, w: 132, h: 22 }, template: 'curl -fsSL https://claude.ai/{{wert}} -o {{wert}}',
    }
    const model = practiceModel(turn({ task: { ...base, type: 'fill_in', presentation } }), { mode: 'training' })
    expect((model.task as any).template).toBe('curl -fsSL https://claude.ai/{{wert}} -o {{wert}}')
    expect(imageFallback((model.task as any))).toBe(false)
    expect(imageFallback({ ...(model.task as any), image: undefined })).toBe(true)
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

  test('matching right items keep their graph picture', () => {
    const presentation = {
      left: [{ id: 'l1', label: 'Funktion A' }],
      right: [{ id: 'r1', label: 'Graph 1', image: 'http://h/lernsequenz-medien/graph-1.png', width: 480, height: 320 }],
    }
    const model = practiceModel(turn({ task: { ...base, type: 'matching', presentation } }), { mode: 'training' })
    expect((model.task as any).right[0]).toEqual({
      id: 'r1', label: 'Graph 1', image: { src: 'http://h/lernsequenz-medien/graph-1.png', width: 480, height: 320 },
    })
  })
})

describe('numeric tasks', () => {
  test('maps a numeric engine task with its unit', () => {
    const model = practiceModel(
      turn({ task: { id: 't2', type: 'numeric', prompt: 'Lösen Sie $2x=4$.', options: [], source_refs: [ref], presentation: { unit: 'x =' } } }),
      { mode: 'training' },
    )
    expect(model.task).toMatchObject({ type: 'numeric', unit: 'x =' })
  })

  test('numeric task without unit has none', () => {
    const model = practiceModel(
      turn({ task: { id: 't2', type: 'numeric', prompt: 'p', options: [], source_refs: [ref] } }),
      { mode: 'training' },
    )
    expect((model.task as any).unit).toBeUndefined()
  })
})

describe('parseNumber', () => {
  test('accepts comma, spaces and exponent', () => {
    expect(parseNumber('-1,5')).toBe(-1.5)
    expect(parseNumber(' 2 ')).toBe(2)
    expect(parseNumber('1e3')).toBe(1000)
    expect(parseNumber('\u22121,5')).toBe(-1.5)
  })
  test('rejects nonsense', () => {
    expect(parseNumber('zwei')).toBeNull()
    expect(parseNumber('')).toBeNull()
    expect(parseNumber('1,2,3')).toBeNull()
    expect(parseNumber('Infinity')).toBeNull()
    expect(parseNumber('NaN')).toBeNull()
    expect(parseNumber('0x10')).toBeNull()
    expect(parseNumber('1.000,5')).toBeNull()
  })
})

const base = { id: 't', prompt: 'p', options: [], source_refs: [ref] }

describe('math opt-in', () => {
  test('Terminal strings stay plain: math is false without presentation.math', () => {
    const template = '$currentPath;$env:USERPROFILE\\.local\\bin {{wert}}'
    const fill = practiceTask({ ...base, type: 'fill_in', presentation: { template } })
    expect(fill.math).toBe(false)
    expect((fill as any).template).toBe(template)
    const label = 'export PATH="$HOME/.local/bin:$PATH"'
    const opt = practiceTask({ ...base, type: 'single_choice', options: [{ id: 'a', label }] })
    expect(opt.math).toBe(false)
    expect((opt as any).options[0].label).toBe(label)
  })

  test('math is true only for presentation.math === true', () => {
    expect(practiceTask({ ...base, type: 'numeric', presentation: { math: true } }).math).toBe(true)
    for (const v of ['true', 1, false, null]) {
      expect(practiceTask({ ...base, type: 'numeric', presentation: { math: v } }).math).toBe(false)
    }
    expect(practiceTask({ ...base, type: 'numeric' }).math).toBe(false)
  })

  test('the player model carries the flag for feedback', () => {
    expect(practiceModel(turn(), { mode: 'training' }).task?.math).toBe(false)
  })
})

describe('answerFromForm numeric', () => {
  const task = practiceTask({ ...base, type: 'numeric' })
  const form = (v: string) => { const f = new FormData(); f.set('answer', v); return f }
  test('valid input gives a number', () => {
    expect(answerFromForm(task, form('-1,5'))).toEqual({ value: -1.5 })
  })
  test('invalid input gives no answer', () => {
    expect(answerFromForm(task, form('zwei'))).toBeNull()
    expect(answerFromForm(task, form(''))).toBeNull()
  })

  test('shows only criteria below 100 % with the grader text', () => {
    const model = practiceModel(turn({
      feedback: {
        state: 'partial', score: 0.5,
        criteria: [
          { criterion_id: 'c1', description: 'Ansatz', score: 1, feedback: 'passt' },
          { criterion_id: 'c2', description: 'Rechenweg', score: 0.4, feedback: 'Der Faktor $2$ fehlt.' },
        ],
      },
    }), { mode: 'training' })
    expect(model.feedback?.criteria).toEqual([{ id: 'c2', description: 'Rechenweg', feedback: 'Der Faktor $2$ fehlt.' }])
    expect(practiceModel(turn({ feedback: { state: 'incorrect', score: 0 } }), { mode: 'training' }).feedback?.criteria).toBeUndefined()
  })

  test('drops evidence duplicates with the same title', () => {
    const other = JSON.stringify({ locator: { heading: 'Anderes' }, content: 'x' })
    const task = { ...turn().task!, source_refs: [ref, ref, other] }
    expect(practiceTask(task).evidence.map((e) => e.title)).toEqual(['Vor der Arbeit', 'Anderes'])
  })

  test('learner texts avoid the informal du-form', () => {
    const texts = ['correct', 'partial', 'incorrect', 'needs_review'].map((state) => {
      const m = practiceModel(turn({ feedback: { state: state as 'correct', score: 1, mastery_applied: true } }), { mode: 'training' })
      return m.feedback!.message
    })
    const canvas = practiceModel(turn(), { mode: 'training', canvas: { taskId: 't1', url: 'u', submitted: true } })
    texts.push(canvas.feedback!.message)
    for (const text of texts) expect(text).not.toMatch(/(du|dein\w*|dir|dich|schau)/i)
  })

  test('excerpts are cut outside formulas, at whitespace, with an ellipsis', () => {
    const text = `${'wort '.repeat(78)}$a + b$ und mehr`
    const cut = excerpt(text, 400)
    expect((cut.match(/\$/g) ?? []).length % 2).toBe(0)
    expect(cut.endsWith('…')).toBe(true)
    expect(excerpt('kurz')).toBe('kurz')
  })

  test('learner-visible strings in the touched components avoid du-forms', () => {
    const files = ['LearningPlayer.tsx', 'TaskRenderer.tsx', 'AgentPanel.tsx', 'SourceEvidence.tsx']
      .map((f) => `components/Learning/${f}`).concat('components/Pages/Courses/CourseStart.tsx')
    const du = /\b(du|dein\w*|dir|dich)\b/i
    for (const file of files) {
      const src = readFileSync(file, 'utf-8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
      const strings = [
        ...[...src.matchAll(/'([^'\n]*)'|"([^"\n]*)"|`([^`]*)`/g)].map((m) => m[1] ?? m[2] ?? m[3] ?? ''),
        ...[...src.matchAll(/>([^<>{}]+)</g)].map((m) => m[1]),
      ]
      for (const text of strings) expect([file, du.test(text) ? text : '']).toEqual([file, ''])
    }
  })
})
