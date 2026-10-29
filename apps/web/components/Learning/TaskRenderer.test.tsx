// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import TaskRenderer, { type MatchingTask, type NumericTask } from './TaskRenderer'

const graph = (n: number) => ({ src: `http://h/lernsequenz-medien/graph-${n}.png`, width: 480, height: 320 })

describe('TaskRenderer', () => {
  // Final review: right-side pictures were parsed but never shown, so "Graph 1/2/3" could not be told apart.
  test('a matching task shows the right-hand pictures and keeps choosing by label', () => {
    const task: MatchingTask = {
      id: 'm1',
      type: 'matching',
      prompt: 'Ordnen Sie jedem Graphen den Graphen seiner Ableitung zu.',
      evidence: [],
      math: true,
      left: [{ id: 'l1', label: 'Funktion A', image: graph(0) }],
      right: [
        { id: 'r1', label: 'Graph 1', image: graph(1) },
        { id: 'r2', label: 'Graph 2', image: graph(2) },
        { id: 'r3', label: 'Ohne Bild' },
      ],
    }
    const html = renderToStaticMarkup(<TaskRenderer submitLabel="Antwort prüfen" task={task} />)

    for (const n of [0, 1, 2]) expect(html).toContain(`src="http://h/lernsequenz-medien/graph-${n}.png"`)
    expect(html).toContain('alt="Graph 1"')
    expect(html).toContain('Ohne Bild')
    expect(html).toContain('<option value="r1">Graph 1</option>')
    expect(html).toContain('<option value="r2">Graph 2</option>')
    // Options are labels only, never pictures.
    expect(html).not.toMatch(/<option[^>]*>[^<]*<img/)
  })

  test('a matching task without pictures lists no extra choice gallery', () => {
    const task: MatchingTask = {
      id: 'm2', type: 'matching', prompt: 'Ordnen Sie zu.', evidence: [],
      left: [{ id: 'l1', label: 'Terminal' }],
      right: [{ id: 'r1', label: 'Das Fenster für Befehle' }],
    }
    const html = renderToStaticMarkup(<TaskRenderer submitLabel="Antwort prüfen" task={task} />)
    expect(html).not.toContain('<img')
    expect(html).toContain('<option value="r1">Das Fenster für Befehle</option>')
  })

  // iPhone keyboards for inputMode="decimal" have no minus key: "-1,5" could not be typed.
  test('the number field opens a keyboard with a minus sign', () => {
    const task: NumericTask = { id: 'n1', type: 'numeric', prompt: 'Lösen Sie $2x=-3$.', evidence: [], math: true, unit: 'x =' }
    const html = renderToStaticMarkup(<TaskRenderer submitLabel="Antwort prüfen" task={task} />)
    expect(html).toContain('inputMode="text"')
    expect(html).not.toContain('inputMode="decimal"')
  })
})
