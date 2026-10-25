// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import LearningPlayer, { type LearningPlayerModel } from './LearningPlayer'

const training: LearningPlayerModel = {
  mode: 'training',
  sessionProgress: { completed: 3, total: 8 },
  task: {
    id: 'task-1',
    type: 'multiple_choice',
    prompt: 'Welche Maßnahme begrenzt Halluzinationen in Fachantworten am direktesten?',
    options: [
      { id: 'a', label: 'Quellengebundene Retrieval-Prüfung' },
      { id: 'b', label: 'Höhere Temperatur' },
    ],
    evidence: [
      { id: 'evidence-1', title: 'KI-Richtlinie', locator: 'Kapitel 4.2', supported: true },
    ],
  },
  feedback: {
    state: 'incorrect',
    message: 'Die Antwort erhöht Varianz, begrenzt aber keine unbelegten Aussagen.',
    misconception: 'Kreativität mit Verlässlichkeit verwechselt',
  },
  hint: 'Prüfe, welche Option Aussagen auf freigegebene Fachquellen zurückführt.',
}

describe('LearningPlayer', () => {
  test('renders a real task, answer controls, grounded feedback, hints, and progress in training mode', () => {
    const html = renderToStaticMarkup(
      <LearningPlayer course={{ id: 'course-1', name: 'Verantwortungsvolle KI' }} model={training} />,
    )

    expect(html).toContain('Training')
    expect(html).toContain('3 von 8')
    expect(html).toContain('Welche Maßnahme')
    expect(html).toContain('Quellengebundene Retrieval-Prüfung')
    expect(html).toContain('Antwort prüfen')
    expect(html).toContain('Hinweis anzeigen')
    expect(html).toContain('Kreativität mit Verlässlichkeit verwechselt')
    expect(html).toContain('KI-Richtlinie')
    expect(html).toContain('Kapitel 4.2')
    expect(html).toContain('id="answer"')
  })

  test('withholds hints and correctness feedback in exam mode', () => {
    const html = renderToStaticMarkup(
      <LearningPlayer
        course={{ id: 'course-1', name: 'Verantwortungsvolle KI' }}
        model={{ ...training, mode: 'exam' }}
      />,
    )

    expect(html).toContain('Prüfung')
    expect(html).not.toContain('Hinweis anzeigen')
    expect(html).not.toContain('Kreativität mit Verlässlichkeit verwechselt')
    expect(html).toContain('Antwort abgeben')
  })

  test('offers a host-owned session start when no task is active', () => {
    const html = renderToStaticMarkup(
      <LearningPlayer
        course={{ id: 'course-1', name: 'Verantwortungsvolle KI' }}
        model={{ mode: 'training', sessionProgress: { completed: 0, total: 0 }, task: null }}
        onStartSession={() => undefined}
      />,
    )

    expect(html).toContain('Lernsitzung starten')
    expect(html).not.toContain('VibeMind Host erforderlich')
  })
})
