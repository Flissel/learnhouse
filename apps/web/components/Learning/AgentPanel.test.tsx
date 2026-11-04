// @ts-expect-error Bun supplies this runtime module; the web tsconfig intentionally omits Bun globals.
import { describe, expect, test } from 'bun:test'
import { readFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'

import AgentPanel from './AgentPanel'

describe('AgentPanel', () => {
  test('shows the tutor answer but never its next_step', () => {
    // Learning's next_step is at times written to a teacher and names expected values.
    const tutor = { answer: 'Welchen Wert hat p bei Ihnen?', nextStep: 'p=-6 wird erwartet, aber nicht vorgeben.' }
    const html = renderToStaticMarkup(
      <AgentPanel course={null} state="ready" visibleOnCompact onAsk={() => {}} tutor={tutor} />,
    )
    expect(html).toContain('Welchen Wert hat p bei Ihnen?')
    expect(html).not.toContain('Nächster Schritt')
    expect(html).not.toContain('p=-6')
  })

  test('the practice hook does not pass next_step on', () => {
    const src = readFileSync('hooks/usePracticeSession.ts', 'utf-8')
    expect(src.includes('next_step')).toBe(false)
  })
})
