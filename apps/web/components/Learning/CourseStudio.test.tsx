// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import CourseStudio, { type CourseStudioModel } from './CourseStudio'

const model: CourseStudioModel = {
  audience: 'Fachteams in regulierten Unternehmen',
  outcome: 'KI-Systeme fachlich und sicher beurteilen',
  prerequisites: 'Grundlagen zu Daten und Prozessen',
  difficulty: 'advanced',
  sources: [
    { id: 'source-1', title: 'Interne KI-Richtlinie', state: 'ready', revision: 2 },
    { id: 'source-2', title: 'Unlesbarer Scan', state: 'failed', errorCode: 'parse_failed' },
  ],
  generation: {
    stage: 'quality_gate',
    progress: 86,
    unsupportedClaims: [
      { id: 'claim-1', text: 'Das Verfahren ist in jeder Branche verpflichtend.' },
    ],
    sourceCoverage: 78,
    regenerationAttempts: 1,
    maximumRegenerationAttempts: 3,
  },
  reviewStatus: 'pending',
}

describe('CourseStudio', () => {
  test('renders course definition, source versions, ingestion errors, and generation progress', () => {
    const html = renderToStaticMarkup(
      <CourseStudio
        course={{ id: 'course-1', name: 'Verantwortungsvolle KI' }}
        model={model}
        onPublish={() => undefined}
      />,
    )

    expect(html).toContain('Zielgruppe')
    expect(html).toContain('Lernziel')
    expect(html).toContain('Voraussetzungen')
    expect(html).toContain('Fortgeschritten')
    expect(html).toContain('Interne KI-Richtlinie')
    expect(html).toContain('name="sourceTitle"')
    expect(html).toContain('name="sourceUrl"')
    expect(html).toContain('Version 2')
    expect(html).toContain('Verarbeitung fehlgeschlagen')
    expect(html).toContain('Qualitätsprüfung')
    expect(html).toContain('86%')
  })

  test('shows unsupported claims, bounded regeneration, and explicit publication', () => {
    const pending = renderToStaticMarkup(
      <CourseStudio
        course={{ id: 'course-1', name: 'Verantwortungsvolle KI' }}
        model={model}
      />,
    )
    const approved = renderToStaticMarkup(
      <CourseStudio
        course={{ id: 'course-1', name: 'Verantwortungsvolle KI' }}
        model={{ ...model, reviewStatus: 'approved' }}
        onPublish={() => undefined}
      />,
    )

    expect(pending).toContain('Nicht belegte Aussage')
    expect(pending).toContain('2 von 3 Versuchen verfügbar')
    expect(pending).toContain('Kurs ausdrücklich veröffentlichen')
    expect(pending).toContain('disabled=""')
    expect(approved).toContain('Freigabe erteilt')
    const publishLabel = approved.indexOf('Kurs ausdrücklich veröffentlichen')
    const publishTag = approved.slice(approved.lastIndexOf('<button', publishLabel), approved.indexOf('>', publishLabel))
    expect(publishTag).not.toContain(' disabled=""')
  })
})
