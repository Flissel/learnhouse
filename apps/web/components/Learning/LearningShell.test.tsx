// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import LearningShell, {
  nextPanelAfterKey,
  type LearningCourse,
  type LearningShellState,
} from './LearningShell'

const longCourseName =
  'Verantwortungsvolle KI-Systeme in regulierten Schweizer Versorgungsunternehmen'

const courses: LearningCourse[] = [
  {
    id: 'course_responsible-ai',
    name: longCourseName,
    description: 'Governance, Betrieb und belastbare Entscheidungen.',
  },
  {
    id: 'course_prompt-systems',
    name: 'Prompt-Systeme für Fachteams',
  },
]

function render(state: LearningShellState, items = courses) {
  return renderToStaticMarkup(
    <LearningShell orgslug="academy" courses={items} state={state} />,
  )
}

describe('LearningShell', () => {
  test('renders the approved four-area workspace and permanent status strip', () => {
    const html = render('ready')

    expect(html).toContain('data-testid="space-rail"')
    expect(html).toContain('data-testid="course-outline"')
    expect(html).toContain('data-testid="learning-workspace"')
    expect(html).toContain('data-testid="agent-panel"')
    expect(html).toContain('data-testid="status-strip"')
    expect(html).toContain('h-[calc(100vh-4rem)]')
    expect(html).not.toContain('min-h-[calc(100vh-4rem)]')
    expect(html).toContain('href="#learning-workspace"')
    expect(html).toContain('MCP nicht geprüft')
    expect(html).not.toContain('MCP verbunden')
  })

  const stateCases: ReadonlyArray<readonly [Exclude<LearningShellState, 'ready'>, string]> = [
    ['loading', 'Kurse werden geladen'],
    ['empty', 'Noch keine Kurse'],
    ['error', 'Kurse konnten nicht geladen werden'],
    ['degraded', 'Eingeschränkter Betrieb'],
  ]

  for (const [state, label] of stateCases) {
    test(`renders the ${state} state`, () => {
      expect(render(state, [])).toContain(label)
    })
  }

  test('keeps long labels in wrapping, shrinkable regions', () => {
    const html = render('ready')

    expect(html).toContain(longCourseName)
    expect(html).toContain('break-words')
    expect(html).toContain('min-w-0')
  })

  test('provides compact panel controls and focus targets', () => {
    const html = render('ready')

    expect(html).toContain('aria-controls="course-outline"')
    expect(html).toContain('aria-controls="learning-workspace"')
    expect(html).toContain('aria-controls="agent-panel"')
    expect(html).toContain('tabindex="-1"')
  })

  test('returns focus to the workspace when Escape closes a compact panel', () => {
    expect(nextPanelAfterKey('outline', 'Escape')).toBe('workspace')
    expect(nextPanelAfterKey('agent', 'Escape')).toBe('workspace')
    expect(nextPanelAfterKey('outline', 'ArrowDown')).toBe('outline')
  })
})
